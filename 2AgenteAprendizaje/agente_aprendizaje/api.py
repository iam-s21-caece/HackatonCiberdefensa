"""API para la interfaz — RA2-08.

    uvicorn --factory agente_aprendizaje.api:crear_app --host 0.0.0.0 --port 8102

Todo es lectura salvo `POST /api/reportes/{id}/veredicto`, que exige `Authorization: Bearer <token>`.
Sin `AGENTE2_TOKEN` configurado la escritura queda deshabilitada (403): el valor por defecto seguro
es no aceptar veredictos de nadie.

RG-05: el Agente 2 no tiene ninguna salida de red; sólo lee archivos locales y atiende a la interfaz.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .attack_aporte import aporte_agente1, capa_navigator
from .bucle import AgenteAprendizaje
from .config import Config

log = logging.getLogger("agente_aprendizaje")


class NuevoVeredicto(BaseModel):
    veredicto: Literal["MALICIOSO", "LEGITIMO"]
    analista: str = Field(min_length=1, max_length=80)
    comentario: str = Field(default="", max_length=2000)


def _traza_agente1(config: Config, report_id: str) -> dict | None:
    """RG-06: lee las trazas JSONL que escribe el Agente 1, buscando por report_id."""
    directorio = config.agente1_trazas_dir
    if not directorio or not directorio.is_dir():
        return None
    for archivo in sorted(directorio.glob("*.jsonl"), reverse=True):
        for linea in reversed(archivo.read_text(encoding="utf-8").splitlines()):
            if linea.strip() and f'"{report_id}"' in linea:
                registro = json.loads(linea)
                if registro.get("report_id") == report_id:
                    return registro
    return None


def crear_app(config: Config | None = None) -> FastAPI:
    config = config or Config.desde_entorno()
    agente = AgenteAprendizaje(config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        detener = threading.Event()

        def bucle():
            while True:
                try:
                    agente.ciclo("autonomo")
                except Exception:
                    log.exception("ciclo del agente de aprendizaje")
                if detener.wait(config.intervalo_s):
                    return

        threading.Thread(target=bucle, name="agente-aprendizaje", daemon=True).start()
        yield
        detener.set()

    app = FastAPI(title="CENTINELA · Agente 2 · Aprendizaje y supervisión", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origenes, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"])

    def exigir_token(authorization: str = Header(default="")) -> None:
        if not config.token:
            raise HTTPException(403, "escritura deshabilitada: AGENTE2_TOKEN no está configurado")
        esquema, _, valor = authorization.partition(" ")
        if esquema.lower() != "bearer" or not secrets.compare_digest(valor.encode(), config.token.encode()):
            raise HTTPException(401, "token inválido", headers={"WWW-Authenticate": "Bearer"})

    def reporte_o_404(report_id: str):
        agente.reportes.refrescar()
        r = agente.reportes.obtener(report_id)
        if not r:
            raise HTTPException(404, "reporte inexistente")
        return r

    @app.get("/api/salud")
    def salud() -> dict:
        e = agente.estado()
        return {"estado": "ok", "version": __version__, "ciclo_id": e["ciclo_id"], "generado_en": e["generado_en"],
                "reportes": e["critica"]["n_reportes"], "etiquetados": e["critica"]["n_etiquetados"],
                "escritura_habilitada": bool(config.token),
                "umbrales_actuales": {"escalar": config.umbral_escalar, "bloquear": config.umbral_bloquear}}

    @app.get("/api/reportes")
    def reportes(veredicto: str | None = None, limite: int = Query(200, ge=1, le=2000)) -> list[dict]:
        agente.ciclo()
        verdades = agente.veredictos.ultimos()
        filas = [{**r.resumen(), "veredicto_humano": verdades.get(r.id)} for r in reversed(agente.reportes.todos())
                 if not veredicto or r.veredicto_final == veredicto]
        return filas[:limite]

    @app.get("/api/reportes/{report_id}")
    def reporte(report_id: str) -> dict:
        r = reporte_o_404(report_id)
        prioridad = next((c for c in agente.estado()["cola"] if c["report_id"] == report_id), None)
        return {"resumen": r.resumen(), "reporte": r.datos, "veredicto_humano": agente.veredictos.historial(report_id),
                "aporte_agente1": aporte_agente1(r, agente.umbrales), "traza_agente1": _traza_agente1(config, report_id),
                "prioridad": prioridad and {"prioridad": prioridad["prioridad"], "motivos": prioridad["motivos"]}}

    @app.post("/api/reportes/{report_id}/veredicto", dependencies=[Depends(exigir_token)], status_code=201)
    def registrar_veredicto(report_id: str, cuerpo: NuevoVeredicto) -> dict:
        reporte_o_404(report_id)
        entrada = agente.veredictos.registrar(report_id, cuerpo.veredicto, cuerpo.analista, cuerpo.comentario)
        agente.ciclo("veredicto")
        return entrada

    @app.get("/api/cola")
    def cola() -> list[dict]:
        return agente.ciclo()["cola"]

    @app.get("/api/metricas")
    def metricas() -> dict:
        e = agente.ciclo()
        return {"critica": e["critica"], "supervision": e["supervision"]["global"], "aporte_agente1": e["aporte_agente1"]}

    @app.get("/api/calibracion")
    def calibracion() -> dict:
        return agente.ciclo()["calibracion"]

    @app.get("/api/supervision")
    def supervision() -> dict:
        e = agente.ciclo()
        return {**e["supervision"], "meta_alertas": agente.meta_alertas()}

    @app.get("/api/actores")
    def actores() -> dict:
        return agente.ciclo()["actores"]

    @app.get("/api/aprendizaje")
    def aprendizaje() -> dict:
        e = agente.ciclo()
        return {"confiabilidad_degradacion_ia": e["supervision"]["confiabilidad_degradacion"],
                "margen_supervision_usado": e["supervision"]["margen_usado"],
                "evidencia_real": e["evidencia_aprendizaje"],
                "experimento_controlado": agente.experimento()}

    @app.get("/api/attack")
    def attack() -> dict:
        return agente.ciclo()["attack"]

    @app.get("/api/attack/navigator")
    def navigator() -> dict:
        return capa_navigator(agente.ciclo()["attack"])

    return app
