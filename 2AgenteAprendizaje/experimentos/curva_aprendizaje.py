from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agente_aprendizaje.aprendizaje import curva_aprendizaje  # noqa: E402
from agente_aprendizaje.critico import Costos  # noqa: E402

VIGENTES = (30, 65)
TAMANOS = [10, 20, 40, 80, 160, 320]


def _recortar(x: float) -> int:
    return max(0, min(100, round(x)))


def poblacion(n: int, semilla: int) -> list[tuple[int, list[str], str]]:
    rng = random.Random(semilla)
    datos = []
    for _ in range(n):
        if rng.random() < 0.30:
            tipo = rng.random()
            if tipo < 0.35:
                datos.append((100, ["adjunto_ejecutable"], "MALICIOSO"))
            elif tipo < 0.70:
                datos.append((_recortar(rng.gauss(74, 14)), [], "MALICIOSO"))
            else:
                datos.append((_recortar(rng.gauss(36, 9)), [], "MALICIOSO"))
        elif rng.random() < 0.08:
            datos.append((_recortar(rng.gauss(42, 6)), [], "LEGITIMO"))
        else:
            datos.append((_recortar(rng.gauss(12, 9)), [], "LEGITIMO"))
    return datos


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=800)
    p.add_argument("--semilla", type=int, default=11)
    p.add_argument("--repeticiones", type=int, default=40)
    a = p.parse_args()

    datos = poblacion(a.n, a.semilla)
    filas = curva_aprendizaje(datos, Costos(), VIGENTES, TAMANOS, repeticiones=a.repeticiones, semilla=a.semilla)
    print(f"población sintética: {len(datos)} correos, {sum(1 for *_, v in datos if v == 'MALICIOSO')} maliciosos")
    print(f"{'n':>5} | {'costo reservado aprendido':>26} | {'vigente 30/65':>13} | {'mejora':>7} | no peor")
    for f in filas:
        barra = "#" * max(0, round(f["mejora_media"] * 40))
        print(f"{f['n_entrenamiento']:>5} | {f['costo_reservado_propuesto']:>12.4f} ± {f['desvio_propuesto']:<11.4f} | "
              f"{f['costo_reservado_vigente']:>13.4f} | {f['mejora_media']:>+7.4f} | {f['proporcion_no_peor']:.0%} {barra}")

    salida = Path(__file__).parent / "resultados" / "curva_aprendizaje.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps({
        "tipo": "experimento controlado con población sintética",
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "parametros": {"n": a.n, "semilla": a.semilla, "repeticiones": a.repeticiones, "vigentes": VIGENTES,
                       "costos": {"falso_negativo": 20, "falso_positivo": 1, "escalar": 0.2}},
        "poblacion": {"maliciosos": sum(1 for *_, v in datos if v == "MALICIOSO"), "total": len(datos)},
        "curva": filas,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"resultados -> {salida}")


if __name__ == "__main__":
    main()
