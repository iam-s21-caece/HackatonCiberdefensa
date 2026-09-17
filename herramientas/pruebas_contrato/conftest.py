"""Pruebas de contrato entre agentes — RG-06.

Importa los dos paquetes reales (no copias) para verificar que lo que escribe uno lo entiende el otro.

    pytest herramientas/pruebas_contrato
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
for carpeta in ("1AgenteModelosObjetivos", "2AgenteAprendizaje"):
    sys.path.insert(0, str(RAIZ / carpeta))
