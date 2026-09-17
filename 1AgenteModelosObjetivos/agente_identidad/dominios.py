"""Utilidades de dominios y direcciones.

`registrable` replica el algoritmo del flujo n8n (misma lista de sufijos de segundo nivel) para que
el Agente 1 y el flujo coincidan en qué es "el mismo dominio" (RA1-06, RA1-11).
"""

from __future__ import annotations

import re

SLD2 = frozenset({
    "com.ar", "gob.ar", "gov.ar", "mil.ar", "org.ar", "net.ar", "edu.ar", "tur.ar", "int.ar",
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.br", "gov.br", "com.mx", "gob.mx", "com.co", "gov.co",
    "com.pe", "gob.pe", "com.uy", "gub.uy", "com.cl", "gob.cl", "com.au", "co.jp", "co.nz", "com.es",
    "com.ve", "gob.ve", "com.bo", "gob.bo", "com.py", "gov.py", "com.ec", "gob.ec", "co.za", "com.tr",
    "com.cn", "co.in",
})

_EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")


def normalizar(host: str | None) -> str:
    return (host or "").strip().lower().rstrip(".")


def registrable(host: str | None) -> str:
    partes = [p for p in normalizar(host).split(".") if p]
    if len(partes) <= 2:
        return ".".join(partes)
    if ".".join(partes[-2:]) in SLD2:
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])


def dominio_de(direccion: str | None) -> str:
    direccion = normalizar(direccion).strip("<>")
    return direccion.rsplit("@", 1)[1] if "@" in direccion else ""


def direcciones(texto: str | None) -> list[str]:
    vistas: list[str] = []
    for d in _EMAIL.findall(texto or ""):
        d = d.lower()
        if d not in vistas:
            vistas.append(d)
    return vistas


def pertenece(dominio: str | None, padre: str | None) -> bool:
    """True si `dominio` es `padre` o un subdominio suyo."""
    dominio, padre = normalizar(dominio), normalizar(padre)
    return bool(dominio and padre) and (dominio == padre or dominio.endswith("." + padre))


def es_propio(dominio: str | None, propios: set[str] | frozenset[str]) -> bool:
    return any(pertenece(dominio, p) for p in propios)
