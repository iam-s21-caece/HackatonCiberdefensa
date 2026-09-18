from __future__ import annotations

import ipaddress
import re
from dataclasses import asdict, dataclass, field

from .dns_resolver import ErrorDNS, NoExiste, ResolverDNS

CALIFICADOR = {"+": "pass", "-": "fail", "~": "softfail", "?": "neutral"}
RESULTADOS_DEFINITIVOS = {"pass", "fail", "softfail", "neutral", "none", "permerror"}

_MODIFICADOR = re.compile(r"^([a-zA-Z][a-zA-Z0-9_.-]*)=(.*)$")
_MECANISMO = re.compile(r"^([a-zA-Z0-9]+)(.*)$")
_DOMINIO_CIDR = re.compile(r"^(?::([^/]+))?(?:/(\d+))?(?://(\d+))?$")


@dataclass
class ResultadoSPF:
    resultado: str
    dominio: str
    ip: str
    registro: str | None = None
    mecanismo: str | None = None
    consultas: int = 0
    detalle: str = ""
    notas: list[str] = field(default_factory=list)

    @property
    def definitivo(self) -> bool:
        return self.resultado in RESULTADOS_DEFINITIVOS

    def a_dict(self) -> dict:
        return asdict(self)


class _Permerror(Exception):
    pass


class _Temperror(Exception):
    pass


class _NoSoportado(Exception):
    pass


def evaluar_spf(ip: str, dominio: str, resolver: ResolverDNS, limite_consultas: int = 10) -> ResultadoSPF:
    """Evalúa SPF para `ip` enviando en nombre de `dominio`."""
    dominio = (dominio or "").strip().lower().rstrip(".")
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return ResultadoSPF("permerror", dominio, ip, detalle="IP de origen inválida")
    ev = _Evaluador(direccion, resolver, limite_consultas)
    try:
        resultado, mecanismo, registro = ev.check_host(dominio)
        return ResultadoSPF(resultado, dominio, ip, registro, mecanismo, ev.consultas, notas=ev.notas)
    except _Permerror as e:
        return ResultadoSPF("permerror", dominio, ip, ev.registro_raiz, None, ev.consultas, str(e), ev.notas)
    except _Temperror as e:
        return ResultadoSPF("temperror", dominio, ip, ev.registro_raiz, None, ev.consultas, str(e), ev.notas)
    except _NoSoportado as e:
        return ResultadoSPF("no_soportado", dominio, ip, ev.registro_raiz, None, ev.consultas, str(e), ev.notas)


