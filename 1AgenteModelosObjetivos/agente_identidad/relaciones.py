from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from .dominios import direcciones, normalizar


class ModeloRelaciones:
    def __init__(self, ruta: Path | None = None):
        self._ruta = ruta
        self._lock = threading.Lock()
        self._pares: dict[str, dict] = {}
        if ruta and ruta.exists():
            self._pares = json.loads(ruta.read_text(encoding="utf-8")).get("pares", {})

    @staticmethod
    def _clave(remitente: str, destinatario: str) -> str:
        return f"{normalizar(remitente)}|{normalizar(destinatario)}"

    def __len__(self) -> int:
        return len(self._pares)

    def contactos_previos(self, remitente: str, destinatarios: list[str]) -> int:
        with self._lock:
            return sum(self._pares.get(self._clave(remitente, d), {}).get("n", 0) for d in destinatarios)

    def es_primer_contacto(self, remitente: str, destinatarios: list[str]) -> bool:
        return self.contactos_previos(remitente, destinatarios) == 0

    def aprender(self, remitente: str, destinatarios: list[str], cuando: str, evidencia: str) -> None:
        with self._lock:
            for d in destinatarios:
                par = self._pares.setdefault(self._clave(remitente, d), {"primera": cuando, "n": 0})
                par["n"] += 1
                par["ultima"] = cuando
                par["evidencia"] = evidencia
            self._persistir()

    def aprender_de_reporte(self, reporte: dict, veredicto_humano: str | None) -> str:
        """Aplica la regla anti-envenenamiento. Devuelve 'aprendido' | 'descartado' | 'pendiente'."""
        correo = reporte.get("correo") or {}
        remitente = ((correo.get("de") or {}).get("direccion") or "").lower()
        destinatarios = direcciones(correo.get("para"))
        if not remitente or not destinatarios:
            return "descartado"
        cuando = reporte.get("recibido_en") or datetime.now(timezone.utc).isoformat()
        if veredicto_humano == "MALICIOSO":
            return "descartado"
        if veredicto_humano == "LEGITIMO":
            self.aprender(remitente, destinatarios, cuando, "veredicto humano LEGITIMO")
            return "aprendido"
        conclusion = (((reporte.get("fuentes") or {}).get("agente_identidad") or {})
                      .get("resultados") or {}).get("conclusion")
        if reporte.get("veredicto_final") == "FALSO_POSITIVO" and conclusion == "IDENTIDAD_VERIFICADA":
            self.aprender(remitente, destinatarios, cuando, "entregado con identidad verificada")
            return "aprendido"
        return "pendiente"

    def _persistir(self) -> None:
        if not self._ruta:
            return
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._ruta.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pares": self._pares}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._ruta)


class AprendizRelaciones:
    """Recorre los reportes del flujo (solo lectura) y aplica `aprender_de_reporte`.

    RG-06: consume `veredictos.jsonl` tal como lo escribe el Agente 2 (report_id, veredicto).

    Un reporte `pendiente` se reevalúa en cada ciclo: si más tarde llega un veredicto humano, se
    resuelve entonces.
    """

    def __init__(self, modelo: ModeloRelaciones, dir_reportes: Path, ruta_veredictos: Path | None,
                 ruta_estado: Path | None):
        self.modelo = modelo
        self.dir_reportes = dir_reportes
        self.ruta_veredictos = ruta_veredictos
        self.ruta_estado = ruta_estado
        self.resueltos: dict[str, str] = {}
        if ruta_estado and ruta_estado.exists():
            self.resueltos = json.loads(ruta_estado.read_text(encoding="utf-8"))

    def _veredictos(self) -> dict[str, str]:
        ultimos: dict[str, str] = {}
        if self.ruta_veredictos and self.ruta_veredictos.exists():
            for linea in self.ruta_veredictos.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    v = json.loads(linea)
                    ultimos[v["report_id"]] = v["veredicto"]
        return ultimos

    def ciclo(self) -> dict[str, int]:
        cuenta = {"aprendido": 0, "descartado": 0, "pendiente": 0}
        if not self.dir_reportes.is_dir():
            return cuenta
        veredictos = self._veredictos()
        for archivo in sorted(self.dir_reportes.glob("*.json")):
            report_id = archivo.stem
            if report_id in self.resueltos:
                continue
            try:
                reporte = json.loads(archivo.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue  # el flujo puede estar escribiéndolo; se reintenta en el próximo ciclo
            estado = self.modelo.aprender_de_reporte(reporte, veredictos.get(report_id))
            cuenta[estado] += 1
            if estado != "pendiente":
                self.resueltos[report_id] = estado
        if self.ruta_estado:
            self.ruta_estado.parent.mkdir(parents=True, exist_ok=True)
            self.ruta_estado.write_text(json.dumps(self.resueltos), encoding="utf-8")
        return cuenta
