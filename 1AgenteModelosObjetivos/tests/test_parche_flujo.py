"""El parche de integración no modifica el workflow original — RG-01.

Prueba unitaria: no ejecuta el flujo ni usa red. Se saltea si `resources/centinela.json` no está (por
ejemplo, en un clon que excluye esa carpeta).
"""

import difflib
import hashlib
import json
from pathlib import Path

import pytest

import parchear_flujo

RAIZ = Path(__file__).resolve().parents[2]
ORIGINAL = RAIZ / "resources" / "centinela.json"
HASH_ORIGINAL = "881d4551a83ffc6fb480764edba5862e354545c7ab9154314af92885ff83a113"
CODIGO_NODO = (Path(parchear_flujo.__file__).parent / "nodo_agente1.js").read_text(encoding="utf-8")


@pytest.mark.skipif(not ORIGINAL.exists(), reason="resources/centinela.json no está en este checkout")
def test_rg_01_el_parche_no_modifica_el_original_y_es_idempotente():
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() == HASH_ORIGINAL
    original = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    una_vez = parchear_flujo.parchear(original, CODIGO_NODO)
    assert parchear_flujo.parchear(una_vez, CODIGO_NODO) == una_vez
    assert json.loads(ORIGINAL.read_text(encoding="utf-8")) == original  # parchear() trabaja sobre una copia

    nodos = {n["name"]: n for n in una_vez["nodes"]}
    assert len(una_vez["nodes"]) == len(original["nodes"]) + 1
    assert nodos["Unir inteligencia"]["parameters"]["numberInputs"] == 11
    assert nodos[parchear_flujo.NOMBRE]["onError"] == "continueRegularOutput"
    for n in original["nodes"]:  # todo lo demás, idéntico al original
        if n["name"] != "Unir inteligencia":
            assert nodos[n["name"]] == n


# ------------------------------------------------------------------ v2: la integración la hace el generador del flujo
FLUJO_V2 = RAIZ / "workflow" / "centinela_workflow.json"
NODOS_V2 = RAIZ / "workflow" / "nodes"
NOMBRE_V2 = "Agente 1: identidad del remitente"
# Lo único que el flujo agrega al nodo del equipo: dos líneas de autoría y la guarda de canal.
AGREGADO_V2 = {
    "//  Código de Elián (1AgenteModelosObjetivos/integracion_n8n/nodo_agente1.js), sin cambios,",
    "//  salvo la guarda de canal: el agente recalcula SPF/DKIM/DMARC, que sólo existen en correo.",
    "",
    "// WhatsApp / SMS: no hay SPF/DKIM/DMARC que recalcular; la identidad la evalúa el nodo de cabeceras",
}


@pytest.mark.skipif(not FLUJO_V2.exists(), reason="workflow/centinela_workflow.json no está en este checkout")
def test_rg_01_el_flujo_integra_el_nodo_del_agente1_sin_cambios_salvo_la_guarda_de_canal():
    """RG-01 en v2 y RG-04: el nodo del flujo es `nodo_agente1.js` + guarda de canal, el JSON importable está
    sincronizado con las fuentes y el nodo falla abierto."""
    flujo = json.loads(FLUJO_V2.read_text(encoding="utf-8"))
    nodos = {n["name"]: n for n in flujo["nodes"]}
    nodo = nodos[NOMBRE_V2]

    fuente = (NODOS_V2 / "17_agente1.js").read_text(encoding="utf-8")
    comun = (NODOS_V2 / "_common.js").read_text(encoding="utf-8")
    assert nodo["parameters"]["jsCode"] == comun + "\n" + fuente, "centinela_workflow.json desactualizado: python workflow/build_workflow.py"

    guarda = [l for l in fuente.splitlines() if l.startswith("if (d.canal && d.canal !== 'email') return salida(F, 'sin_artefactos'")]
    assert len(guarda) == 1 and "NO_APLICA" in guarda[0]
    cambios = [l for l in difflib.ndiff(CODIGO_NODO.splitlines(), fuente.splitlines()) if l[:2] in ("- ", "+ ")]
    assert not [l for l in cambios if l.startswith("- ")], "el flujo quitó o cambió líneas del nodo del Agente 1"
    assert {l[2:] for l in cambios} <= AGREGADO_V2 | set(guarda)

    assert nodo["onError"] == "continueRegularOutput"
    union = nodos["Unir inteligencia"]
    salidas = flujo["connections"][NOMBRE_V2]["main"][0]
    assert [s["node"] for s in salidas] == ["Unir inteligencia"]
    assert salidas[0]["index"] < union["parameters"]["numberInputs"]
    assert "Agente 1: identidad del remitente" in [s["node"] for s in flujo["connections"]["Desarmar correo"]["main"][0]]
