"""Integración con el workflow real de n8n — RG-04, RA1-01.

Ejecuta el código de los nodos del workflow (original y copia parcheada) con
`herramientas/harness_flujo/harness.mjs`, contra un Agente 1 levantado de verdad por HTTP.
Requiere Node.js. Los analizadores del flujo (crt.sh, RDAP, DNS) consultan la red igual que en n8n;
el Agente 1 usa la zona DNS de prueba para que su resultado sea reproducible.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from agente_identidad.api import crear_app
from agente_identidad.config import Config
from agente_identidad.dns_resolver import ResolverMemoria

from .conftest import zona_base

sys.path.insert(0, str(Path(__file__).parents[1] / "integracion_n8n"))
import parchear_flujo  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
ORIGINAL = RAIZ / "resources" / "centinela.json"
HARNESS = RAIZ / "herramientas" / "harness_flujo" / "harness.mjs"
MUESTRAS = ["bec_autenticacion_forjada", "bec_suplantacion_interna", "interno_legitimo", "phishing_reembolso"]

pytestmark = pytest.mark.integracion
requiere_node = pytest.mark.skipif(shutil.which("node") is None, reason="requiere Node.js para el harness")


def correr(flujo: Path, muestra: str, ia: str, agente_url: str) -> dict:
    salida = subprocess.run(
        ["node", str(HARNESS), "--flujo", str(flujo), "--eml", str(RAIZ / "muestras" / f"{muestra}.eml"),
         "--ia", ia, "--env", f"AGENTE1_URL={agente_url}"],
        capture_output=True, text=True, encoding="utf-8", timeout=120, check=True, cwd=RAIZ,
    )
    return json.loads(salida.stdout)


@pytest.fixture(scope="module")
def flujo_parcheado(tmp_path_factory) -> Path:
    destino = tmp_path_factory.mktemp("flujo") / "centinela_con_agente1.json"
    codigo = (Path(parchear_flujo.__file__).parent / "nodo_agente1.js").read_text(encoding="utf-8")
    destino.write_text(json.dumps(parchear_flujo.parchear(json.loads(ORIGINAL.read_text(encoding="utf-8")), codigo)),
                       encoding="utf-8")
    return destino


@pytest.fixture(scope="module")
def agente_url(tmp_path_factory):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    config = Config(dominios_propios=["ejercito.mil.ar"], origenes_confiables=["imap", "eml_crudo"],
                    data_dir=tmp_path_factory.mktemp("agente1"))
    servidor = uvicorn.Server(uvicorn.Config(crear_app(config, ResolverMemoria(zona_base())),
                                             host="127.0.0.1", port=puerto, log_level="warning"))
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()
    for _ in range(100):
        if servidor.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{puerto}"
    servidor.should_exit = True
    hilo.join(timeout=5)


# ------------------------------------------------------------------ RG-04
@requiere_node
@pytest.mark.parametrize("muestra", MUESTRAS)
@pytest.mark.parametrize("ia", ["coincide", "caida"])
def test_rg_04_con_el_agente_caido_el_flujo_decide_igual_que_el_original(flujo_parcheado, muestra, ia):
    original = correr(ORIGINAL, muestra, ia, "http://127.0.0.1:1")
    parcheado = correr(flujo_parcheado, muestra, ia, "http://127.0.0.1:1")  # puerto sin servicio
    assert parcheado["agente1"]["estado"] == "con_error"
    assert (parcheado["score"], parcheado["veredicto_reglas"], parcheado["veredicto_final"]) == \
           (original["score"], original["veredicto_reglas"], original["veredicto_final"])


# ------------------------------------------------------------------ RA1-01 integrado
@requiere_node
def test_ra1_01_integrado_el_bec_forjado_deja_de_entregarse(flujo_parcheado, agente_url):
    original = correr(ORIGINAL, "bec_autenticacion_forjada", "caida", agente_url)
    assert original["veredicto_final"] == "FALSO_POSITIVO"  # la falla que motivó al agente

    con_agente = correr(flujo_parcheado, "bec_autenticacion_forjada", "caida", agente_url)
    assert con_agente["agente1"]["conclusion"] == "SUPLANTACION_CONFIRMADA"
    assert "interno_autenticado_limpio" not in con_agente["reglas_duras"]
    assert con_agente["veredicto_final"] == "VERDADERO_POSITIVO"

    ia_engañada = correr(flujo_parcheado, "bec_autenticacion_forjada", "legitimo", agente_url)
    assert ia_engañada["veredicto_final"] != "FALSO_POSITIVO"


@requiere_node
def test_ra1_01_integrado_no_altera_el_correo_legitimo_ni_el_phishing_externo(flujo_parcheado, agente_url):
    for muestra in ("interno_legitimo", "phishing_reembolso"):
        original = correr(ORIGINAL, muestra, "coincide", agente_url)
        con_agente = correr(flujo_parcheado, muestra, "coincide", agente_url)
        assert con_agente["veredicto_final"] == original["veredicto_final"]
        assert con_agente["score"] == original["score"]
