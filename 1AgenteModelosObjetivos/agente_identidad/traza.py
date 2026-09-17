"""Registro auditable de cada análisis — RG-03, RA1-10.

Un archivo JSONL por día (`trazas/AAAA-MM-DD.jsonl`), una línea por análisis con la entrada
resumida, cada paso del bucle orientado a objetivos y la conclusión. Es lo que permite responder
"¿por qué el agente dijo esto?" sin volver a ejecutar nada.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class RegistroTrazas:
    def __init__(self, directorio: Path | None):
        self.directorio = directorio / "trazas" if directorio else None
        self._lock = threading.Lock()

    def registrar(self, registro: dict) -> None:
        if not self.directorio:
            return
        self.directorio.mkdir(parents=True, exist_ok=True)
        archivo = self.directorio / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
        linea = json.dumps(registro, ensure_ascii=False, default=str)
        with self._lock, archivo.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")

    def buscar(self, report_id: str) -> dict | None:
        if not self.directorio or not self.directorio.is_dir():
            return None
        for archivo in sorted(self.directorio.glob("*.jsonl"), reverse=True):
            for linea in reversed(archivo.read_text(encoding="utf-8").splitlines()):
                if linea.strip():
                    registro = json.loads(linea)
                    if registro.get("report_id") == report_id:
                        return registro
        return None
