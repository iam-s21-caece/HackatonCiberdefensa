from __future__ import annotations

import json
from pathlib import Path

import pytest

from agente_aprendizaje.config import Config
from agente_aprendizaje.percepcion import Reporte

FIXTURES = Path(__file__).parent / "fixtures"
REPORTES_DIR = FIXTURES / "reports"
ESCENARIOS: dict[str, dict] = json.loads((FIXTURES / "escenarios.json").read_text(encoding="utf-8"))


def reportes_fixture() -> list[Reporte]:
    return sorted((Reporte(json.loads(p.read_text(encoding="utf-8"))) for p in REPORTES_DIR.glob("*.json")),
                  key=lambda r: (r.recibido_en, r.id))


def buscar(muestra: str, flujo: str, ia: str) -> Reporte:
    rid = next(k for k, v in ESCENARIOS.items() if (v["muestra"], v["flujo"], v["ia"]) == (muestra, flujo, ia))
    return next(r for r in reportes_fixture() if r.id == rid)


def verdades_de(reportes: list[Reporte]) -> dict[str, str]:
    return {r.id: ESCENARIOS[r.id]["verdad"] for r in reportes}


def sintetico(rid: str, score: int, veredicto_reglas: str, veredicto_final: str, ia: str | None = None,
              recibido_en: str = "2026-09-16T10:00:00Z", reglas_duras: list[str] | None = None,
              confianza: float = 0.8, mitre: list[str] | None = None) -> Reporte:
    return Reporte({"report_id": rid, "recibido_en": recibido_en, "score": score, "reglas_duras": reglas_duras or [],
                    "veredicto_reglas": veredicto_reglas, "veredicto_final": veredicto_final,
                    "ia": {"disponible": ia is not None, "veredicto": ia, "confianza": confianza,
                           "mitre_attack": mitre or [], "duracion_ms": 1000},
                    "correo": {"de": {"direccion": f"{rid}@x.ar"}, "asunto": rid}, "hallazgos": []})


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(reportes_dir=REPORTES_DIR, data_dir=tmp_path / "agente2", token="secreto-de-prueba",
                  muestra_minima=10, ventana_supervision=20, minimo_supervision=5)
