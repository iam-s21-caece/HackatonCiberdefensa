from agente_identidad.dns_resolver import ResolverMemoria
from agente_identidad.spf import evaluar_spf


def test_ra1_04_ip_autorizada_por_ip4_da_pass(resolver):
    r = evaluar_spf("179.51.212.118", "ejercito.mil.ar", resolver)
    assert r.resultado == "pass"
    assert r.mecanismo == "+ip4:179.51.212.118"


def test_ra1_04_ip_no_autorizada_con_menos_all_da_fail(resolver):
    r = evaluar_spf("203.0.113.45", "ejercito.mil.ar", resolver)
    assert r.resultado == "fail"
    assert r.mecanismo == "-all"
    assert r.consultas == 2  # a + mx


def test_ra1_04_mecanismos_a_y_mx(resolver):
    assert evaluar_spf("179.51.212.120", "ejercito.mil.ar", resolver).mecanismo == "+a"
    assert evaluar_spf("179.51.212.119", "ejercito.mil.ar", resolver).mecanismo == "+mx"


def test_ra1_04_include_redirect_y_calificadores():
    zona = {
        "org.ar": {"TXT": ["v=spf1 include:_spf.proveedor.net ~all"]},
        "_spf.proveedor.net": {"TXT": ["v=spf1 ip4:192.0.2.0/24 ip6:2001:db8::/32 -all"]},
        "sub.org.ar": {"TXT": ["v=spf1 redirect=org.ar"]},
    }
    r = ResolverMemoria(zona)
    assert evaluar_spf("192.0.2.77", "org.ar", r).resultado == "pass"
    assert evaluar_spf("2001:db8::5", "org.ar", r).resultado == "pass"
    assert evaluar_spf("198.51.100.1", "org.ar", r).resultado == "softfail"
    redir = evaluar_spf("198.51.100.1", "sub.org.ar", r)
    assert redir.resultado == "softfail" and redir.mecanismo.startswith("redirect=org.ar")


def test_ra1_04_limite_de_10_consultas_da_permerror():
    zona = {f"d{i}.ar": {"TXT": [f"v=spf1 include:d{i + 1}.ar -all"]} for i in range(12)}
    zona["d12.ar"] = {"TXT": ["v=spf1 -all"]}
    r = evaluar_spf("192.0.2.1", "d0.ar", ResolverMemoria(zona))
    assert r.resultado == "permerror" and "límite" in r.detalle


def test_ra1_04_dominio_inexistente_da_none(resolver):
    assert evaluar_spf("192.0.2.1", "notificaciones-mercadopago.online", resolver).resultado == "none"


def test_ra1_04_dos_registros_spf_da_permerror():
    r = ResolverMemoria({"doble.ar": {"TXT": ["v=spf1 -all", "v=spf1 +all"]}})
    assert evaluar_spf("192.0.2.1", "doble.ar", r).resultado == "permerror"


def test_ra1_04_macros_se_declaran_no_soportadas():
    r = ResolverMemoria({"macro.ar": {"TXT": ["v=spf1 exists:%{i}._spf.macro.ar -all"]}})
    assert evaluar_spf("192.0.2.1", "macro.ar", r).resultado == "no_soportado"


def test_ra1_12_falla_dns_da_temperror_y_no_un_resultado_definitivo(zona):
    r = evaluar_spf("203.0.113.45", "ejercito.mil.ar", ResolverMemoria(zona, fallar={"ejercito.mil.ar"}))
    assert r.resultado == "temperror"
    assert not r.definitivo
