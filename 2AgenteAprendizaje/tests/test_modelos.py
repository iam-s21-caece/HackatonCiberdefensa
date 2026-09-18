import ast
from pathlib import Path

from agente_aprendizaje.aprendizaje import proponer_umbrales
from agente_aprendizaje.attack_aporte import agregar_attack, aporte_agente1, capa_navigator, resumen_aporte
from agente_aprendizaje.critico import Costos, evaluar, criticar
from agente_aprendizaje.generador import priorizar
from agente_aprendizaje.puntaje import puntuar
from agente_aprendizaje.supervisor import ParametrosSupervision, supervisar

from .conftest import ESCENARIOS, buscar, reportes_fixture, sintetico, verdades_de

UMBRALES = (30, 65)


# ------------------------------------------------------------------ RA2-09
def test_ra2_09_paridad_del_motor_de_puntaje_con_el_flujo_en_todos_los_reportes():
    reportes = reportes_fixture()
    assert len(reportes) == len(ESCENARIOS)
    for r in reportes:
        p = puntuar(r.datos["hallazgos"], *UMBRALES)
        assert (p.score, sorted(p.reglas_duras), p.veredicto_reglas) == (r.score, sorted(r.reglas_duras), r.veredicto_reglas), r.id


def test_ra2_09_aporte_del_agente1_medido_por_contrafactico():
    resumen = resumen_aporte(reportes_fixture(), UMBRALES)
    integrados = [k for k, v in ESCENARIOS.items() if v["flujo"] == "con_agente1"]
    assert resumen["reportes_con_agente1"] == len(integrados) and resumen["sin_paridad"] == []
    bec = {v["muestra"] for v in ESCENARIOS.values() if v["muestra"].startswith("bec_")}
    # El veredicto de reglas no depende de la IA: cada BEC cambia en sus 3 escenarios de IA, y nada más cambia.
    assert sorted(resumen["reportes_con_cambio"]) == sorted(k for k in integrados if ESCENARIOS[k]["muestra"] in bec)
    assert all(d.endswith("→VERDADERO_POSITIVO") for d in resumen["por_direccion"])


def test_ra2_09_sin_paridad_no_se_afirma_un_contrafactico():
    r = buscar("bec_autenticacion_forjada", "con_agente1", "coincide")
    r.datos["score"] = 55  # el reporte ya no coincide con la réplica del motor
    a = aporte_agente1(r, UMBRALES)
    assert a["paridad"] is False and a["cambio_veredicto"] is False


# ------------------------------------------------------------------ RA2-03
def test_ra2_03_matriz_metricas_y_costo_con_convencion_explicita():
    costos = Costos(falso_negativo=20, falso_positivo=1, escalar=0.2)
    e = evaluar([("VERDADERO_POSITIVO", "MALICIOSO"), ("ESCALAR", "MALICIOSO"), ("FALSO_POSITIVO", "MALICIOSO"),
                 ("VERDADERO_POSITIVO", "LEGITIMO"), ("FALSO_POSITIVO", "LEGITIMO")], costos)
    d = e["deteccion"]
    assert (d["tp"], d["fn"], d["fp"], d["tn"]) == (2, 1, 1, 1)
    assert (e["bloqueo_automatico"]["tp"], e["bloqueo_automatico"]["fn"]) == (1, 2)
    assert e["costo_total"] == 21.2 and e["tasa_escalamiento"] == 0.2


def test_ra2_03_el_critico_mide_lo_que_la_ia_engañada_deja_pasar_con_y_sin_agente1():
    reportes = reportes_fixture()
    verdades = verdades_de(reportes)
    costos = Costos()
    original = [r for r in reportes if ESCENARIOS[r.id]["flujo"] == "original" and ESCENARIOS[r.id]["ia"] == "legitimo"]
    integrado = [r for r in reportes if ESCENARIOS[r.id]["flujo"] == "con_agente1" and ESCENARIOS[r.id]["ia"] == "legitimo"]
    c_orig = criticar(original, verdades, costos)["flujo_final"]
    c_int = criticar(integrado, verdades, costos)["flujo_final"]
    bec = {v["muestra"] for v in ESCENARIOS.values() if v["muestra"].startswith("bec_")}
    assert c_orig["deteccion"]["fn"] == len(bec)  # con la IA engañada, todos los BEC llegan al usuario
    assert c_int["deteccion"]["fn"] == 0
    assert c_int["costo_total"] < c_orig["costo_total"]


# ------------------------------------------------------------------ RA2-04
def test_ra2_04_con_muestra_insuficiente_no_propone():
    reportes = reportes_fixture()[:4]
    c = proponer_umbrales(reportes, verdades_de(reportes), Costos(), UMBRALES, muestra_minima=10)
    assert c["estado"] == "muestra_insuficiente" and "propuesta" not in c


def test_ra2_04_propone_el_par_de_menor_costo_informa_el_rango_y_no_aplica_nada():
    legitimos = [sintetico(f"l{i}", s, "ESCALAR", "ESCALAR") for i, s in enumerate([34, 36, 38, 40, 42])]
    maliciosos = [sintetico(f"m{i}", s, "ESCALAR", "ESCALAR") for i, s in enumerate([48, 52, 55, 58, 60])]
    reportes = legitimos + maliciosos
    verdades = {r.id: "LEGITIMO" for r in legitimos} | {r.id: "MALICIOSO" for r in maliciosos}
    c = proponer_umbrales(reportes, verdades, Costos(), UMBRALES, muestra_minima=10)
    assert c["estado"] == "propuesta"
    p = c["propuesta"]
    assert 42 < p["bloquear"] <= 48 and p["escalar"] > 42  # separa ambas poblaciones sin escalar nada
    assert p["costo_total"] == 0 and c["mejora_costo"] == 2.0  # hoy se escalan los 10 (10 x 0.2)
    assert c["rango_optimo"]["bloquear"][0] <= p["bloquear"] <= c["rango_optimo"]["bloquear"][1]
    assert UMBRALES == (30, 65) and "no se aplica" in c["nota"]


