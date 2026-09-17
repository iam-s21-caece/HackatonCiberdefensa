"""Agente basado en modelos y orientado a objetivos — RA1-02, RA1-10, RA1-12.

Estructura (Russell & Norvig, cap. 2):
- **Modelo del mundo**: `ModeloOrganizacion` (dominios propios, MX de confianza aprendidos por DNS)
  y `ModeloRelaciones` (quién le escribe a quién). Recuerdan lo que un correo aislado no muestra.
- **Estado de creencias**: `Creencias`, lo que el agente sabe de ESTE correo en cada momento.
- **Objetivo**: concluir la identidad del remitente con evidencia verificada y evaluar el patrón BEC.
  `objetivo_cumplido()` es el test de objetivo.
- **Acciones**: cada verificación tiene precondiciones sobre las creencias y un valor de información.
  En cada paso el agente elige, entre las aplicables, la de mayor valor. Las precondiciones podan lo
  que ya no hace falta: si una firma DKIM alineada ya prueba la identidad, no gasta hasta 10
  consultas DNS recalculando SPF.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from . import __version__
from .bec import SenalesBEC, extraer as extraer_bec
from .config import Config
from .contrato import EntradaAnalisis, SalidaAnalizador
from .dkim_verif import FirmaDKIM, verificar as verificar_dkim
from .dmarc import PoliticaDMARC, ResultadoDMARC, alineado, consultar_politica, evaluar as evaluar_dmarc
from .dns_resolver import ErrorDNS, NoExiste, ResolverDNS
from .dominios import direcciones, dominio_de, es_propio, normalizar
from .hallazgos import construir as construir_hallazgos
from .origen import DeclaracionAR, Origen, declaraciones_ar, salto_de_origen
from .relaciones import ModeloRelaciones
from .spf import ResultadoSPF, evaluar_spf
from .traza import RegistroTrazas

CONCLUSIONES = ("IDENTIDAD_VERIFICADA", "SUPLANTACION_CONFIRMADA", "NO_VERIFICABLE")
_ENTRADAS_CON_CABECERAS_COMPLETAS = {"eml_crudo", "imap"}


# --------------------------------------------------------------------------- modelo del mundo
class ModeloOrganizacion:
    """Dominios propios y MX de confianza (RA1-02). Los MX se aprenden del DNS y se refrescan."""

    def __init__(self, config: Config, resolver: ResolverDNS, refresco_s: float = 3600, reintento_s: float = 20):
        self.config = config
        self.resolver = resolver
        self.refresco_s = refresco_s
        self.reintento_s = reintento_s
        self._mx_dns: set[str] = set()
        self._proximo_refresco = 0.0
        self._errores: list[str] = []
        self._lock = threading.Lock()

    def dominios_propios(self, del_flujo: list[str] | None = None) -> set[str]:
        return {normalizar(d) for d in (self.config.dominios_propios + (del_flujo or [])) if d}

    def mx_confiables(self) -> set[str]:
        with self._lock:
            if time.monotonic() >= self._proximo_refresco:
                mx, errores = set(), []
                for dominio in self.dominios_propios():
                    try:
                        mx.update(normalizar(h) for h in self.resolver.mx(dominio))
                    except NoExiste:
                        continue
                    except ErrorDNS as e:
                        errores.append(str(e))
                # Una falla temporal no borra lo ya aprendido, y se reintenta pronto en lugar de
                # quedar una hora sin MX de confianza (con lo que todo sería NO_VERIFICABLE).
                self._mx_dns = (mx | self._mx_dns) if errores else mx
                self._errores = errores
                espera = self.reintento_s if errores else self.refresco_s
                self._proximo_refresco = time.monotonic() + espera
            return self._mx_dns | {normalizar(h) for h in self.config.mx_confiables}

    def authserv_confiables(self) -> set[str]:
        return {normalizar(h) for h in self.config.authserv_confiables} or self.mx_confiables()

    def estado(self) -> dict:
        return {"dominios_propios": sorted(self.dominios_propios()), "mx_confiables": sorted(self.mx_confiables()),
                "authserv_confiables": sorted(self.authserv_confiables()),
                "origenes_confiables": sorted(self.config.origenes_confiables), "errores_dns": self._errores}


class _ResolverAcotado:
    """Cuenta las consultas de UN análisis y corta cuando se agota el presupuesto de tiempo."""

    def __init__(self, base: ResolverDNS, limite: float):
        self._base, self._limite, self.consultas = base, limite, 0

    def _ir(self, metodo: str, nombre: str) -> list[str]:
        if time.monotonic() > self._limite:
            raise ErrorDNS("presupuesto de tiempo del análisis agotado")
        self.consultas += 1
        return getattr(self._base, metodo)(nombre)

    def txt(self, n): return self._ir("txt", n)
    def a(self, n): return self._ir("a", n)
    def aaaa(self, n): return self._ir("aaaa", n)
    def mx(self, n): return self._ir("mx", n)


# --------------------------------------------------------------------------- creencias
@dataclass
class Creencias:
    report_id: str
    origen_entrada: str
    from_dir: str
    from_nombre: str
    from_dom: str
    spf_dom: str
    destinatarios: list[str]
    dominio_propio: bool
    declarada: dict
    declaraciones: list[DeclaracionAR]
    tiene_firma_dkim: bool
    raw: bytes | None
    asunto: str
    cuerpo: str
    received: list[dict]
    origen: Origen | None = None
    estado_politica: str | None = None
    politica: PoliticaDMARC | None = None
    dkim: list[FirmaDKIM] | None = None
    dkim_evaluado: bool = False
    spf: ResultadoSPF | None = None
    spf_evaluado: bool = False
    dmarc: ResultadoDMARC | None = None
    conclusion: str | None = None
    motivo_conclusion: str = ""
    primer_contacto: bool | None = None
    contactos_previos: int = 0
    bec: SenalesBEC | None = None
    degradado: list[str] = field(default_factory=list)


def objetivo_cumplido(c: Creencias) -> bool:
    return c.conclusion is not None and c.bec is not None


@dataclass
class Contexto:
    resolver: _ResolverAcotado
    organizacion: ModeloOrganizacion
    relaciones: ModeloRelaciones


# --------------------------------------------------------------------------- acciones
class Accion:
    nombre = ""
    valor = 0
    proposito = ""

    def aplicable(self, c: Creencias) -> bool:
        raise NotImplementedError

    def ejecutar(self, c: Creencias, ctx: Contexto) -> dict:
        raise NotImplementedError


class IdentificarOrigen(Accion):
    nombre, valor = "identificar_origen", 100
    proposito = "ubicar la IP que entregó el correo a un MX propio (base de todo recálculo SPF)"

    def aplicable(self, c):
        return c.origen is None

    def ejecutar(self, c, ctx):
        c.origen = salto_de_origen(c.received, ctx.organizacion.mx_confiables(), c.origen_entrada,
                                   set(ctx.organizacion.config.origenes_confiables))
        return c.origen.a_dict()


class VerificarDKIM(Accion):
    nombre, valor = "verificar_dkim", 90
    proposito = "prueba criptográfica de identidad, independiente de la ruta de entrada"

    def aplicable(self, c):
        return not c.dkim_evaluado and c.raw is not None and c.tiene_firma_dkim

    def ejecutar(self, c, ctx):
        c.dkim = verificar_dkim(c.raw, ctx.resolver)
        c.dkim_evaluado = True
        if any(f.valida is None for f in c.dkim):
            c.degradado.append("DKIM: falla DNS temporal al obtener la clave pública")
        return {"firmas": [f.a_dict() for f in c.dkim]}


class ConsultarPolitica(Accion):
    nombre, valor = "consultar_politica_dmarc", 80
    proposito = "saber qué exige el dueño del dominio del From y con qué alineación"

    def aplicable(self, c):
        return c.estado_politica is None and bool(c.from_dom)

    def ejecutar(self, c, ctx):
        c.estado_politica, c.politica = consultar_politica(c.from_dom, ctx.resolver)
        if c.estado_politica == "error":
            c.degradado.append("DMARC: falla DNS al consultar la política")
        return {"estado": c.estado_politica, "politica": c.politica.a_dict() if c.politica else None}


def _dkim_ya_prueba_identidad(c: Creencias) -> bool:
    modo = c.politica.adkim if c.politica else "r"
    return any(f.valida is True and alineado(f.dominio, c.from_dom, modo) for f in (c.dkim or []))


class RecalcularSPF(Accion):
    nombre, valor = "recalcular_spf", 70
    proposito = "decidir si la IP de origen está autorizada, sin creerle a la cabecera"

    def aplicable(self, c):
        return (not c.spf_evaluado and c.origen is not None and c.origen.confiable and bool(c.origen.ip)
                and c.estado_politica is not None and not VerificarDKIM().aplicable(c)
                and not _dkim_ya_prueba_identidad(c))

    def ejecutar(self, c, ctx):
        c.spf = evaluar_spf(c.origen.ip, c.spf_dom, ctx.resolver)
        c.spf_evaluado = True
        if not c.spf.definitivo:
            c.degradado.append(f"SPF: {c.spf.resultado} ({c.spf.detalle})")
        return c.spf.a_dict()


class EvaluarDMARC(Accion):
    nombre, valor = "evaluar_dmarc", 60
    proposito = "combinar SPF y DKIM recalculados con la alineación que exige el dominio"

    def aplicable(self, c):
        return (c.dmarc is None and c.estado_politica is not None and c.origen is not None
                and not VerificarDKIM().aplicable(c) and not RecalcularSPF().aplicable(c))

    def ejecutar(self, c, ctx):
        spf = c.spf if c.spf_evaluado else None
        firmas = c.dkim if c.dkim_evaluado else None
        c.dmarc = evaluar_dmarc(c.from_dom, c.estado_politica, c.politica, spf, firmas)
        return c.dmarc.a_dict()


class ConcluirIdentidad(Accion):
    nombre, valor = "concluir_identidad", 50
    proposito = "alcanzar la primera parte del objetivo"

    def aplicable(self, c):
        return c.conclusion is None and (c.dmarc is not None or not c.from_dom)

    def ejecutar(self, c, ctx):
        if not c.from_dom:
            c.conclusion, c.motivo_conclusion = "NO_VERIFICABLE", "el correo no tiene un From con dominio"
        elif c.dmarc.resultado == "pass":
            c.conclusion, c.motivo_conclusion = "IDENTIDAD_VERIFICADA", c.dmarc.detalle
        elif c.dmarc.resultado == "fail":
            c.conclusion, c.motivo_conclusion = "SUPLANTACION_CONFIRMADA", c.dmarc.detalle
        else:
            motivo = c.dmarc.detalle
            if c.origen and not c.origen.confiable:
                motivo += f"; {c.origen.motivo}"
            c.conclusion, c.motivo_conclusion = "NO_VERIFICABLE", motivo
        return {"conclusion": c.conclusion, "motivo": c.motivo_conclusion}


class ConsultarRelacion(Accion):
    nombre, valor = "consultar_relacion", 40
    proposito = "recordar si este remitente ya le escribió a estos destinatarios"

    def aplicable(self, c):
        return c.primer_contacto is None

    def ejecutar(self, c, ctx):
        if not c.from_dir or not c.destinatarios:
            c.primer_contacto = False
            return {"primer_contacto": None, "nota": "sin remitente o destinatarios para consultar"}
        c.contactos_previos = ctx.relaciones.contactos_previos(c.from_dir, c.destinatarios)
        c.primer_contacto = c.contactos_previos == 0
        return {"primer_contacto": c.primer_contacto, "contactos_previos": c.contactos_previos}


class EvaluarBEC(Accion):
    nombre, valor = "evaluar_patron_bec", 30
    proposito = "alcanzar la segunda parte del objetivo: fraude por suplantación de autoridad"

    def aplicable(self, c):
        return c.bec is None and c.conclusion is not None and c.primer_contacto is not None

    def ejecutar(self, c, ctx):
        c.bec = extraer_bec(c.from_nombre, c.asunto, c.cuerpo)
        return c.bec.a_dict()


ACCIONES: list[Accion] = [IdentificarOrigen(), VerificarDKIM(), ConsultarPolitica(), RecalcularSPF(),
                          EvaluarDMARC(), ConcluirIdentidad(), ConsultarRelacion(), EvaluarBEC()]


# --------------------------------------------------------------------------- agente
class AgenteIdentidad:
    def __init__(self, config: Config, resolver: ResolverDNS, relaciones: ModeloRelaciones,
                 trazas: RegistroTrazas, organizacion: ModeloOrganizacion | None = None):
        self.config = config
        self.resolver = resolver
        self.relaciones = relaciones
        self.trazas = trazas
        self.organizacion = organizacion or ModeloOrganizacion(config, resolver)

    def _percibir(self, entrada: EntradaAnalisis, degradado: list[str]) -> Creencias:
        p = entrada.parseado
        correo = p.correo
        from_dir = normalizar(correo.from_.direccion)
        from_dom = normalizar(correo.from_.dominio) or dominio_de(from_dir)
        rp_dom = normalizar(correo.return_path.dominio) or dominio_de(correo.return_path.direccion)
        propios = self.organizacion.dominios_propios(p.config.dominios_propios)

        raw = None
        if entrada.raw_eml:
            datos = entrada.raw_eml.encode("utf-8")
            if len(datos) <= self.config.max_eml_bytes:
                raw = datos
            else:
                degradado.append(f".eml de {len(datos)} bytes supera el máximo: DKIM no verificable")

        tiene_firma = "dkim-signature" in correo.cabeceras
        c = Creencias(
            report_id=p.report_id, origen_entrada=p.origen_entrada, from_dir=from_dir,
            from_nombre=correo.from_.nombre, from_dom=from_dom, spf_dom=rp_dom or from_dom,
            destinatarios=direcciones(correo.to), dominio_propio=es_propio(from_dom, propios),
            declarada=correo.auth.model_dump(exclude={"raw"}),
            declaraciones=declaraciones_ar(correo.cabeceras, self.organizacion.authserv_confiables()),
            tiene_firma_dkim=tiene_firma, raw=raw, asunto=correo.subject, cuerpo=correo.cuerpo,
            received=[s.model_dump(by_alias=True) for s in correo.received], degradado=degradado,
        )
        # Sin firma DKIM en cabeceras completas, DKIM ya está evaluado: no hay nada que verificar.
        if not tiene_firma and (raw is not None or p.origen_entrada in _ENTRADAS_CON_CABECERAS_COMPLETAS):
            c.dkim, c.dkim_evaluado = [], True
        return c

    def analizar(self, entrada: EntradaAnalisis) -> SalidaAnalizador:
        inicio = time.monotonic()
        analisis_id = f"a1-{uuid.uuid4().hex[:12]}"
        degradado: list[str] = []
        c = self._percibir(entrada, degradado)
        ctx = Contexto(_ResolverAcotado(self.resolver, inicio + self.config.presupuesto_s),
                       self.organizacion, self.relaciones)

        pasos = []
        while not objetivo_cumplido(c):
            candidatas = [a for a in ACCIONES if a.aplicable(c)]
            if not candidatas:
                break
            elegida = max(candidatas, key=lambda a: a.valor)
            t, consultas = time.monotonic(), ctx.resolver.consultas
            resultado = elegida.ejecutar(c, ctx)
            pasos.append({
                "n": len(pasos) + 1, "accion": elegida.nombre, "proposito": elegida.proposito,
                "candidatas": [a.nombre for a in candidatas],
                "ms": round((time.monotonic() - t) * 1000, 1),
                "consultas_dns": ctx.resolver.consultas - consultas, "resultado": resultado,
            })

        if c.conclusion is None:
            c.conclusion = "NO_VERIFICABLE"
            c.motivo_conclusion = "no quedaron verificaciones aplicables para concluir"
        hallazgos = construir_hallazgos(c)
        duracion_ms = round((time.monotonic() - inicio) * 1000, 1)
        resultados = {
            "analisis_id": analisis_id,
            "version": __version__,
            "objetivo_cumplido": objetivo_cumplido(c),
            "conclusion": c.conclusion,
            "motivo_conclusion": c.motivo_conclusion,
            "remitente": c.from_dir,
            "dominio_propio": c.dominio_propio,
            "origen": c.origen.a_dict() if c.origen else None,
            "autenticacion_declarada": c.declarada,
            "authentication_results": [d.a_dict() for d in c.declaraciones],
            "spf_recalculado": c.spf.a_dict() if c.spf else None,
            "dkim_verificado": [f.a_dict() for f in c.dkim] if c.dkim_evaluado else None,
            "politica_dmarc": c.politica.a_dict() if c.politica else None,
            "dmarc_recalculado": c.dmarc.a_dict() if c.dmarc else None,
            "relacion": {"primer_contacto": c.primer_contacto, "contactos_previos": c.contactos_previos},
            "bec": c.bec.a_dict() if c.bec else None,
            "degradado": c.degradado,
            "pasos": [{"n": p["n"], "accion": p["accion"], "ms": p["ms"]} for p in pasos],
            "duracion_ms": duracion_ms,
        }
        salida = SalidaAnalizador(
            estado="parcial" if c.degradado else "ok", resultados=resultados,
            hallazgos=hallazgos, n_hallazgos=len(hallazgos), consultas=ctx.resolver.consultas,
        )
        self.trazas.registrar({
            "analisis_id": analisis_id, "report_id": c.report_id, "duracion_ms": duracion_ms,
            "entrada": {"remitente": c.from_dir, "destinatarios": c.destinatarios, "asunto": c.asunto[:160],
                        "origen_entrada": c.origen_entrada, "saltos_received": len(c.received),
                        "eml_crudo": c.raw is not None},
            "pasos": pasos, "conclusion": c.conclusion, "motivo_conclusion": c.motivo_conclusion,
            "estado": salida.estado, "degradado": c.degradado,
            "hallazgos": [{"tipo": h.tipo, "peso": h.peso} for h in hallazgos],
        })
        return salida
