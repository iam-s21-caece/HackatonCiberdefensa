from __future__ import annotations

from dataclasses import asdict, dataclass

from .dkim_verif import FirmaDKIM
from .dns_resolver import ErrorDNS, NoExiste, ResolverDNS
from .dominios import normalizar, registrable
from .spf import ResultadoSPF


@dataclass
class PoliticaDMARC:
    p: str
    sp: str | None = None
    adkim: str = "r"
    aspf: str = "r"
    pct: int = 100
    registro: str = ""
    dominio_registro: str = ""

    def politica_para(self, dominio_from: str) -> str:
        es_subdominio = normalizar(dominio_from) != normalizar(self.dominio_registro)
        return (self.sp or self.p) if es_subdominio else self.p

    def a_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoDMARC:
    resultado: str  # pass | fail | none | no_evaluable
    politica: str | None
    alineacion_spf: bool
    alineacion_dkim: bool
    detalle: str = ""

    def a_dict(self) -> dict:
        return asdict(self)


def parsear_registro(txt: str, dominio_registro: str = "") -> PoliticaDMARC | None:
    etiquetas: dict[str, str] = {}
    for parte in txt.split(";"):
        if "=" in parte:
            k, v = parte.split("=", 1)
            etiquetas[k.strip().lower()] = v.strip()
    if etiquetas.get("v", "").upper() != "DMARC1":
        return None
    p = etiquetas.get("p", "none").lower()
    if p not in ("none", "quarantine", "reject"):
        p = "none"
    sp = etiquetas.get("sp", "").lower() or None
    try:
        pct = max(0, min(100, int(etiquetas.get("pct", "100"))))
    except ValueError:
        pct = 100
    return PoliticaDMARC(
        p=p,
        sp=sp if sp in ("none", "quarantine", "reject") else None,
        adkim="s" if etiquetas.get("adkim", "r").lower() == "s" else "r",
        aspf="s" if etiquetas.get("aspf", "r").lower() == "s" else "r",
        pct=pct,
        registro=txt,
        dominio_registro=dominio_registro,
    )


def consultar_politica(dominio_from: str, resolver: ResolverDNS) -> tuple[str, PoliticaDMARC | None]:
    """Devuelve ('encontrada' | 'sin_registro' | 'error', política)."""
    dominio_from = normalizar(dominio_from)
    candidatos = [dominio_from]
    organizacional = registrable(dominio_from)
    if organizacional and organizacional != dominio_from:
        candidatos.append(organizacional)
    for dominio in candidatos:
        try:
            txts = resolver.txt(f"_dmarc.{dominio}")
        except NoExiste:
            continue
        except ErrorDNS:
            return "error", None
        registros = [t for t in txts if t.strip().upper().startswith("V=DMARC1")]
        if len(registros) == 1:
            politica = parsear_registro(registros[0], dominio)
            if politica:
                return "encontrada", politica
    return "sin_registro", None


def alineado(dominio_autenticado: str, dominio_from: str, modo: str) -> bool:
    a, b = normalizar(dominio_autenticado), normalizar(dominio_from)
    if not a or not b:
        return False
    return a == b if modo == "s" else registrable(a) == registrable(b)


def evaluar(
    dominio_from: str,
    estado_politica: str,
    politica: PoliticaDMARC | None,
    spf: ResultadoSPF | None,
    firmas_dkim: list[FirmaDKIM] | None,
) -> ResultadoDMARC:
    """`spf=None`: SPF no evaluable. `firmas_dkim=None`: hay firmas que no se pudieron verificar."""
    modo_spf = politica.aspf if politica else "r"
    modo_dkim = politica.adkim if politica else "r"
    al_spf = bool(spf and spf.resultado == "pass" and alineado(spf.dominio, dominio_from, modo_spf))
    al_dkim = any(f.valida is True and alineado(f.dominio, dominio_from, modo_dkim) for f in (firmas_dkim or []))
    nombre_politica = politica.politica_para(dominio_from) if politica else None

    if estado_politica == "error":
        return ResultadoDMARC("no_evaluable", None, al_spf, al_dkim, "falla DNS al consultar la política")
    if al_spf or al_dkim:
        via = " y ".join(v for v, ok in (("SPF", al_spf), ("DKIM", al_dkim)) if ok)
        resultado = "pass" if politica else "none"
        return ResultadoDMARC(resultado, nombre_politica, al_spf, al_dkim, f"{via} pasa alineado con {dominio_from}")
    if politica is None:
        return ResultadoDMARC("none", None, al_spf, al_dkim, f"{dominio_from} no publica DMARC")

    spf_concluyente = spf is not None and spf.definitivo
    dkim_concluyente = firmas_dkim is not None and all(f.valida is not None for f in firmas_dkim)
    if spf_concluyente and dkim_concluyente:
        dkim_txt = f"{len(firmas_dkim)} firma/s sin alineación válida" if firmas_dkim else "el correo no está firmado"
        return ResultadoDMARC(
            "fail", nombre_politica, False, False,
            f"no pasa ni SPF ({spf.resultado} para {spf.dominio}) ni DKIM ({dkim_txt}) alineados con {dominio_from}",
        )
    faltante = []
    if not spf_concluyente:
        faltante.append("SPF")
    if not dkim_concluyente:
        faltante.append("DKIM")
    return ResultadoDMARC("no_evaluable", nombre_politica, False, False,
                          f"sin resultado concluyente de {' ni '.join(faltante)}")
