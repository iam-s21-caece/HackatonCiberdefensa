from fastapi.testclient import TestClient

from agente_identidad import api as api_mod
from agente_identidad.api import crear_app

from .conftest import cargar_parser

CAMPOS_HALLAZGO_FLUJO = {"categoria", "tipo", "valor", "severidad", "peso", "detalle", "fuente"}


def cliente(config, resolver):
    return TestClient(crear_app(config, resolver))


def test_ra1_01_contrato_de_salida_igual_al_de_los_analizadores_del_flujo(config, resolver):
    r = cliente(config, resolver).post("/analizar", json={"parseado": cargar_parser("bec_autenticacion_forjada")})
    assert r.status_code == 200
    cuerpo = r.json()
    # Lo que "Consolidar evidencia y puntuar" lee de cada ítem: fuente, estado, resultados, hallazgos.
    assert cuerpo["fuente"] == "agente_identidad"
    assert cuerpo["estado"] in ("ok", "parcial")
    assert cuerpo["n_hallazgos"] == len(cuerpo["hallazgos"]) > 0
    assert all(set(h) == CAMPOS_HALLAZGO_FLUJO for h in cuerpo["hallazgos"])
    assert all(isinstance(h["peso"], int) for h in cuerpo["hallazgos"])


def test_rg_02_entrada_que_no_cumple_el_contrato_responde_422(config, resolver):
    c = cliente(config, resolver)
    assert c.post("/analizar", json={"parseado": {"correo": {}}}).status_code == 422  # falta report_id
    assert c.post("/analizar", json={"otro": 1}).status_code == 422


def test_rg_04_error_interno_responde_con_error_sin_hallazgos(config, resolver, monkeypatch):
    def romper(self, entrada):
        raise RuntimeError("falla simulada")
    monkeypatch.setattr(api_mod.AgenteIdentidad, "analizar", romper)
    r = cliente(config, resolver).post("/analizar", json={"parseado": cargar_parser("interno_legitimo")})
    assert r.status_code == 200
    assert r.json()["estado"] == "con_error" and r.json()["hallazgos"] == []


def test_rg_03_traza_consultable_por_report_id(config, resolver):
    c = cliente(config, resolver)
    parseado = cargar_parser("bec_suplantacion_interna")
    c.post("/analizar", json={"parseado": parseado})
    traza = c.get(f"/trazas/{parseado['report_id']}")
    assert traza.status_code == 200 and traza.json()["conclusion"] == "SUPLANTACION_CONFIRMADA"
    assert c.get("/trazas/inexistente").status_code == 404


def test_ra1_02_salud_expone_el_modelo_de_la_organizacion(config, resolver):
    cuerpo = cliente(config, resolver).get("/salud").json()
    assert cuerpo["organizacion"]["mx_confiables"] == ["mx4.ejercito.mil.ar"]
    assert cuerpo["organizacion"]["origenes_confiables"] == ["eml_crudo", "imap"]
