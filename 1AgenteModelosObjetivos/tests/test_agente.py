import ast
import json
from pathlib import Path

from agente_identidad.dns_resolver import ResolverMemoria
from agente_identidad.hallazgos import CATALOGO, TOPES_FLUJO
from agente_identidad.relaciones import ModeloRelaciones

from .conftest import cargar_parser, entrada, zona_base
from .test_dmarc_origen_dkim import firmar


def tipos(salida):
    return {h.tipo for h in salida.hallazgos}


def test_ra1_07_bec_con_autenticacion_forjada_se_detecta_como_suplantacion(construir_agente, resolver):
    s = construir_agente(resolver).analizar(entrada("bec_autenticacion_forjada"))
    assert s.estado == "ok"
    assert s.resultados["conclusion"] == "SUPLANTACION_CONFIRMADA"
    assert {"a1_autenticacion_forjada", "a1_spf_recalculado_fail", "a1_dmarc_recalculado_fail_reject",
            "a1_suplantacion_dominio_propio"} <= tipos(s)
    assert s.resultados["spf_recalculado"]["ip"] == "203.0.113.45"


def test_ra1_09_bec_sin_cabecera_forjada_suplantacion_y_patron_bec_de_primer_contacto(construir_agente, resolver):
    s = construir_agente(resolver).analizar(entrada("bec_suplantacion_interna"))
    assert s.resultados["conclusion"] == "SUPLANTACION_CONFIRMADA"
    assert "a1_autenticacion_forjada" not in tipos(s)  # no había declaración que contradecir
    assert {"a1_suplantacion_dominio_propio", "a1_patron_bec_primer_contacto"} <= tipos(s)


def test_ra1_09_con_relacion_previa_el_patron_bec_no_es_de_primer_contacto(construir_agente, resolver):
    relaciones = ModeloRelaciones()
    relaciones.aprender("ricardo.paz@ejercito.mil.ar", ["tesoreria@ejercito.mil.ar"], "2026-09-01", "prueba")
    s = construir_agente(resolver, relaciones).analizar(entrada("bec_suplantacion_interna"))
    assert "a1_patron_bec" in tipos(s) and "a1_patron_bec_primer_contacto" not in tipos(s)


def test_ra1_11_interno_legitimo_verificado_sin_sumar_puntaje(construir_agente, resolver):
    s = construir_agente(resolver).analizar(entrada("interno_legitimo"))
    assert s.resultados["conclusion"] == "IDENTIDAD_VERIFICADA"
    assert [(h.tipo, h.peso) for h in s.hallazgos] == [("a1_identidad_verificada", 0)]


def test_ra1_11_phishing_externo_no_duplica_lo_que_el_flujo_ya_detecta(construir_agente, resolver):
    s = construir_agente(resolver).analizar(entrada("phishing_reembolso"))
    assert s.resultados["conclusion"] == "NO_VERIFICABLE"
    assert sum(h.peso for h in s.hallazgos) == 0


def test_ra1_11_catalogo_con_prefijo_a1_categorias_del_flujo_y_pesos_dentro_de_topes():
    for tipo, (categoria, _severidad, peso) in CATALOGO.items():
        assert tipo.startswith("a1_")
        assert categoria in TOPES_FLUJO
        assert 0 <= peso <= TOPES_FLUJO[categoria]


def test_ra1_02_mx_de_confianza_se_aprenden_del_dns(construir_agente, resolver):
    agente = construir_agente(resolver)
    assert agente.organizacion.mx_confiables() == {"mx4.ejercito.mil.ar"}


def test_ra1_12_si_el_dns_falla_al_aprender_los_mx_reintenta_pronto_sin_perder_lo_aprendido(config):
    from agente_identidad.agente import ModeloOrganizacion

    class ResolverIntermitente(ResolverMemoria):
        fallar_mx = True

        def mx(self, nombre):
            if self.fallar_mx:
                from agente_identidad.dns_resolver import ErrorDNS
                raise ErrorDNS("timeout simulado")
            return super().mx(nombre)

    r = ResolverIntermitente(zona_base())
    org = ModeloOrganizacion(config, r, refresco_s=3600, reintento_s=0)
    assert org.mx_confiables() == set() and org.estado()["errores_dns"]
    r.fallar_mx = False
    assert org.mx_confiables() == {"mx4.ejercito.mil.ar"}  # reintentó en vez de esperar una hora
    r.fallar_mx = True
    org._proximo_refresco = 0
    assert org.mx_confiables() == {"mx4.ejercito.mil.ar"}  # una falla posterior no borra lo aprendido


