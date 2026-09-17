"""Genera una COPIA del workflow de CENTINELA con el Agente 1 integrado — RG-01, RA1-01.

    python parchear_flujo.py [--origen ../../resources/centinela.json] [--destino centinela_con_agente1.json]

Cambios, y ninguno más:
1. Nodo Code "Agente 1: identidad del remitente" = bloque de utilidades compartidas del flujo
   (copiado de un analizador existente) + `nodo_agente1.js`, con `onError: continueRegularOutput`.
2. "Desarmar correo" -> nuevo nodo -> entrada 11 de "Unir inteligencia".
3. "Unir inteligencia": `numberInputs` 10 -> 11.

El archivo de origen se abre en solo lectura y se verifica que su hash no cambie. Es idempotente:
aplicarlo sobre una copia ya parcheada produce el mismo resultado.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import uuid
from pathlib import Path

AQUI = Path(__file__).resolve().parent
NOMBRE = "Agente 1: identidad del remitente"
ORIGEN_ANALIZADORES = "Desarmar correo"
MERGE = "Unir inteligencia"
ANALIZADOR_MODELO = "Cabeceras y autenticación (SPF/DKIM/DMARC)"


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def prelude(codigo: str) -> str:
    """Bloque de utilidades compartidas que build_workflow.py inyecta al inicio de cada nodo."""
    i = codigo.find("//  NODO:")
    if i < 0:
        raise ValueError("no se encontró el encabezado '//  NODO:' en el analizador modelo")
    return codigo[: codigo.rfind("// =====", 0, i)]


def parchear(flujo: dict, codigo_nodo: str) -> dict:
    flujo = copy.deepcopy(flujo)
    nodos = {n["name"]: n for n in flujo["nodes"]}
    modelo = nodos[ANALIZADOR_MODELO]

    flujo["nodes"] = [n for n in flujo["nodes"] if n["name"] != NOMBRE]
    flujo["nodes"].append({
        "parameters": {"jsCode": prelude(modelo["parameters"]["jsCode"]) + codigo_nodo},
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "centinela/agente1")),
        "name": NOMBRE,
        "type": modelo["type"],
        "typeVersion": modelo["typeVersion"],
        "position": [modelo["position"][0], max(n["position"][1] for n in flujo["nodes"]) + 176],
        "onError": "continueRegularOutput",
    })

    salidas = flujo["connections"][ORIGEN_ANALIZADORES]["main"][0]
    salidas[:] = [c for c in salidas if c["node"] != NOMBRE] + [{"node": NOMBRE, "type": "main", "index": 0}]

    merge = nodos[MERGE]
    entradas_existentes = {c["index"] for src, con in flujo["connections"].items() if src != NOMBRE
                           for c in con["main"][0] if c["node"] == MERGE}
    indice = max(entradas_existentes) + 1
    flujo["connections"][NOMBRE] = {"main": [[{"node": MERGE, "type": "main", "index": indice}]]}
    next(n for n in flujo["nodes"] if n["name"] == MERGE)["parameters"]["numberInputs"] = indice + 1
    assert merge["parameters"]["numberInputs"] in (indice, indice + 1)
    return flujo


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--origen", type=Path, default=AQUI.parents[1] / "resources" / "centinela.json")
    p.add_argument("--destino", type=Path, default=AQUI / "centinela_con_agente1.json")
    a = p.parse_args()

    hash_antes = sha256(a.origen)
    flujo = json.loads(a.origen.read_text(encoding="utf-8"))
    parcheado = parchear(flujo, (AQUI / "nodo_agente1.js").read_text(encoding="utf-8"))
    a.destino.write_text(json.dumps(parcheado, ensure_ascii=False, indent=2), encoding="utf-8")
    if sha256(a.origen) != hash_antes:
        raise SystemExit("ERROR: el workflow de origen cambió durante el parcheo")
    print(f"origen intacto  {hash_antes}  {a.origen}")
    print(f"copia integrada {sha256(a.destino)}  {a.destino}")


if __name__ == "__main__":
    main()