class _Evaluador:
    def __init__(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address, resolver: ResolverDNS, limite: int):
        self.ip = ip
        self.r = resolver
        self.limite = limite
        self.consultas = 0
        self.notas: list[str] = []
        self.registro_raiz: str | None = None

    def _contar(self) -> None:
        self.consultas += 1
        if self.consultas > self.limite:
            raise _Permerror(f"se excedió el límite de {self.limite} consultas DNS")

    def _resolver(self, funcion, nombre: str) -> list[str]:
        try:
            return funcion(nombre)
        except NoExiste:
            return []
        except ErrorDNS as e:
            raise _Temperror(str(e)) from e

    def check_host(self, dominio: str) -> tuple[str, str | None, str | None]:
        if not dominio or "." not in dominio or len(dominio) > 253:
            return "none", None, None
        try:
            txts = self.r.txt(dominio)
        except NoExiste:
            return "none", None, None
        except ErrorDNS as e:
            raise _Temperror(str(e)) from e
        registros = [t for t in txts if re.match(r"^v=spf1(\s|$)", t.strip(), re.IGNORECASE)]
        if not registros:
            return "none", None, None
        if len(registros) > 1:
            raise _Permerror(f"{dominio} publica más de un registro SPF")
        registro = registros[0].strip()
        if self.registro_raiz is None:
            self.registro_raiz = registro

        redirect: str | None = None
        for termino in registro.split()[1:]:
            mod = _MODIFICADOR.match(termino)
            if mod:
                if mod.group(1).lower() == "redirect":
                    if redirect is not None:
                        raise _Permerror("modificador redirect duplicado")
                    redirect = mod.group(2).lower().rstrip(".")
                continue  # exp= y modificadores desconocidos se ignoran (§6)
            calificador = "+"
            if termino[0] in CALIFICADOR:
                calificador, termino = termino[0], termino[1:]
            m = _MECANISMO.match(termino)
            if not m:
                raise _Permerror(f"término inválido: {termino!r}")
            nombre, resto = m.group(1).lower(), m.group(2)
            if "%" in resto:
                raise _NoSoportado(f"macros SPF en '{termino}'")
            if self._coincide(nombre, resto, dominio):
                return CALIFICADOR[calificador], f"{calificador}{nombre}{resto}", registro

        if redirect:
            if "%" in redirect:
                raise _NoSoportado("macros SPF en redirect")
            self._contar()
            resultado, mecanismo, _ = self.check_host(redirect)
            if resultado == "none":
                raise _Permerror(f"redirect a {redirect}, que no publica SPF")
            return resultado, f"redirect={redirect} -> {mecanismo}", registro
        return "neutral", None, registro

    def _coincide(self, nombre: str, resto: str, dominio: str) -> bool:
        if nombre == "all":
            if resto:
                raise _Permerror("'all' no admite argumentos")
            return True
        if nombre in ("ip4", "ip6"):
            if not resto.startswith(":"):
                raise _Permerror(f"{nombre} sin dirección")
            try:
                red = ipaddress.ip_network(resto[1:], strict=False)
            except ValueError as e:
                raise _Permerror(f"{nombre} inválido: {resto[1:]}") from e
            if red.version != (4 if nombre == "ip4" else 6):
                raise _Permerror(f"{nombre} con dirección de otra versión: {resto[1:]}")
            return self.ip.version == red.version and self.ip in red
        if nombre in ("a", "mx"):
            destino, cidr4, cidr6 = self._dominio_y_cidr(resto, dominio)
            self._contar()
            hosts = [destino] if nombre == "a" else self._resolver(self.r.mx, destino)[:10]
            consulta = self.r.a if self.ip.version == 4 else self.r.aaaa
            prefijo = cidr4 if self.ip.version == 4 else cidr6
            for host in hosts:
                for direccion in self._resolver(consulta, host):
                    try:
                        if self.ip in ipaddress.ip_network(f"{direccion}/{prefijo}", strict=False):
                            return True
                    except ValueError:
                        continue
            return False
        if nombre == "include":
            if not resto.startswith(":") or len(resto) < 2:
                raise _Permerror("include sin dominio")
            self._contar()
            resultado, _, _ = self.check_host(resto[1:].lower().rstrip("."))
            if resultado == "pass":
                return True
            if resultado in ("fail", "softfail", "neutral"):
                return False
            raise _Permerror(f"include:{resto[1:]} devolvió {resultado}")
        if nombre == "exists":
            if not resto.startswith(":") or len(resto) < 2:
                raise _Permerror("exists sin dominio")
            self._contar()
            return bool(self._resolver(self.r.a, resto[1:]))
        if nombre == "ptr":
            self._contar()
            self.notas.append("mecanismo ptr no evaluado (RFC 7208 §5.5 lo desaconseja)")
            return False
        raise _Permerror(f"mecanismo desconocido: {nombre}")

    @staticmethod
    def _dominio_y_cidr(resto: str, dominio: str) -> tuple[str, int, int]:
        m = _DOMINIO_CIDR.match(resto)
        if not m:
            raise _Permerror(f"argumento inválido: {resto!r}")
        destino = (m.group(1) or dominio).lower().rstrip(".")
        cidr4 = int(m.group(2)) if m.group(2) else 32
        cidr6 = int(m.group(3)) if m.group(3) else 128
        if cidr4 > 32 or cidr6 > 128:
            raise _Permerror("longitud de prefijo fuera de rango")
        return destino, cidr4, cidr6
