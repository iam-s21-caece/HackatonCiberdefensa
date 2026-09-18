import dkim

from agente_identidad import dmarc
from agente_identidad.dkim_verif import FirmaDKIM, verificar
from agente_identidad.dns_resolver import ResolverMemoria
from agente_identidad.origen import declaraciones_ar, salto_de_origen
from agente_identidad.spf import ResultadoSPF

from .conftest import DKIM_PRIVADA, zona_base

MX = {"mx4.ejercito.mil.ar"}


# ---------------------------------------------------------------- DMARC (RA1-06)
def test_ra1_06_parsea_la_politica_real_de_ejercito(resolver):
    estado, politica = dmarc.consultar_politica("ejercito.mil.ar", resolver)
    assert estado == "encontrada"
    assert (politica.p, politica.adkim, politica.aspf) == ("reject", "s", "s")


def test_ra1_06_subdominio_usa_la_politica_organizacional(resolver):
    estado, politica = dmarc.consultar_politica("tesoreria.ejercito.mil.ar", resolver)
    assert estado == "encontrada" and politica.dominio_registro == "ejercito.mil.ar"


def test_ra1_06_alineacion_estricta_y_relajada():
    assert dmarc.alineado("ejercito.mil.ar", "ejercito.mil.ar", "s")
    assert not dmarc.alineado("correo.ejercito.mil.ar", "ejercito.mil.ar", "s")
    assert dmarc.alineado("correo.ejercito.mil.ar", "ejercito.mil.ar", "r")


def test_ra1_06_fail_exige_spf_y_dkim_concluyentes(resolver):
    _, politica = dmarc.consultar_politica("ejercito.mil.ar", resolver)
    spf_fail = ResultadoSPF("fail", "ejercito.mil.ar", "203.0.113.45")
    assert dmarc.evaluar("ejercito.mil.ar", "encontrada", politica, spf_fail, []).resultado == "fail"
    # Hay firma DKIM que no se pudo verificar (sin crudo): podría ser válida -> no se afirma fail.
    assert dmarc.evaluar("ejercito.mil.ar", "encontrada", politica, spf_fail, None).resultado == "no_evaluable"
    temporal = [FirmaDKIM("ejercito.mil.ar", "s1", None, "DNS temporal")]
    assert dmarc.evaluar("ejercito.mil.ar", "encontrada", politica, spf_fail, temporal).resultado == "no_evaluable"


def test_ra1_06_pass_por_dkim_alineado_aunque_spf_falle(resolver):
    _, politica = dmarc.consultar_politica("ejercito.mil.ar", resolver)
    spf_fail = ResultadoSPF("fail", "ejercito.mil.ar", "203.0.113.45")
    firma = [FirmaDKIM("ejercito.mil.ar", "s1", True)]
    r = dmarc.evaluar("ejercito.mil.ar", "encontrada", politica, spf_fail, firma)
    assert r.resultado == "pass" and r.alineacion_dkim and not r.alineacion_spf


# ---------------------------------------------------------------- origen (RA1-03)
def _salto(raw, ip):
    return {"from": None, "ip": ip, "raw": raw}


def test_ra1_03_toma_el_received_mas_alto_de_un_mx_propio():
    received = [
        _salto("from mail.srv-notif.net (mail.srv-notif.net [203.0.113.45]) by mx4.ejercito.mil.ar with ESMTPS", "203.0.113.45"),
        _salto("from x (x [179.51.212.118]) by mx4.ejercito.mil.ar with ESMTP", "179.51.212.118"),  # forjado debajo
    ]
    o = salto_de_origen(received, MX, "eml_crudo", {"eml_crudo"})
    assert o.confiable and o.ip == "203.0.113.45" and o.indice_received == 0


def test_ra1_03_baja_por_saltos_internos_hasta_el_externo():
    received = [
        _salto("from mx4.ejercito.mil.ar (mx4.ejercito.mil.ar [10.1.1.4]) by buzon.ejercito.mil.ar", "10.1.1.4"),
        _salto("from relay (relay [10.1.1.9]) by mx4.ejercito.mil.ar", "10.1.1.9"),
        _salto("from ext (ext [198.51.100.7]) by mx4.ejercito.mil.ar", "198.51.100.7"),
    ]
    o = salto_de_origen(received, MX | {"buzon.ejercito.mil.ar"}, "imap", {"imap"})
    assert o.confiable and o.ip == "198.51.100.7" and o.indice_received == 2


def test_ra1_03_via_de_entrada_no_habilitada_no_es_confiable():
    received = [_salto("from ext (ext [198.51.100.7]) by mx4.ejercito.mil.ar", "198.51.100.7")]
    o = salto_de_origen(received, MX, "eml_crudo", {"imap"})
    assert not o.confiable and o.ip is None and "no está habilitada" in o.motivo


def test_ra1_03_sin_mx_propio_en_la_cadena_no_hay_origen():
    received = [_salto("from ext (ext [198.51.100.7]) by mx.gmail.com", "198.51.100.7")]
    assert not salto_de_origen(received, MX, "imap", {"imap"}).confiable


def test_ra1_07_authentication_results_marca_authserv_confiable():
    cab = {"authentication-results": ["mx4.ejercito.mil.ar; spf=pass smtp.mailfrom=x; dmarc=pass",
                                      "mx.google.com; dkim=fail header.d=x"]}
    decl = declaraciones_ar(cab, MX)
    assert [(d.authserv_id, d.confiable, d.spf, d.dkim) for d in decl] == [
        ("mx4.ejercito.mil.ar", True, "pass", None), ("mx.google.com", False, None, "fail")]


# ---------------------------------------------------------------- DKIM (RA1-05)
MENSAJE = (b"From: Proveedor <ventas@proveedor.com.ar>\nTo: <compras@ejercito.mil.ar>\n"
           b"Subject: Presupuesto\nDate: Wed, 16 Sep 2026 11:00:00 -0300\nMessage-ID: <p1@proveedor.com.ar>\n\n"
           b"Adjunto presupuesto solicitado.\n")


def firmar(mensaje: bytes = MENSAJE) -> bytes:
    firma = dkim.sign(mensaje, b"sel2026", b"proveedor.com.ar", DKIM_PRIVADA,
                      include_headers=[b"from", b"to", b"subject", b"date", b"message-id"])
    return firma.replace(b"\r\n", b"\n") + mensaje


def test_ra1_05_firma_valida_verifica_criptograficamente(resolver):
    firmas = verificar(firmar(), resolver)
    assert [(f.dominio, f.selector, f.valida) for f in firmas] == [("proveedor.com.ar", "sel2026", True)]


def test_ra1_05_cuerpo_alterado_no_verifica(resolver):
    alterado = firmar().replace(b"presupuesto solicitado", b"presupuesto con nuevo CBU")
    assert verificar(alterado, resolver)[0].valida is False


def test_ra1_05_falla_dns_temporal_no_se_confunde_con_firma_invalida():
    r = ResolverMemoria(zona_base(), fallar={"sel2026._domainkey.proveedor.com.ar"})
    assert verificar(firmar(), r)[0].valida is None


def test_ra1_05_mensaje_sin_firma_devuelve_lista_vacia(resolver):
    assert verificar(MENSAJE, resolver) == []
