from __future__ import annotations

import ipaddress
import re
from dataclasses import asdict, dataclass

from .dominios import normalizar

_BY = re.compile(r"\bby\s+([^\s;()\[\]]+)", re.IGNORECASE)
_FROM_HOST = re.compile(r"^\s*from\s+([^\s;()\[\]]+)", re.IGNORECASE)


@dataclass
class Origen:
    ip: str | None
    mx: str | None
    confiable: bool
    motivo: str
    indice_received: int | None = None

    def a_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeclaracionAR:
    authserv_id: str
    spf: str | None
    dkim: str | None
    dmarc: str | None
    confiable: bool

    def a_dict(self) -> dict:
        return asdict(self)


_REDES_NO_PUBLICAS_V4 = [ipaddress.ip_network(r) for r in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/3",
)]


def _ip_publica(ip: str | None) -> bool:
    """Mismo criterio que `esIpPrivada` del flujo n8n, para que ambos vean la misma ruta."""
    try:
        d = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    if d.version == 4:
        return not any(d in red for red in _REDES_NO_PUBLICAS_V4)
    return not (d.is_private or d.is_loopback or d.is_link_local or d.is_multicast)


def salto_de_origen(
    received: list[dict],
    mx_confiables: set[str],
    origen_entrada: str,
    origenes_confiables: set[str],
) -> Origen:
    if origen_entrada not in origenes_confiables:
        return Origen(None, None, False,
                      f"la vía de entrada '{origen_entrada}' no está habilitada como confiable "
                      "(las cabeceras Received pudieron ser escritas por el remitente)")
    if not received:
        return Origen(None, None, False, "el correo no trae cadena Received")

    tope = None
    for i, salto in enumerate(received):
        m = _BY.search(salto.get("raw") or "")
        if m and normalizar(m.group(1)) in mx_confiables:
            tope = i
            break
    if tope is None:
        return Origen(None, None, False,
                      "ningún Received fue agregado por un MX de la organización "
                      f"(MX de confianza: {', '.join(sorted(mx_confiables)) or 'ninguno'})")

    # Bajamos por los saltos internos (IP privada o emisor que también es MX propio) hasta el
    # primer salto que vino de afuera. Debajo de ese punto, todo lo escribió el remitente.
    for i in range(tope, len(received)):
        salto = received[i]
        raw = salto.get("raw") or ""
        by = _BY.search(raw)
        if not by or normalizar(by.group(1)) not in mx_confiables:
            break
        emisor = _FROM_HOST.search(raw)
        interno = (emisor and normalizar(emisor.group(1)) in mx_confiables) or not _ip_publica(salto.get("ip"))
        if interno:
            continue
        return Origen(salto.get("ip"), normalizar(by.group(1)), True,
                      f"IP que entregó el correo a {normalizar(by.group(1))}", i)
    return Origen(None, None, False, "sólo hay saltos internos: no se identificó un origen externo")


def declaraciones_ar(cabeceras: dict[str, list[str]], authserv_confiables: set[str]) -> list[DeclaracionAR]:
    """Cada Authentication-Results del mensaje, en orden, marcando si su authserv-id es nuestro."""
    salida = []
    for valor in cabeceras.get("authentication-results", []):
        authserv = normalizar(valor.split(";", 1)[0].strip().split()[0]) if valor.strip() else ""

        def extraer(metodo: str) -> str | None:
            m = re.search(rf"\b{metodo}=(\w+)", valor, re.IGNORECASE)
            return m.group(1).lower() if m else None

        salida.append(DeclaracionAR(authserv, extraer("spf"), extraer("dkim"), extraer("dmarc"),
                                    authserv in authserv_confiables))
    return salida
