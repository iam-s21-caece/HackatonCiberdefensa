import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from agente_aprendizaje.actores import agrupar, registrable as registrable_a2
from agente_aprendizaje.api import crear_app as crear_app_a2
from agente_aprendizaje.config import Config as ConfigA2
from agente_aprendizaje.percepcion import VEREDICTOS_HUMANOS, RegistroVeredictos, Reporte
from agente_identidad.agente import AgenteIdentidad, ModeloOrganizacion
from agente_identidad.bec import huella_destino
from agente_identidad.config import Config as ConfigA1
from agente_identidad.contrato import EntradaAnalisis
from agente_identidad.dns_resolver import ResolverMemoria
from agente_identidad.dominios import registrable as registrable_a1
from agente_identidad.relaciones import AprendizRelaciones, ModeloRelaciones
from agente_identidad.traza import RegistroTrazas

RAIZ = Path(__file__).resolve().parents[2]
FIX_A1 = RAIZ / "1AgenteModelosObjetivos" / "tests" / "fixtures"
FIX_A2 = RAIZ / "2AgenteAprendizaje" / "tests" / "fixtures"
ESCENARIOS = json.loads((FIX_A2 / "escenarios.json").read_text(encoding="utf-8"))
ZONA = {
    "ejercito.mil.ar": {"TXT": ["v=spf1 a mx ip4:179.51.212.118 -all"], "MX": ["mx4.ejercito.mil.ar"]},
    "mx4.ejercito.mil.ar": {"A": ["179.51.212.119"]},
    "_dmarc.ejercito.mil.ar": {"TXT": ["v=DMARC1; p=reject; adkim=s; aspf=s"]},
}


def reporte_fixture(muestra: str, flujo: str, ia: str) -> dict:
    rid = next(k for k, v in ESCENARIOS.items() if (v["muestra"], v["flujo"], v["ia"]) == (muestra, flujo, ia))
    return json.loads((FIX_A2 / "reports" / f"{rid}.json").read_text(encoding="utf-8"))


def test_rg_06_los_veredictos_que_escribe_el_agente2_los_aprende_el_agente1(tmp_path):
    reportes = tmp_path / "reports"
    reportes.mkdir()
    # Entregado por el flujo original, sin Agente 1: sin veredicto humano no enseña (anti-envenenamiento).
    rep = reporte_fixture("interno_legitimo", "original", "coincide")
    (reportes / f"{rep['report_id']}.json").write_text(json.dumps(rep), encoding="utf-8")
    malicioso = reporte_fixture("bec_suplantacion_interna", "original", "legitimo")
    (reportes / f"{malicioso['report_id']}.json").write_text(json.dumps(malicioso), encoding="utf-8")

    veredictos = RegistroVeredictos(tmp_path / "agente2" / "veredictos.jsonl")  # lo que escribe el Agente 2
    modelo = ModeloRelaciones()
    aprendiz = AprendizRelaciones(modelo, reportes, veredictos.ruta, None)  # lo que lee el Agente 1
    assert aprendiz.ciclo() == {"aprendido": 0, "descartado": 0, "pendiente": 2}

    veredictos.registrar(rep["report_id"], "LEGITIMO", "analista", "boletín verificado")
    veredictos.registrar(malicioso["report_id"], "MALICIOSO", "analista", "BEC")
    assert aprendiz.ciclo() == {"aprendido": 1, "descartado": 1, "pendiente": 0}
    assert not modelo.es_primer_contacto("comunicaciones@ejercito.mil.ar", ["personal@ejercito.mil.ar"])
    assert modelo.es_primer_contacto("ricardo.paz@ejercito.mil.ar", ["tesoreria@ejercito.mil.ar"])
    assert set(VEREDICTOS_HUMANOS) == {"MALICIOSO", "LEGITIMO"}


def test_rg_06_la_traza_del_agente1_aparece_en_el_detalle_del_agente2(tmp_path):
    config_a1 = ConfigA1(dominios_propios=["ejercito.mil.ar"], origenes_confiables=["eml_crudo"],
                         data_dir=tmp_path / "agente1")
    resolver = ResolverMemoria(ZONA)
    agente1 = AgenteIdentidad(config_a1, resolver, ModeloRelaciones(), RegistroTrazas(config_a1.data_dir),
                              ModeloOrganizacion(config_a1, resolver))
    parseado = json.loads((FIX_A1 / "parser_bec_autenticacion_forjada.json").read_text(encoding="utf-8"))
    agente1.analizar(EntradaAnalisis(parseado=parseado))

    reportes = tmp_path / "reports"
    reportes.mkdir()
    rep = reporte_fixture("bec_autenticacion_forjada", "con_agente1", "coincide")
    rep["report_id"] = parseado["report_id"]
    (reportes / f"{rep['report_id']}.json").write_text(json.dumps(rep), encoding="utf-8")

    config_a2 = ConfigA2(reportes_dir=reportes, data_dir=tmp_path / "agente2",
                         agente1_trazas_dir=config_a1.data_dir / "trazas")
    with TestClient(crear_app_a2(config_a2)) as c:
        detalle = c.get(f"/api/reportes/{parseado['report_id']}").json()
    traza = detalle["traza_agente1"]
    assert traza["report_id"] == parseado["report_id"]
    assert traza["conclusion"] == "SUPLANTACION_CONFIRMADA"
    assert [p["accion"] for p in traza["pasos"]][0] == "identificar_origen"


def test_rg_06_los_resultados_del_agente1_en_el_reporte_alimentan_actores_y_aporte():
    reportes = [Reporte(reporte_fixture(m, "con_agente1", "coincide"))
                for m in ("bec_suplantacion_interna", "bec_transferencia_campana2")]
    assert all(r.agente1["resultados"]["conclusion"] == "SUPLANTACION_CONFIRMADA" for r in reportes)
    actores = agrupar(reportes, {}, {"ejercito.mil.ar", "mil.ar"})
    assert actores["n_actores"] == 1  # dos BEC distintos, mismo actor
    vinculos = {(v["tipo"], v["valor"]) for v in actores["actores"][0]["vinculos"]}
    assert ("destino_pago", huella_destino("0170099220000067797370")) in vinculos
    assert ("ip_origen", "203[.]0[.]113[.]45") in vinculos


def test_rg_06_ambos_agentes_coinciden_en_el_dominio_registrable():
    hosts = ["mx4.ejercito.mil.ar", "ejercito.mil.ar", "mail.proveedor.com.ar", "login-m365-ejercito.top",
             "a.b.c.gob.ar", "srv.co.uk", "localhost", "", "MERCADOPAGO-REEMBOLSOS.click."]
    assert [registrable_a1(h) for h in hosts] == [registrable_a2(h) for h in hosts]
