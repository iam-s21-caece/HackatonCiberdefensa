import json
import sys
from pathlib import Path

from agente_aprendizaje.actores import agrupar
from agente_aprendizaje.aprendizaje import (curva_aprendizaje, datos_etiquetados, evidencia_real, proponer_umbrales,
                                            tabla_costos)
from agente_aprendizaje.critico import Costos
from agente_aprendizaje.percepcion import ACCION, Reporte
from agente_aprendizaje.puntaje import decidir
from agente_aprendizaje.supervisor import ParametrosSupervision, confiabilidad_degradacion, supervisar

from .conftest import ESCENARIOS, buscar, reportes_fixture, sintetico, verdades_de

sys.path.insert(0, str(Path(__file__).parents[1] / "experimentos"))
import curva_aprendizaje as experimento  # noqa: E402

PROPIOS = {"ejercito.mil.ar", "argentina.gob.ar", "mil.ar"}
MUESTRAS = sorted({v["muestra"] for v in ESCENARIOS.values()})


def una_por_muestra(flujo="con_agente1", ia="coincide") -> dict[str, Reporte]:
    return {m: buscar(m, flujo, ia) for m in MUESTRAS}


# ------------------------------------------------------------------ RA2-10
def test_ra2_10_agrupa_campanas_por_infraestructura_compartida_y_explica_los_vinculos():
    por_muestra = una_por_muestra()
    resultado = agrupar(list(por_muestra.values()), {}, PROPIOS)
    grupos = {frozenset(next(m for m, r in por_muestra.items() if r.id == rid) for rid in a["reportes"]): a
              for a in resultado["actores"]}
    assert set(grupos) == {
        frozenset({"bec_autenticacion_forjada", "bec_suplantacion_interna", "bec_transferencia_campana2"}),
        frozenset({"phishing_reembolso", "phishing_reembolso_campana2"}),
        frozenset({"phishing_m365_credenciales"}),
    }  # el boletín legítimo entregado no es candidato
    reembolso = grupos[frozenset({"phishing_reembolso", "phishing_reembolso_campana2"})]
    vinculos = {(v["tipo"], v["valor"]) for v in reembolso["vinculos"]}
    assert {("reply_to", "reembolsos[.]mp@yandex[.]com"), ("ip_origen", "198[.]51[.]100[.]23"),
            ("dominio", "mercadopago-reembolsos[.]click")} <= vinculos
    assert reembolso["kits_message_id"] == ["srv-01[.]local"] or reembolso["kits_message_id"] == ["srv-01.local"]
    bec = grupos[frozenset({"bec_autenticacion_forjada", "bec_suplantacion_interna", "bec_transferencia_campana2"})]
    assert {v["tipo"] for v in bec["vinculos"]} >= {"ip_origen", "destino_pago"}
    assert bec["conclusiones_agente1"] == {"SUPLANTACION_CONFIRMADA": 3}
    assert resultado["actores"][0]["n_reportes"] == 3  # campañas grandes primero


def test_ra2_10_veredicto_legitimo_excluye_y_el_cbu_nunca_aparece_en_claro():
    por_muestra = una_por_muestra()
    m365 = por_muestra["phishing_m365_credenciales"]
    resultado = agrupar(list(por_muestra.values()), {m365.id: "LEGITIMO"}, PROPIOS)
    assert m365.id not in {rid for a in resultado["actores"] for rid in a["reportes"]}
    texto = json.dumps(resultado)
    assert "0170099220000067797370" not in texto and "0170-0992" not in texto


def test_ra2_10_dominios_propios_y_plataformas_masivas_no_unen_actores_distintos():
    def rep(rid, ip):
        r = sintetico(rid, 70, "VERDADERO_POSITIVO", "VERDADERO_POSITIVO")
        r.datos["correo"]["de"] = {"direccion": f"jefe@ejercito.mil.ar", "dominio": "ejercito.mil.ar"}
        r.datos["artefactos"] = {"ips": [ip], "urls": [{"dominio": "docs.google.com", "es_ip": False}], "hashes": []}
        return r
    resultado = agrupar([rep("x1", "192.0.2.1"), rep("x2", "192.0.2.2")], {}, PROPIOS)
    assert resultado["n_actores"] == 2


# ------------------------------------------------------------------ RA2-11
def test_ra2_11_aprende_que_las_degradaciones_son_riesgosas_y_recomienda_el_guardrail():
    degradados = [sintetico(f"d{i}", 45, "ESCALAR", "FALSO_POSITIVO", ia="FALSO_POSITIVO") for i in range(10)]
    verdades = {r.id: ("MALICIOSO" if i < 6 else "LEGITIMO") for i, r in enumerate(degradados)}
    c = confiabilidad_degradacion(degradados, verdades, ParametrosSupervision())
    assert c["estado"] == "riesgosa" and c["revisadas"] == 10 and c["maliciosas"] == 6
    assert c["ic95"][0] > 0.10 and c["riesgo_aprendido"] == c["ic95"][0]
    assert "guardrail" in c["recomendacion"]
    pocos = confiabilidad_degradacion(degradados[:3], verdades, ParametrosSupervision())
    assert pocos["estado"] == "evidencia_insuficiente" and pocos["riesgo_aprendido"] == 0


