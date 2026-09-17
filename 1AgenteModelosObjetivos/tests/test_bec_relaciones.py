import json

from agente_identidad.bec import cbu_valido, extraer
from agente_identidad.relaciones import AprendizRelaciones, ModeloRelaciones

from .conftest import cargar_parser


# ---------------------------------------------------------------- BEC (RA1-09)
def test_ra1_09_cbu_digito_verificador():
    assert cbu_valido("0170099220000067797370")
    assert cbu_valido("2850590940090418135201")
    assert cbu_valido("285 0590 9 40090418135201")
    assert not cbu_valido("0170099220000067797371")  # un dígito cambiado
    assert not cbu_valido("12345")


def test_ra1_09_extrae_autoridad_y_pago_del_bec_real():
    c = cargar_parser("bec_suplantacion_interna")["correo"]
    s = extraer(c["from"]["nombre"], c["subject"], c["cuerpo"])
    assert s.se_presenta_como_autoridad and "Cnel. Ricardo" in s.autoridad
    assert s.cbu == ["017…7370"]  # enmascarado: no se replica el dato completo en trazas
    assert s.instruccion_pago and s.transferencia and s.montos == ["$2.850.000"]
    assert {"urgente", "confidencial", "no lo comentes"} <= set(s.urgencia_secreto)


def test_ra1_09_destino_de_pago_se_expone_solo_como_huella_estable():
    c = cargar_parser("bec_suplantacion_interna")["correo"]
    s = extraer(c["from"]["nombre"], c["subject"], c["cuerpo"])
    otra = extraer("", "", "Transferí ya al CBU 0170-0992-2000-0067-7973-70, es urgente")
    assert len(s.destinos_hash) == 1 and s.destinos_hash == otra.destinos_hash  # mismo CBU, otro formato
    assert "0170099220000067797370" not in str(s.a_dict())


def test_ra1_09_boletin_institucional_no_tiene_instruccion_de_pago():
    c = cargar_parser("interno_legitimo")["correo"]
    s = extraer(c["from"]["nombre"], c["subject"], c["cuerpo"])
    assert not s.instruccion_pago


def test_ra1_09_numero_de_22_digitos_invalido_no_es_cbu():
    s = extraer("", "", "Transferí al 0170099220000067797371 hoy")
    assert s.cbu == [] and s.cvu == []


def test_ra1_09_alias_y_cvu():
    s = extraer("", "", "Depositá $150.000 al alias: compras.jefatura.ok o al CVU 0000003100010000000016")
    assert s.alias == ["compras.jefatura.ok"]
    assert s.cvu == ["000…0016"] and s.cbu == []
    assert s.instruccion_pago


# ---------------------------------------------------------------- relaciones (RA1-08)
def reporte(veredicto_final="FALSO_POSITIVO", conclusion="IDENTIDAD_VERIFICADA", report_id="r1"):
    return {"report_id": report_id, "recibido_en": "2026-09-16T08:30:11Z", "veredicto_final": veredicto_final,
            "correo": {"de": {"direccion": "comunicaciones@ejercito.mil.ar"}, "para": "<personal@ejercito.mil.ar>"},
            "fuentes": {"agente_identidad": {"resultados": {"conclusion": conclusion}}}}


def test_ra1_08_veredicto_humano_malicioso_nunca_ensena():
    m = ModeloRelaciones()
    assert m.aprender_de_reporte(reporte(), "MALICIOSO") == "descartado"
    assert m.es_primer_contacto("comunicaciones@ejercito.mil.ar", ["personal@ejercito.mil.ar"])


def test_ra1_08_entregado_sin_identidad_verificada_no_ensena():
    m = ModeloRelaciones()
    assert m.aprender_de_reporte(reporte(conclusion="NO_VERIFICABLE"), None) == "pendiente"
    assert len(m) == 0


def test_ra1_08_entregado_con_identidad_verificada_ensena_y_persiste(tmp_path):
    ruta = tmp_path / "relaciones.json"
    m = ModeloRelaciones(ruta)
    assert m.aprender_de_reporte(reporte(), None) == "aprendido"
    recargado = ModeloRelaciones(ruta)
    assert not recargado.es_primer_contacto("comunicaciones@ejercito.mil.ar", ["personal@ejercito.mil.ar"])


def test_ra1_08_aprendiz_resuelve_un_pendiente_cuando_llega_el_veredicto_humano(tmp_path):
    reportes = tmp_path / "reports"
    reportes.mkdir()
    (reportes / "r1.json").write_text(json.dumps(reporte(conclusion="NO_VERIFICABLE")), encoding="utf-8")
    veredictos = tmp_path / "veredictos.jsonl"
    m = ModeloRelaciones()
    aprendiz = AprendizRelaciones(m, reportes, veredictos, tmp_path / "estado.json")
    assert aprendiz.ciclo() == {"aprendido": 0, "descartado": 0, "pendiente": 1}
    veredictos.write_text(json.dumps({"report_id": "r1", "veredicto": "LEGITIMO"}) + "\n", encoding="utf-8")
    assert aprendiz.ciclo()["aprendido"] == 1
    assert aprendiz.ciclo() == {"aprendido": 0, "descartado": 0, "pendiente": 0}  # ya resuelto, no reprocesa
