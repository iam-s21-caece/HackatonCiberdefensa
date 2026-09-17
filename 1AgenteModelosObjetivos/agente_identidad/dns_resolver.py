"""Acceso a DNS detrás de un puerto, para poder probar todo sin red.

RG-05: es la ÚNICA salida de red del Agente 1. Ningún dato del correo se envía a servicios externos.

Semántica común a todas las implementaciones:
- dominio inexistente (NXDOMAIN)           -> `NoExiste`
- el nombre existe pero no hay ese tipo     -> lista vacía
- timeout / SERVFAIL / error de red         -> `ErrorDNS` (temporal: nunca se interpreta como "no hay")

RA1-12: la implementación real cachea respuestas (incluidas las negativas) y aplica timeout.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol

import dns.exception
import dns.resolver


class NoExiste(Exception):
    """El nombre consultado no existe (NXDOMAIN)."""


class ErrorDNS(Exception):
    """Falla temporal de resolución: no se puede concluir nada."""


class ResolverDNS(Protocol):
    def txt(self, nombre: str) -> list[str]: ...
    def a(self, nombre: str) -> list[str]: ...
    def aaaa(self, nombre: str) -> list[str]: ...
    def mx(self, nombre: str) -> list[str]: ...


class ResolverReal:
    """Resolver con dnspython, caché con TTL y timeout por consulta (RA1-12)."""

    def __init__(self, timeout_s: float = 2.0, servidores: list[str] | None = None, ttl_cache_s: int = 300):
        self._r = dns.resolver.Resolver(configure=True)
        if servidores:
            self._r.nameservers = servidores
        self._r.lifetime = timeout_s
        self._r.timeout = timeout_s
        self._ttl = ttl_cache_s
        self._cache: dict[tuple[str, str], tuple[float, list[str] | Exception]] = {}
        self._lock = threading.Lock()
        self.consultas_red = 0

    def _consultar(self, nombre: str, tipo: str) -> list[str]:
        clave = (nombre.lower().rstrip("."), tipo)
        ahora = time.monotonic()
        with self._lock:
            en_cache = self._cache.get(clave)
        if en_cache and en_cache[0] > ahora:
            valor = en_cache[1]
            if isinstance(valor, Exception):
                raise valor
            return list(valor)
        self.consultas_red += 1
        try:
            respuesta = self._r.resolve(clave[0], tipo, search=False)
            if tipo == "TXT":
                valores = [b"".join(r.strings).decode("utf-8", "replace") for r in respuesta]
            elif tipo == "MX":
                valores = [str(r.exchange).rstrip(".").lower()
                           for r in sorted(respuesta, key=lambda r: r.preference)]
            else:
                valores = [r.to_text() for r in respuesta]
            guardar: list[str] | Exception = valores
        except dns.resolver.NXDOMAIN:
            guardar = NoExiste(clave[0])
        except dns.resolver.NoAnswer:
            guardar = []
        except (dns.exception.Timeout, dns.resolver.NoNameservers, dns.exception.DNSException) as e:
            raise ErrorDNS(f"{tipo} {clave[0]}: {type(e).__name__}") from e
        with self._lock:
            self._cache[clave] = (ahora + self._ttl, guardar)
        if isinstance(guardar, Exception):
            raise guardar
        return list(guardar)

    def txt(self, nombre: str) -> list[str]:
        return self._consultar(nombre, "TXT")

    def a(self, nombre: str) -> list[str]:
        return self._consultar(nombre, "A")

    def aaaa(self, nombre: str) -> list[str]:
        return self._consultar(nombre, "AAAA")

    def mx(self, nombre: str) -> list[str]:
        return self._consultar(nombre, "MX")


class ResolverMemoria:
    """Zona DNS en memoria para pruebas reproducibles.

    `zona` = {"dominio": {"TXT": [...], "A": [...], "MX": [...]}}. Un nombre ausente es NXDOMAIN;
    un tipo ausente en un nombre presente es respuesta vacía. `fallar` lista nombres que dan ErrorDNS.
    """

    def __init__(self, zona: dict[str, dict[str, list[str]]], fallar: set[str] | None = None):
        self._zona = {k.lower().rstrip("."): v for k, v in zona.items()}
        self._fallar = {f.lower() for f in (fallar or set())}
        self.consultas_red = 0

    def _consultar(self, nombre: str, tipo: str) -> list[str]:
        nombre = nombre.lower().rstrip(".")
        self.consultas_red += 1
        if nombre in self._fallar:
            raise ErrorDNS(f"{tipo} {nombre}: simulado")
        if nombre not in self._zona:
            raise NoExiste(nombre)
        return list(self._zona[nombre].get(tipo, []))

    def txt(self, nombre: str) -> list[str]:
        return self._consultar(nombre, "TXT")

    def a(self, nombre: str) -> list[str]:
        return self._consultar(nombre, "A")

    def aaaa(self, nombre: str) -> list[str]:
        return self._consultar(nombre, "AAAA")

    def mx(self, nombre: str) -> list[str]:
        return self._consultar(nombre, "MX")
