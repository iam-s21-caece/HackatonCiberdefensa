"""Fixtures compartidas.

- `parser_*.json`: salida REAL del nodo "Desarmar correo", generada con
  `herramientas/harness_flujo/harness.mjs` sobre `muestras/*.eml` (ver tests/fixtures/README.md).
- La zona DNS replica los registros públicos reales de ejercito.mil.ar consultados el 2026-09-16
  (SPF `a mx ip4:179.51.212.118 -all`, DMARC `p=reject adkim=s aspf=s`, MX mx4.ejercito.mil.ar).
  Las direcciones A son supuestas: sólo importa que la IP de origen del BEC no esté autorizada.
- La clave DKIM de `fixtures/` es descartable y existe sólo para las pruebas.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agente_identidad.agente import AgenteIdentidad, ModeloOrganizacion
from agente_identidad.config import Config
from agente_identidad.contrato import EntradaAnalisis
from agente_identidad.dns_resolver import ResolverMemoria
from agente_identidad.relaciones import ModeloRelaciones
from agente_identidad.traza import RegistroTrazas

FIXTURES = Path(__file__).parent / "fixtures"
DKIM_PUBLICA = (FIXTURES / "dkim_prueba_publica.b64").read_text().strip()
DKIM_PRIVADA = (FIXTURES / "dkim_prueba_privada.pem").read_bytes()


def zona_base() -> dict:
    return {
        "ejercito.mil.ar": {"TXT": ["v=spf1 a mx ip4:179.51.212.118 -all",
                                    "google-site-verification=GSWNT-DY8ZaZL4SsOuFJiBQefjq900_mF2uScXkkJGc"],
                            "MX": ["mx4.ejercito.mil.ar"], "A": ["179.51.212.120"]},
        "mx4.ejercito.mil.ar": {"A": ["179.51.212.119"]},
        "_dmarc.ejercito.mil.ar": {"TXT": ["v=DMARC1; p=reject; rua=mailto:secsistemas@ejercito.mil.ar; "
                                           "ruf=mailto:secsistemas@ejercito.mil.ar; pct=100; adkim=s; aspf=s"]},
        "proveedor.com.ar": {"TXT": ["v=spf1 ip4:198.51.100.10 -all"], "MX": ["mail.proveedor.com.ar"]},
        "_dmarc.proveedor.com.ar": {"TXT": ["v=DMARC1; p=quarantine"]},
        "sel2026._domainkey.proveedor.com.ar": {"TXT": [f"v=DKIM1; k=rsa; p={DKIM_PUBLICA}"]},
    }


@pytest.fixture
def zona() -> dict:
    return zona_base()


@pytest.fixture
def resolver(zona) -> ResolverMemoria:
    return ResolverMemoria(zona)


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(dominios_propios=["ejercito.mil.ar"], origenes_confiables=["imap", "eml_crudo"],
                  data_dir=tmp_path / "agente1")


def cargar_parser(nombre: str) -> dict:
    return json.loads((FIXTURES / f"parser_{nombre}.json").read_text(encoding="utf-8"))


def entrada(nombre: str, raw: str | None = None) -> EntradaAnalisis:
    return EntradaAnalisis(parseado=cargar_parser(nombre), raw_eml=raw)


@pytest.fixture
def construir_agente(config):
    def _construir(resolver, relaciones: ModeloRelaciones | None = None) -> AgenteIdentidad:
        return AgenteIdentidad(config, resolver, relaciones or ModeloRelaciones(),
                               RegistroTrazas(config.data_dir), ModeloOrganizacion(config, resolver))
    return _construir
