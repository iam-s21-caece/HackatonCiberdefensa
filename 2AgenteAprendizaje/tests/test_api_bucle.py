import hashlib
import json
import shutil

from fastapi.testclient import TestClient

from agente_aprendizaje.api import crear_app
from agente_aprendizaje.bucle import AgenteAprendizaje

from .conftest import ESCENARIOS, REPORTES_DIR, buscar

AUTH = {"Authorization": "Bearer secreto-de-prueba"}


def huella(directorio) -> dict:
    return {p.name: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in directorio.iterdir()}


# ------------------------------------------------------------------ RA2-08
def test_ra2_08_lectura_libre_y_escritura_con_token_bearer(config):
    rid = buscar("bec_suplantacion_interna", "original", "legitimo").id
    with TestClient(crear_app(config)) as c:
        for ruta in ("/api/salud", "/api/reportes", f"/api/reportes/{rid}", "/api/cola", "/api/metricas",
                     "/api/calibracion", "/api/supervision", "/api/actores", "/api/aprendizaje", "/api/attack",
                     "/api/attack/navigator"):
            assert c.get(ruta).status_code == 200, ruta
        cuerpo = {"veredicto": "MALICIOSO", "analista": "sgto.gomez", "comentario": "BEC confirmado"}
        assert c.post(f"/api/reportes/{rid}/veredicto", json=cuerpo).status_code == 401
        assert c.post(f"/api/reportes/{rid}/veredicto", json=cuerpo,
                      headers={"Authorization": "Bearer otro"}).status_code == 401
        assert c.post(f"/api/reportes/{rid}/veredicto", json=cuerpo, headers=AUTH).status_code == 201
        # RG-02: contrato validado
        assert c.post(f"/api/reportes/{rid}/veredicto", json={**cuerpo, "veredicto": "QUIZAS"}, headers=AUTH).status_code == 422
        assert c.post("/api/reportes/inexistente/veredicto", json=cuerpo, headers=AUTH).status_code == 404


def test_ra2_08_sin_token_configurado_la_escritura_queda_deshabilitada(config):
    config.token = ""
    rid = buscar("interno_legitimo", "original", "coincide").id
    with TestClient(crear_app(config)) as c:
        r = c.post(f"/api/reportes/{rid}/veredicto", json={"veredicto": "LEGITIMO", "analista": "x"},
                   headers={"Authorization": "Bearer "})
        assert r.status_code == 403
        assert c.get("/api/salud").json()["escritura_habilitada"] is False


# ------------------------------------------------------------------ RA2-02
def test_ra2_02_veredicto_append_only_vale_el_ultimo_y_conserva_historial(config):
    rid = buscar("bec_autenticacion_forjada", "original", "caida").id
    with TestClient(crear_app(config)) as c:
        c.post(f"/api/reportes/{rid}/veredicto", json={"veredicto": "LEGITIMO", "analista": "a"}, headers=AUTH)
        c.post(f"/api/reportes/{rid}/veredicto", json={"veredicto": "MALICIOSO", "analista": "b",
                                                      "comentario": "cabecera forjada"}, headers=AUTH)
        detalle = c.get(f"/api/reportes/{rid}").json()
        assert [v["veredicto"] for v in detalle["veredicto_humano"]] == ["LEGITIMO", "MALICIOSO"]
        assert detalle["veredicto_humano"][-1]["anterior"] == "LEGITIMO"
        fila = next(f for f in c.get("/api/reportes").json() if f["report_id"] == rid)
        assert fila["veredicto_humano"] == "MALICIOSO"
    lineas = config.veredictos_path.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2 and json.loads(lineas[0])["veredicto"] == "LEGITIMO"


# ------------------------------------------------------------------ RA2-01
def test_ra2_01_lectura_incremental_y_nunca_escribe_en_los_reportes_del_flujo(config, tmp_path):
    origen = sorted(REPORTES_DIR.glob("*.json"))
    config.reportes_dir = tmp_path / "reports"
    config.reportes_dir.mkdir()
    for p in origen[:2]:
        shutil.copy(p, config.reportes_dir)
    agente = AgenteAprendizaje(config)
    assert len(agente.reportes.refrescar()) == 2
    shutil.copy(origen[2], config.reportes_dir)
    (config.reportes_dir / "a_medio_escribir.json").write_text('{"report_id": ', encoding="utf-8")
    assert agente.reportes.refrescar() == [origen[2].stem]  # el archivo incompleto se ignora sin romper
    antes = huella(config.reportes_dir)
    agente.ciclo()
    rid = origen[0].stem
    agente.veredictos.registrar(rid, "MALICIOSO", "analista")
    agente.ciclo("veredicto")
    assert huella(config.reportes_dir) == antes
    assert not config.data_dir.is_relative_to(config.reportes_dir)


# ------------------------------------------------------------------ RG-03 / RA2-05
def test_rg_03_cada_ciclo_con_cambios_queda_trazado_y_sin_cambios_no(config):
    agente = AgenteAprendizaje(config)
    agente.ciclo()
    agente.ciclo()  # nada nuevo: no traza
    rid = buscar("bec_suplantacion_interna", "original", "legitimo").id
    agente.veredictos.registrar(rid, "MALICIOSO", "analista")
    agente.ciclo("veredicto")
    trazas = [json.loads(l) for l in (config.data_dir / "trazas" / "ciclos.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [t["motivo"] for t in trazas] == ["consulta", "veredicto"]
    assert trazas[0]["percibido"]["reportes"] == len(ESCENARIOS)
    assert trazas[1]["supervision"]["alertas_nuevas"] == [f"ia_malicioso:{rid}"]


def test_ra2_01_el_hilo_propio_percibe_un_reporte_nuevo_sin_que_nadie_consulte(config, tmp_path):
    """RG-03: la traza dice que el ciclo lo disparó el agente (`autonomo`) y qué reporte percibió.
    Es lo que usa scripts/verificar_e2e.sh para demostrar la percepción autónoma en el despliegue."""
    import time

    origen = sorted(REPORTES_DIR.glob("*.json"))
    config.reportes_dir = tmp_path / "reports"
    config.reportes_dir.mkdir()
    config.intervalo_s = 0.05
    ruta = config.data_dir / "trazas" / "ciclos.jsonl"

    def trazas() -> list[dict]:
        return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines()] if ruta.exists() else []

    with TestClient(crear_app(config)):  # arranca el hilo del agente; no se llama a ningún endpoint
        shutil.copy(origen[0], config.reportes_dir)
        limite = time.monotonic() + 5
        while not any(origen[0].stem in t["percibido"]["nuevos"] for t in trazas()) and time.monotonic() < limite:
            time.sleep(0.05)
    ciclo = next(t for t in trazas() if origen[0].stem in t["percibido"]["nuevos"])
    assert ciclo["motivo"] == "autonomo"


def test_ra2_05_las_meta_alertas_se_registran_una_sola_vez(config):
    rid = buscar("bec_suplantacion_interna", "original", "legitimo").id
    agente = AgenteAprendizaje(config)
    agente.veredictos.registrar(rid, "MALICIOSO", "analista")
    agente.ciclo()
    agente.veredictos.registrar(rid, "MALICIOSO", "otro analista")
    agente.ciclo("veredicto")
    assert [a["clave"] for a in AgenteAprendizaje(config).meta_alertas()] == [f"ia_malicioso:{rid}"]
