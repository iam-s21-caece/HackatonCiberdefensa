"""Servicio HTTP del Agente 1 — RA1-01, RG-04.

    uvicorn --factory agente_identidad.api:crear_app --host 0.0.0.0 --port 8101

Falla abierta: un error interno responde 200 con `estado: con_error` y sin hallazgos, que para
"Consolidar evidencia y puntuar" equivale a una fuente sin datos. El flujo decide igual que sin
el agente. Una entrada que no cumple el contrato responde 422 (RG-02); el nodo del flujo también la
trata como fuente sin datos.
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from . import __version__
from .agente import AgenteIdentidad, ModeloOrganizacion
from .config import Config
from .contrato import EntradaAnalisis, SalidaAnalizador
from .dns_resolver import ResolverDNS, ResolverReal
from .relaciones import AprendizRelaciones, ModeloRelaciones
from .traza import RegistroTrazas

log = logging.getLogger("agente_identidad")


def crear_app(config: Config | None = None, resolver: ResolverDNS | None = None) -> FastAPI:
    config = config or Config.desde_entorno()
    resolver = resolver or ResolverReal(config.dns_timeout_s, config.dns_servidores or None)
    relaciones = ModeloRelaciones(config.data_dir / "relaciones.json" if config.data_dir else None)
    organizacion = ModeloOrganizacion(config, resolver)
    agente = AgenteIdentidad(config, resolver, relaciones, RegistroTrazas(config.data_dir), organizacion)
    aprendiz = None
    if config.reportes_dir:
        aprendiz = AprendizRelaciones(relaciones, config.reportes_dir, config.veredictos_path,
                                      config.data_dir / "relaciones_estado.json" if config.data_dir else None)
    ultimo_ciclo: dict = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        detener = threading.Event()
        if aprendiz:
            def bucle():
                while not detener.wait(config.intervalo_aprendizaje_s):
                    try:
                        ultimo_ciclo.update(aprendiz.ciclo())
                    except Exception:
                        log.exception("ciclo de aprendizaje de relaciones")
            threading.Thread(target=bucle, name="aprendiz-relaciones", daemon=True).start()
        yield
        detener.set()

    app = FastAPI(title="CENTINELA · Agente 1 · Identidad del remitente", version=__version__, lifespan=lifespan)

    @app.post("/analizar", response_model=SalidaAnalizador)
    def analizar(entrada: EntradaAnalisis) -> SalidaAnalizador:
        try:
            return agente.analizar(entrada)
        except Exception as e:  # RG-04: nunca romper el flujo
            log.exception("análisis %s", entrada.parseado.report_id)
            return SalidaAnalizador(estado="con_error", resultados={}, hallazgos=[], n_hallazgos=0,
                                    nota=f"{type(e).__name__}: {e}")

    @app.get("/salud")
    def salud() -> dict:
        return {"estado": "ok", "version": __version__, "organizacion": organizacion.estado(),
                "relaciones_conocidas": len(relaciones), "aprendizaje_relaciones": bool(aprendiz),
                "ultimo_ciclo_aprendizaje": ultimo_ciclo}

    @app.get("/trazas/{report_id}")
    def traza(report_id: str) -> dict:
        registro = agente.trazas.buscar(report_id)
        if not registro:
            raise HTTPException(404, "sin traza para ese reporte")
        return registro

    return app