def test_ra1_10_bucle_orientado_a_objetivos_trazado(construir_agente, resolver, config):
    s = construir_agente(resolver).analizar(entrada("bec_suplantacion_interna"))
    assert s.resultados["objetivo_cumplido"] is True
    acciones = [p["accion"] for p in s.resultados["pasos"]]
    assert acciones == ["identificar_origen", "consultar_politica_dmarc", "recalcular_spf", "evaluar_dmarc",
                        "concluir_identidad", "consultar_relacion", "evaluar_patron_bec"]
    # RG-03: la traza completa queda en disco con candidatas y resultado de cada paso
    lineas = next((config.data_dir / "trazas").glob("*.jsonl")).read_text(encoding="utf-8").splitlines()
    traza = json.loads(lineas[-1])
    assert traza["report_id"] == cargar_parser("bec_suplantacion_interna")["report_id"]
    assert traza["pasos"][0]["candidatas"][0] == "identificar_origen"
    assert all({"accion", "proposito", "candidatas", "resultado", "ms", "consultas_dns"} <= p.keys()
               for p in traza["pasos"])


def test_ra1_10_una_firma_dkim_alineada_poda_el_recalculo_de_spf(construir_agente, resolver):
    parseado = cargar_parser("interno_legitimo")
    raw = firmar().decode()
    correo = parseado["correo"]
    correo["from"].update(direccion="ventas@proveedor.com.ar", dominio="proveedor.com.ar", nombre="Proveedor")
    correo["return_path"].update(direccion="ventas@proveedor.com.ar", dominio="proveedor.com.ar")
    correo["cabeceras"]["dkim-signature"] = ["v=1; d=proveedor.com.ar; s=sel2026"]
    from agente_identidad.contrato import EntradaAnalisis
    s = construir_agente(resolver).analizar(EntradaAnalisis(parseado=parseado, raw_eml=raw))
    acciones = [p["accion"] for p in s.resultados["pasos"]]
    assert "verificar_dkim" in acciones and "recalcular_spf" not in acciones
    assert s.resultados["conclusion"] == "IDENTIDAD_VERIFICADA"


def test_ra1_05_sin_eml_crudo_una_firma_dkim_nunca_se_da_por_valida(construir_agente, resolver):
    parseado = cargar_parser("bec_autenticacion_forjada")
    parseado["correo"]["cabeceras"]["dkim-signature"] = ["v=1; d=ejercito.mil.ar; s=s1"]
    from agente_identidad.contrato import EntradaAnalisis
    s = construir_agente(resolver).analizar(EntradaAnalisis(parseado=parseado))
    assert s.resultados["dkim_verificado"] is None
    assert s.resultados["conclusion"] == "NO_VERIFICABLE"  # sin crudo no se puede afirmar suplantación


def test_ra1_12_falla_dns_estado_parcial_y_sin_hallazgos_sobre_lo_no_verificado(construir_agente, config):
    resolver = ResolverMemoria(zona_base(), fallar={"_dmarc.ejercito.mil.ar"})
    s = construir_agente(resolver).analizar(entrada("bec_suplantacion_interna"))
    assert s.estado == "parcial"
    assert s.resultados["conclusion"] == "NO_VERIFICABLE"
    assert not tipos(s) & {"a1_suplantacion_dominio_propio", "a1_dmarc_recalculado_fail_reject",
                           "a1_autenticacion_forjada"}


def test_ra1_12_presupuesto_de_tiempo_agotado_degrada_sin_colgar(construir_agente, config, resolver):
    config.presupuesto_s = 0
    s = construir_agente(resolver).analizar(entrada("bec_suplantacion_interna"))
    assert s.estado == "parcial" and s.resultados["conclusion"] == "NO_VERIFICABLE"


def test_ra1_13_la_salida_no_contiene_mapeo_mitre(construir_agente, resolver):
    for nombre in ("bec_autenticacion_forjada", "bec_suplantacion_interna", "interno_legitimo", "phishing_reembolso"):
        texto = construir_agente(resolver).analizar(entrada(nombre)).model_dump_json().lower()
        assert "mitre" not in texto and "t1566" not in texto and "att&ck" not in texto


def test_rg_05_el_paquete_no_usa_clientes_http_solo_dns():
    prohibidos = {"requests", "httpx", "urllib", "http", "aiohttp", "socket"}
    paquete = Path(__file__).parents[1] / "agente_identidad"
    for archivo in paquete.glob("*.py"):
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if isinstance(nodo, (ast.Import, ast.ImportFrom)):
                nombres = [a.name for a in nodo.names] if isinstance(nodo, ast.Import) else [nodo.module or ""]
                assert not {n.split(".")[0] for n in nombres} & prohibidos, f"{archivo.name} importa {nombres}"