def test_ra2_11_lo_aprendido_vuelve_mas_sensible_al_supervisor():
    p = ParametrosSupervision(ventana=20, minimo=5, z=0.0, margen_minimo=0.15)
    base = [sintetico(f"b{i:02d}", 45, "ESCALAR", "FALSO_POSITIVO" if i < 3 else "ESCALAR",
                      ia="FALSO_POSITIVO" if i < 3 else "ESCALAR", recibido_en=f"2026-09-15T10:{i:02d}:00Z")
            for i in range(30)]  # línea base: 10 % de degradación
    ventana = [sintetico(f"v{i:02d}", 45, "ESCALAR", "FALSO_POSITIVO" if i < 4 else "ESCALAR",
                         ia="FALSO_POSITIVO" if i < 4 else "ESCALAR", recibido_en=f"2026-09-16T10:{i:02d}:00Z")
               for i in range(20)]  # ventana: 20 %
    reportes = base + ventana
    sin_aprender = supervisar(reportes, {}, p)
    assert "degradacion_ia_en_aumento" not in [a["tipo"] for a in sin_aprender["alertas"]]  # 20 % <= 10 % + 15 %

    degradados = [r for r in reportes if r.degradacion_ia]
    verdades = {r.id: ("MALICIOSO" if i < 6 else "LEGITIMO") for i, r in enumerate(degradados)}
    aprendido = supervisar(reportes, verdades, p)
    assert aprendido["margen_usado"] < sin_aprender["margen_usado"]
    assert "degradacion_ia_en_aumento" in [a["tipo"] for a in aprendido["alertas"]]


def test_ra2_05_ia_omitida_por_el_flujo_no_cuenta_como_caida():
    omitidos = []
    for i in range(6):
        r = sintetico(f"o{i}", 100, "VERDADERO_POSITIVO", "VERDADERO_POSITIVO", ia=None,
                      recibido_en=f"2026-09-16T{i:02d}:00:00Z", reglas_duras=["adjunto_ejecutable"])
        r.datos["ia"]["omitida"] = True
        omitidos.append(r)
    s = supervisar(omitidos, {}, ParametrosSupervision())
    assert s["global"]["ia_omitida"] == 1 and s["global"]["ia_caida"] == 0
    assert "ia_no_disponible" not in [a["tipo"] for a in s["alertas"]]


# ------------------------------------------------------------------ RA2-04 / RA2-12
def test_ra2_04_tabla_optimizada_equivale_al_recorrido_directo():
    costos = Costos()
    reportes = reportes_fixture()
    datos = datos_etiquetados(reportes, verdades_de(reportes)) + experimento.poblacion(60, semilla=3)
    tabla = tabla_costos(datos, costos)
    for e in range(0, 101, 7):
        for b in range(e, 101, 9):
            directo = sum(costos.de(ACCION[decidir(s, reglas, e, b)], v) for s, reglas, v in datos)
            assert tabla[(e, b)] == round(directo, 6), (e, b)


def test_ra2_12_con_mas_veredictos_el_costo_en_casos_reservados_baja_y_supera_a_los_umbrales_vigentes():
    datos = experimento.poblacion(800, semilla=11)
    curva = {f["n_entrenamiento"]: f for f in
             curva_aprendizaje(datos, Costos(), (30, 65), [10, 160], repeticiones=20, semilla=11)}
    assert curva[160]["costo_reservado_propuesto"] < curva[10]["costo_reservado_propuesto"]
    assert curva[160]["costo_reservado_propuesto"] < curva[160]["costo_reservado_vigente"]
    assert curva[160]["proporcion_no_peor"] >= 0.9
    assert curva[160]["desvio_propuesto"] < curva[10]["desvio_propuesto"]


def test_ra2_12_la_evidencia_real_exige_casos_para_aprender_y_para_medir():
    reportes = reportes_fixture()
    corto = evidencia_real(reportes, verdades_de(reportes), Costos(), (30, 65), muestra_minima=40)
    assert corto["estado"] == "muestra_insuficiente"
    ok = evidencia_real(reportes, verdades_de(reportes), Costos(), (30, 65), muestra_minima=10)
    assert ok["estado"] == "calculada" and ok["curva"]


def test_ra2_04_con_la_muestra_minima_por_defecto_no_propone_sobre_pocos_casos():
    from agente_aprendizaje.config import Config
    minima = Config().muestra_minima
    assert minima == 40
    pocos = reportes_fixture()[:minima - 1]
    assert proponer_umbrales(pocos, verdades_de(pocos), Costos(), (30, 65), minima)["estado"] == "muestra_insuficiente"
    todos = reportes_fixture()
    assert len(todos) >= minima
    assert proponer_umbrales(todos, verdades_de(todos), Costos(), (30, 65), minima)["estado"] != "muestra_insuficiente"
