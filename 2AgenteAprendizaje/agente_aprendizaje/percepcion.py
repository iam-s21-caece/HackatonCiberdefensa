"""Percepción: reportes del flujo (solo lectura) y veredictos humanos (append-only) — RA2-01, RA2-02.

Los reportes son territorio del flujo: se abren únicamente para lectura. Lo único que escribe este
agente vive en su propio directorio de datos.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .puntaje import RANGO

VEREDICTOS_HUMANOS = ("MALICIOSO", "LEGITIMO")
ACCION = {"VERDADERO_POSITIVO": "bloquear", "ESCALAR": "escalar", "FALSO_POSITIVO": "entregar"}


@dataclass
class Reporte:
    datos: dict

    @property
    def id(self) -> str:
        return self.datos["report_id"]

    @property
    def recibido_en(self) -> str:
        return self.datos.get("recibido_en") or ""

    @property
    def score(self) -> int:
        return int(self.datos.get("score") or 0)

    @property
    def reglas_duras(self) -> list[str]:
        return list(self.datos.get("reglas_duras") or [])

    @property
    def veredicto_reglas(self) -> str:
        return self.datos.get("veredicto_reglas") or "ESCALAR"

    @property
    def veredicto_final(self) -> str:
        return self.datos.get("veredicto_final") or "ESCALAR"

    @property
    def ia(self) -> dict:
        return self.datos.get("ia") or {}

    @property
    def ia_omitida(self) -> bool:
        """El flujo decidió no consultar a la IA (p. ej. ya había una regla dura). No es una caída."""
        return self.ia.get("omitida") is True

    @property
    def ia_veredicto(self) -> str | None:
        return self.ia.get("veredicto") if self.ia.get("disponible") and not self.ia_omitida else None

    @property
    def agente1(self) -> dict:
        return (self.datos.get("fuentes") or {}).get("agente_identidad") or {}

    # --- dimensiones del decisor IA (RA2-05) ---
    @property
    def degradacion_ia(self) -> bool:
        return self.ia_veredicto in RANGO and RANGO[self.ia_veredicto] < RANGO[self.veredicto_reglas]

    @property
    def escalamiento_ia(self) -> bool:
        return self.ia_veredicto in RANGO and RANGO[self.ia_veredicto] > RANGO[self.veredicto_reglas]

    @property
    def guardrail_activado(self) -> bool:
        return self.ia_veredicto is not None and self.veredicto_final != self.ia_veredicto

    @property
    def liberado_por_ia(self) -> bool:
        """La IA llevó a entregar un correo que el motor de reglas no entregaba."""
        return (self.degradacion_ia and self.veredicto_final == "FALSO_POSITIVO"
                and self.veredicto_reglas != "FALSO_POSITIVO")

    def resumen(self) -> dict:
        correo = self.datos.get("correo") or {}
        return {
            "report_id": self.id, "recibido_en": self.recibido_en,
            "remitente": (correo.get("de") or {}).get("direccion"), "asunto": correo.get("asunto"),
            "score": self.score, "nivel": self.datos.get("nivel"), "reglas_duras": self.reglas_duras,
            "veredicto_reglas": self.veredicto_reglas, "veredicto_final": self.veredicto_final,
            "accion": ACCION.get(self.veredicto_final),
            "ia": {"disponible": bool(self.ia.get("disponible")), "omitida": self.ia_omitida,
                   "veredicto": self.ia_veredicto, "confianza": self.ia.get("confianza"),
                   "duracion_ms": self.ia.get("duracion_ms")},
            "degradacion_ia": self.degradacion_ia, "escalamiento_ia": self.escalamiento_ia,
            "guardrail_activado": self.guardrail_activado, "liberado_por_ia": self.liberado_por_ia,
            "agente1": {"estado": self.agente1.get("estado"),
                        "conclusion": (self.agente1.get("resultados") or {}).get("conclusion")} if self.agente1 else None,
            "mitre": list(self.ia.get("mitre_attack") or []),
            "n_hallazgos": self.datos.get("n_hallazgos", len(self.datos.get("hallazgos") or [])),
        }


class RepositorioReportes:
    """Lectura incremental de `data/reports/*.json`: sólo relee lo nuevo o modificado."""

    def __init__(self, directorio: Path):
        self.directorio = directorio
        self._cache: dict[str, tuple[float, Reporte]] = {}
        self._lock = threading.Lock()

    def refrescar(self) -> list[str]:
        nuevos = []
        if not self.directorio.is_dir():
            return nuevos
        with self._lock:
            for archivo in self.directorio.glob("*.json"):
                mtime = archivo.stat().st_mtime
                previo = self._cache.get(archivo.stem)
                if previo and previo[0] == mtime:
                    continue
                try:
                    with archivo.open("r", encoding="utf-8") as f:
                        datos = json.load(f)
                except (OSError, json.JSONDecodeError):
                    continue  # el flujo puede estar escribiéndolo: se reintenta en el próximo ciclo
                if "report_id" not in datos:
                    continue
                if not previo:
                    nuevos.append(archivo.stem)
                self._cache[archivo.stem] = (mtime, Reporte(datos))
        return nuevos

    def todos(self) -> list[Reporte]:
        """Ordenados del más antiguo al más reciente."""
        with self._lock:
            return sorted((r for _, r in self._cache.values()), key=lambda r: (r.recibido_en, r.id))

    def obtener(self, report_id: str) -> Reporte | None:
        with self._lock:
            par = self._cache.get(report_id)
        return par[1] if par else None


class RegistroVeredictos:
    """Veredictos humanos append-only: nunca se reescribe una línea; vale el último por reporte."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self._lock = threading.Lock()
        self._historial: dict[str, list[dict]] = {}
        self._lineas = 0
        if ruta.exists():
            for linea in ruta.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    v = json.loads(linea)
                    self._historial.setdefault(v["report_id"], []).append(v)
                    self._lineas += 1

    def registrar(self, report_id: str, veredicto: str, analista: str, comentario: str = "") -> dict:
        if veredicto not in VEREDICTOS_HUMANOS:
            raise ValueError(f"veredicto inválido: {veredicto}")
        if not analista.strip():
            raise ValueError("el analista es obligatorio")
        with self._lock:
            anterior = self._historial.get(report_id, [])
            entrada = {"report_id": report_id, "veredicto": veredicto, "analista": analista.strip(),
                       "comentario": comentario.strip(), "fecha": datetime.now(timezone.utc).isoformat(),
                       "anterior": anterior[-1]["veredicto"] if anterior else None}
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            with self.ruta.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
            self._historial.setdefault(report_id, []).append(entrada)
            self._lineas += 1
            return entrada

    def historial(self, report_id: str) -> list[dict]:
        with self._lock:
            return list(self._historial.get(report_id, []))

    def ultimos(self) -> dict[str, str]:
        with self._lock:
            return {rid: h[-1]["veredicto"] for rid, h in self._historial.items() if h}

    @property
    def total(self) -> int:
        return self._lineas
