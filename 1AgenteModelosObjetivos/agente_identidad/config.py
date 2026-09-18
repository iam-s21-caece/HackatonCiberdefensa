from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _lista(nombre: str, defecto: str = "") -> list[str]:
    return [x.strip().lower().rstrip(".") for x in os.environ.get(nombre, defecto).split(",") if x.strip()]


@dataclass
class Config:
    dominios_propios: list[str] = field(default_factory=lambda: ["ejercito.mil.ar"])
    mx_confiables: list[str] = field(default_factory=list)
    authserv_confiables: list[str] = field(default_factory=list)
    origenes_confiables: list[str] = field(default_factory=lambda: ["imap"])
    dns_timeout_s: float = 2.0
    dns_servidores: list[str] = field(default_factory=list)
    presupuesto_s: float = 5.0
    max_eml_bytes: int = 10 * 1024 * 1024
    data_dir: Path | None = None
    reportes_dir: Path | None = None
    veredictos_path: Path | None = None
    intervalo_aprendizaje_s: float = 15.0

    @classmethod
    def desde_entorno(cls) -> "Config":
        data_dir = os.environ.get("AGENTE1_DATA_DIR", "./data/agente1")
        reportes = os.environ.get("CENTINELA_REPORTES_DIR")
        veredictos = os.environ.get("AGENTE2_VEREDICTOS_PATH")
        return cls(
            dominios_propios=_lista("DOMINIOS_PROPIOS", "ejercito.mil.ar"),
            mx_confiables=_lista("MX_CONFIABLES"),
            authserv_confiables=_lista("AUTHSERV_CONFIABLES"),
            origenes_confiables=_lista("ORIGENES_CONFIABLES", "imap"),
            dns_timeout_s=float(os.environ.get("DNS_TIMEOUT_S", "2.0")),
            dns_servidores=[s.strip() for s in os.environ.get("DNS_SERVIDORES", "").split(",") if s.strip()],
            presupuesto_s=float(os.environ.get("AGENTE1_PRESUPUESTO_S", "5.0")),
            max_eml_bytes=int(os.environ.get("AGENTE1_MAX_EML_BYTES", str(10 * 1024 * 1024))),
            data_dir=Path(data_dir) if data_dir else None,
            reportes_dir=Path(reportes) if reportes else None,
            veredictos_path=Path(veredictos) if veredictos else None,
            intervalo_aprendizaje_s=float(os.environ.get("AGENTE1_INTERVALO_APRENDIZAJE_S", "15")),
        )
