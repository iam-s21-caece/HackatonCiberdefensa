"""Verificación criptográfica de DKIM — RA1-05.

A diferencia del SPF recalculado, DKIM no depende de confiar en la ruta por la que llegó el correo:
la firma sólo la puede producir quien tiene la clave privada del dominio. Por eso es la única
prueba de identidad válida incluso cuando el .eml llega por el webhook.

Requiere el .eml crudo byte a byte: el parser del flujo trunca cabeceras y decodifica el cuerpo,
así que sin crudo el resultado es "no verificable", nunca "pass".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import dkim
from dkim.util import InvalidTagValueList, parse_tag_value

from .dns_resolver import ErrorDNS, NoExiste, ResolverDNS


@dataclass
class FirmaDKIM:
    dominio: str
    selector: str
    valida: bool | None  # None = no se pudo evaluar (falla DNS temporal)
    error: str | None = None

    def a_dict(self) -> dict:
        return asdict(self)


class _DNSTemporal(Exception):
    pass


def verificar(raw: bytes, resolver: ResolverDNS, timeout_s: float = 3.0) -> list[FirmaDKIM]:
    """Verifica cada firma DKIM-Signature del mensaje. Lista vacía = el mensaje no está firmado."""
    try:
        mensaje = dkim.DKIM(raw, timeout=int(max(1, timeout_s)))
    except Exception as e:  # mensaje imposible de parsear
        return [FirmaDKIM("", "", False, f"mensaje no parseable: {e}")]

    def dnsfunc(nombre, timeout=5):
        nombre = nombre.decode() if isinstance(nombre, bytes) else nombre
        try:
            registros = resolver.txt(nombre.rstrip("."))
        except NoExiste:
            return None
        except ErrorDNS as e:
            raise _DNSTemporal(str(e)) from e
        dkim_txt = [r for r in registros if "p=" in r]
        return (dkim_txt[0] if dkim_txt else (registros[0] if registros else "")).encode()

    firmas: list[FirmaDKIM] = []
    indices = [i for i, (k, _) in enumerate(mensaje.headers) if k.lower() == b"dkim-signature"]
    for idx, pos in enumerate(indices):
        dominio, selector = _dominio_selector(mensaje.headers[pos][1])
        try:
            valida = bool(mensaje.verify(idx=idx, dnsfunc=dnsfunc))
            firmas.append(FirmaDKIM(dominio, selector, valida, None if valida else "firma no verifica"))
        except _DNSTemporal as e:
            firmas.append(FirmaDKIM(dominio, selector, None, f"DNS temporal: {e}"))
        except dkim.DKIMException as e:
            firmas.append(FirmaDKIM(dominio, selector, False, str(e)))
        except Exception as e:  # dkimpy puede envolver la excepción del dnsfunc
            if isinstance(e.__cause__, _DNSTemporal) or "_DNSTemporal" in repr(e):
                firmas.append(FirmaDKIM(dominio, selector, None, f"DNS temporal: {e}"))
            else:
                firmas.append(FirmaDKIM(dominio, selector, False, f"{type(e).__name__}: {e}"))
    return firmas


def _dominio_selector(valor: bytes) -> tuple[str, str]:
    try:
        tags = parse_tag_value(b"".join(valor.split()))
        return tags.get(b"d", b"").decode().lower(), tags.get(b"s", b"").decode()
    except (InvalidTagValueList, UnicodeDecodeError):
        return "", ""
