"""Ciclo del agente de aprendizaje — RG-03 y orquestación de RA2-01..12.

    percibir (reportes nuevos, veredictos) -> criticar -> aprender (umbrales, confiabilidad de la IA,
    evidencia) -> supervisar al decisor IA -> caracterizar actores -> generar problemas (cola) -> trazar

Sólo traza un ciclo cuando percibió algo nuevo: un ciclo periódico sin cambios no deja ruido.
El motivo distingue quién lo disparó: `autonomo` (el hilo propio del agente, sin que nadie consulte),
`consulta` (una lectura de la API), `veredicto` (un analista) o `inicial`.
Las meta-alertas se registran una sola vez por clave.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .actores import agrupar
from .aprendizaje import evidencia_real, proponer_umbrales
from .attack_aporte import agregar_attack, resumen_aporte
from .config import Config
from .critico import Costos, criticar
from .generador import priorizar
from .percepcion import RegistroVeredictos, RepositorioReportes
from .supervisor import ParametrosSupervision, supervisar

EXPERIMENTO = Path(__file__).resolve().parents[1] / "experimentos" / "resultados" / "curva_aprendizaje.json"


class AgenteAprendizaje:
    def __init__(self, config: Config):
        self.config = config
        self.reportes = RepositorioReportes(config.reportes_dir)
        self.veredictos = RegistroVeredictos(config.veredictos_path)
        self.costos = Costos(config.costo_fn, config.costo_fp, config.costo_escalar)
        self.umbrales = (config.umbral_escalar, config.umbral_bloquear)
        self.parametros = ParametrosSupervision(ventana=config.ventana_supervision, minimo=config.minimo_supervision,
                                                tolerancia_degradacion=config.tolerancia_degradacion)
        self._ruta_alertas = config.data_dir / "meta_alertas.jsonl"
        self._ruta_trazas = config.data_dir / "trazas" / "ciclos.jsonl"
        self._emitidas = self._cargar_claves()
        self._firma: tuple | None = None
        self._estado: dict | None = None
        self._lock = threading.RLock()

    def _cargar_claves(self) -> set[str]:
        if not self._ruta_alertas.exists():
            return set()
        return {json.loads(l)["clave"] for l in self._ruta_alertas.read_text(encoding="utf-8").splitlines() if l.strip()}

    def _append(self, ruta: Path, registro: dict) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")

    def meta_alertas(self) -> list[dict]:
        if not self._ruta_alertas.exists():
            return []
        return [json.loads(l) for l in self._ruta_alertas.read_text(encoding="utf-8").splitlines() if l.strip()]

    @staticmethod
    def experimento() -> dict | None:
        return json.loads(EXPERIMENTO.read_text(encoding="utf-8")) if EXPERIMENTO.exists() else None

    def ciclo(self, motivo: str = "consulta") -> dict:
        with self._lock:
            nuevos = self.reportes.refrescar()
            reportes = self.reportes.todos()
            firma = (len(reportes), self.veredictos.total)
            if self._estado is not None and not nuevos and firma == self._firma:
                return self._estado
            verdades = self.veredictos.ultimos()

            critica = criticar(reportes, verdades, self.costos)
            calibracion = proponer_umbrales(reportes, verdades, self.costos, self.umbrales, self.config.muestra_minima)
            evidencia = evidencia_real(reportes, verdades, self.costos, self.umbrales, self.config.muestra_minima)
            supervision = supervisar(reportes, verdades, self.parametros)
            actores = agrupar(reportes, verdades, set(self.config.dominios_propios))
            ahora = datetime.now(timezone.utc).isoformat()
            nuevas = [a for a in supervision["alertas"] if a["clave"] not in self._emitidas]
            for alerta in nuevas:
                self._append(self._ruta_alertas, {**alerta, "emitida_en": ahora})
                self._emitidas.add(alerta["clave"])
            cola = priorizar(reportes, verdades, self.umbrales)
            aporte = resumen_aporte(reportes, self.umbrales)

            ciclo_id = f"a2-{uuid.uuid4().hex[:10]}"
            confiabilidad = supervision["confiabilidad_degradacion"]
            self._append(self._ruta_trazas, {
                "ciclo_id": ciclo_id, "fecha": ahora, "motivo": motivo, "version": __version__,
                "percibido": {"reportes": len(reportes), "nuevos": nuevos, "veredictos": len(verdades)},
                "critico": {"n_etiquetados": critica["n_etiquetados"],
                            "costo_flujo": critica["flujo_final"]["costo_total"],
                            "costo_solo_reglas": critica["solo_motor_reglas"]["costo_total"],
                            "recall_deteccion": critica["flujo_final"]["deteccion"]["recall"]},
                "aprendizaje": {"umbrales": calibracion["estado"],
                                "propuesta": [calibracion["propuesta"]["escalar"], calibracion["propuesta"]["bloquear"]]
                                if "propuesta" in calibracion else None,
                                "confiabilidad_ia": confiabilidad["estado"],
                                "riesgo_aprendido": confiabilidad["riesgo_aprendido"],
                                "evidencia_real": evidencia["estado"]},
                "supervision": {"alertas_nuevas": [a["clave"] for a in nuevas],
                                "degradacion_ventana": supervision["ventana"]["degradacion"],
                                "margen_usado": supervision["margen_usado"]},
                "actores": {"n": actores["n_actores"], "con_varios_reportes": actores["n_con_varios_reportes"]},
                "cola": [c["report_id"] for c in cola[:10]],
                "aporte_agente1": {k: aporte[k] for k in ("reportes_con_agente1", "cambios_de_veredicto")},
            })
            self._firma = firma
            self._estado = {"ciclo_id": ciclo_id, "generado_en": ahora, "critica": critica,
                            "calibracion": calibracion, "evidencia_aprendizaje": evidencia,
                            "supervision": supervision, "actores": actores, "cola": cola,
                            "aporte_agente1": aporte, "attack": agregar_attack(reportes)}
            return self._estado

    def estado(self) -> dict:
        return self._estado or self.ciclo("inicial")
