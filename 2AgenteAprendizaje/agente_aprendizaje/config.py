"""Configuración por variables de entorno (RNF-03). Ver `.env.example`."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    reportes_dir: Path = Path("./data/reports")
    data_dir: Path = Path("./data/agente2")
    token: str = ""
    agente1_trazas_dir: Path | None = None
    costo_fn: float = 20.0
    costo_fp: float = 1.0
    costo_escalar: float = 0.2
    umbral_escalar: int = 30
    umbral_bloquear: int = 65
    muestra_minima: int = 40
    ventana_supervision: int = 20
    minimo_supervision: int = 5
    intervalo_s: float = 10.0
    cors_origenes: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    dominios_propios: list[str] = field(default_factory=lambda: ["ejercito.mil.ar", "argentina.gob.ar", "mil.ar"])
    tolerancia_degradacion: float = 0.10

    @property
    def veredictos_path(self) -> Path:
        return self.data_dir / "veredictos.jsonl"

    @classmethod
    def desde_entorno(cls) -> "Config":
        e = os.environ.get
        trazas_a1 = e("AGENTE1_TRAZAS_DIR")
        return cls(
            reportes_dir=Path(e("CENTINELA_REPORTES_DIR", "./data/reports")),
            data_dir=Path(e("AGENTE2_DATA_DIR", "./data/agente2")),
            token=e("AGENTE2_TOKEN", ""),
            agente1_trazas_dir=Path(trazas_a1) if trazas_a1 else None,
            costo_fn=float(e("COSTO_FALSO_NEGATIVO", "20")),
            costo_fp=float(e("COSTO_FALSO_POSITIVO", "1")),
            costo_escalar=float(e("COSTO_ESCALAR", "0.2")),
            umbral_escalar=int(e("UMBRAL_ESCALAR", "30")),
            umbral_bloquear=int(e("UMBRAL_BLOQUEAR", "65")),
            muestra_minima=int(e("MUESTRA_MINIMA", "40")),
            ventana_supervision=int(e("SUPERVISION_VENTANA", "20")),
            minimo_supervision=int(e("SUPERVISION_MINIMO", "5")),
            intervalo_s=float(e("AGENTE2_INTERVALO_S", "10")),
            cors_origenes=[o.strip() for o in e("CORS_ORIGENES", "http://localhost:5173").split(",") if o.strip()],
            dominios_propios=[d.strip().lower() for d in
                              e("DOMINIOS_PROPIOS", "ejercito.mil.ar,argentina.gob.ar,mil.ar").split(",") if d.strip()],
            tolerancia_degradacion=float(e("TOLERANCIA_DEGRADACION_IA", "0.10")),
        )