# ------------------------------------------------------------------ RA2-05
def test_ra2_05_dimensiones_de_la_ia_derivadas_del_reporte_real():
    r = buscar("bec_suplantacion_interna", "original", "legitimo")
    assert r.degradacion_ia and r.liberado_por_ia and r.veredicto_final == "FALSO_POSITIVO"
    contenido = buscar("bec_autenticacion_forjada", "con_agente1", "legitimo")
    assert contenido.degradacion_ia and contenido.guardrail_activado and not contenido.liberado_por_ia


def test_ra2_05_alerta_critica_si_la_ia_degrado_un_malicioso_confirmado():
    r = buscar("bec_suplantacion_interna", "original", "legitimo")
    s = supervisar([r], {r.id: "MALICIOSO"}, ParametrosSupervision())
    assert [(a["tipo"], a["severidad"]) for a in s["alertas"]] == [("ia_degrado_un_malicioso", "critica")]
    assert supervisar([r], {}, ParametrosSupervision())["alertas"] == []  # sin verdad no hay acusación


def test_ra2_05_degradacion_en_aumento_respecto_de_la_linea_base_aprendida():
    base = [sintetico(f"b{i}", 40, "ESCALAR", "ESCALAR", ia="ESCALAR", recibido_en=f"2026-09-15T{i:02d}:00:00Z")
            for i in range(24)]
    normal = [sintetico(f"n{i}", 40, "ESCALAR", "ESCALAR", ia="ESCALAR", recibido_en=f"2026-09-16T{i:02d}:00:00Z")
              for i in range(19)] + [sintetico("n19", 40, "ESCALAR", "FALSO_POSITIVO", ia="FALSO_POSITIVO",
                                              recibido_en="2026-09-16T19:00:00Z")]
    ataque = [sintetico(f"a{i}", 40, "ESCALAR", "FALSO_POSITIVO" if i % 2 else "ESCALAR",
                        ia="FALSO_POSITIVO" if i % 2 else "ESCALAR", recibido_en=f"2026-09-16T{i:02d}:30:00Z")
              for i in range(20)]
    p = ParametrosSupervision(ventana=20, minimo=5)
    assert supervisar(base + normal, {}, p)["alertas"] == []
    s = supervisar(base + ataque, {}, p)
    assert s["linea_base"]["origen"] == "aprendida"
    assert [a["tipo"] for a in s["alertas"]] == ["degradacion_ia_en_aumento"]


def test_ra2_05_ia_no_disponible_en_la_mayoria_de_la_ventana():
    caidos = [sintetico(f"c{i}", 40, "ESCALAR", "ESCALAR", ia=None, recibido_en=f"2026-09-16T{i:02d}:00:00Z")
              for i in range(6)]
    assert "ia_no_disponible" in [a["tipo"] for a in supervisar(caidos, {}, ParametrosSupervision())["alertas"]]


# ------------------------------------------------------------------ RA2-06
def test_ra2_06_cola_prioriza_conflictos_explica_motivos_y_excluye_lo_ya_revisado():
    reportes = reportes_fixture()
    liberado = buscar("bec_suplantacion_interna", "original", "legitimo")
    obvio = buscar("interno_legitimo", "original", "coincide")
    revisado = buscar("phishing_reembolso", "original", "coincide")
    cola = priorizar(reportes, {revisado.id: "MALICIOSO"}, UMBRALES)
    ids = [c["report_id"] for c in cola]
    assert revisado.id not in ids and len(cola) == len(ESCENARIOS) - 1
    assert ids.index(liberado.id) < ids.index(obvio.id)
    assert cola[0]["prioridad"] >= 100 and cola[0]["motivos"]
    assert next(c for c in cola if c["report_id"] == obvio.id)["prioridad"] == 1


# ------------------------------------------------------------------ RA2-07
def test_ra2_07_attack_agrega_lo_que_reporto_el_flujo_y_exporta_capa_navigator():
    reportes = reportes_fixture()
    agregado = agregar_attack(reportes)
    del_flujo = {t.split()[0] for r in reportes for t in r.ia.get("mitre_attack") or []}
    assert {t["id"] for t in agregado["tecnicas"]} == del_flujo and del_flujo
    capa = capa_navigator(agregado)
    assert capa["domain"] == "enterprise-attack" and capa["versions"]["layer"] == "4.5"
    assert {t["techniqueID"] for t in capa["techniques"]} == del_flujo
    assert all(t["score"] >= 1 for t in capa["techniques"])


def test_rg_05_el_paquete_no_usa_clientes_http():
    prohibidos = {"requests", "httpx", "urllib", "http", "aiohttp", "socket"}
    for archivo in (Path(__file__).parents[1] / "agente_aprendizaje").glob("*.py"):
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if isinstance(nodo, (ast.Import, ast.ImportFrom)):
                nombres = [a.name for a in nodo.names] if isinstance(nodo, ast.Import) else [nodo.module or ""]
                assert not {n.split(".")[0] for n in nombres} & prohibidos, archivo.name
