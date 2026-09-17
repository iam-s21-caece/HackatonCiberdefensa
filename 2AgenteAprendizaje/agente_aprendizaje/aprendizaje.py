"""Elemento de aprendizaje: umbrales de menor costo esperado y evidencia de que aprende — RA2-04, RA2-12.

`proponer_umbrales` barre todos los pares (umbral de escalar, umbral de bloquear) sobre los reportes
con veredicto humano, simulando el motor de reglas con el puntaje y las reglas duras registrados.
Límites declarados en la salida:
- simula el motor de reglas; la IA y los guardrails no se re-ejecutan;
- con pocos casos muchos pares empatan: se informa el rango óptimo, no sólo un punto;
- **propone, no aplica**: cambiar el umbral de bloqueo de una fuerza es una decisión humana.

`curva_aprendizaje` es la evidencia: aprende umbrales con n veredictos y mide el costo por correo en
casos RESERVADOS (que no vio al aprender), contra los umbrales vigentes, repitiendo con particiones al
azar. Si el agente aprende, el costo reservado baja y se estabiliza a medida que crece n.

La tabla de costos usa sumas acumuladas por valor de puntaje (O(1) por par) y es equivalente al
recorrido directo (`test_ra2_04_tabla_optimizada_equivale_al_recorrido_directo`).
"""

from __future__ import annotations

import random
import statistics

from .critico import Costos, evaluar
from .percepcion import ACCION, Reporte
from .puntaje import LIMPIO, decidir

NOTA = ("Simula el motor de reglas con los puntajes registrados; la IA y los guardrails no se re-ejecutan. "
        "Es una propuesta: no se aplica ningún cambio al flujo.")

Dato = tuple[int, list[str], str]  # (score, reglas_duras, verdad)


def datos_etiquetados(reportes: list[Reporte], verdades: dict[str, str]) -> list[Dato]:
    return [(r.score, r.reglas_duras, verdades[r.id]) for r in reportes if r.id in verdades]


def tabla_costos(datos: list[Dato], costos: Costos) -> dict[tuple[int, int], float]:
    mal, leg, fijo = [0] * 101, [0] * 101, 0.0
    for score, reglas, verdad in datos:
        if any(r != LIMPIO for r in reglas):
            fijo += costos.de("bloquear", verdad)
        elif LIMPIO in reglas:
            fijo += costos.de("entregar", verdad)
        else:
            (mal if verdad == "MALICIOSO" else leg)[max(0, min(100, score))] += 1
    acum_mal, acum_leg = [0] * 102, [0] * 102
    for s in range(101):
        acum_mal[s + 1], acum_leg[s + 1] = acum_mal[s] + mal[s], acum_leg[s] + leg[s]
    tabla = {}
    for e in range(101):
        entregados_mal = acum_mal[e]
        for b in range(e, 101):
            escalados = (acum_mal[b] - acum_mal[e]) + (acum_leg[b] - acum_leg[e])
            bloqueados_leg = acum_leg[101] - acum_leg[b]
            tabla[(e, b)] = round(fijo + entregados_mal * costos.falso_negativo + escalados * costos.escalar
                                  + bloqueados_leg * costos.falso_positivo, 6)
    return tabla


def _elegir(tabla: dict[tuple[int, int], float], actual: tuple[int, int]) -> tuple[tuple[int, int], list]:
    minimo = min(tabla.values())
    optimos = [par for par, c in tabla.items() if c == minimo]
    elegido = min(optimos, key=lambda p: (abs(p[0] - actual[0]) + abs(p[1] - actual[1]), -p[1]))
    return elegido, optimos


def _veredictos(datos: list[Dato], e: int, b: int) -> list[tuple[str, str]]:
    return [(decidir(s, reglas, e, b), v) for s, reglas, v in datos]


def costo_medio(datos: list[Dato], par: tuple[int, int], costos: Costos) -> float:
    return sum(costos.de(ACCION[d], v) for d, v in _veredictos(datos, *par)) / len(datos)


def proponer_umbrales(reportes: list[Reporte], verdades: dict[str, str], costos: Costos,
                      actual: tuple[int, int], muestra_minima: int) -> dict:
    datos = datos_etiquetados(reportes, verdades)
    maliciosos = sum(1 for *_, v in datos if v == "MALICIOSO")
    legitimos = len(datos) - maliciosos
    base = {"n": len(datos), "maliciosos": maliciosos, "legitimos": legitimos, "nota": NOTA,
            "actual": {"escalar": actual[0], "bloquear": actual[1],
                       **({"evaluacion": evaluar(_veredictos(datos, *actual), costos)} if datos else {})}}
    if len(datos) < muestra_minima or not maliciosos or not legitimos:
        return {**base, "estado": "muestra_insuficiente",
                "requiere": f"al menos {muestra_minima} veredictos humanos con ambas clases "
                            f"(hay {maliciosos} maliciosos y {legitimos} legítimos)"}

    tabla = tabla_costos(datos, costos)
    elegido, optimos = _elegir(tabla, actual)
    minimo, costo_actual = tabla[elegido], tabla[actual]
    return {
        **base,
        "estado": "propuesta" if minimo < costo_actual else "actual_es_optimo",
        "propuesta": {"escalar": elegido[0], "bloquear": elegido[1], "costo_total": minimo,
                      "evaluacion": evaluar(_veredictos(datos, *elegido), costos)},
        "mejora_costo": round(costo_actual - minimo, 3),
        "rango_optimo": {"escalar": [min(p[0] for p in optimos), max(p[0] for p in optimos)],
                         "bloquear": [min(p[1] for p in optimos), max(p[1] for p in optimos)],
                         "pares_empatados": len(optimos)},
        "curva_bloquear": [{"umbral": b, "costo": tabla[(elegido[0], b)]} for b in range(elegido[0], 101)],
        "curva_escalar": [{"umbral": e, "costo": tabla[(e, elegido[1])]} for e in range(0, elegido[1] + 1)],
    }


def curva_aprendizaje(datos: list[Dato], costos: Costos, actual: tuple[int, int], tamanos: list[int],
                      repeticiones: int = 30, semilla: int = 7) -> list[dict]:
    rng = random.Random(semilla)
    filas = []
    for n in tamanos:
        if n >= len(datos):
            continue
        propuestos, vigentes, no_peor = [], [], 0
        for _ in range(repeticiones):
            for _intento in range(20):
                indices = set(rng.sample(range(len(datos)), n))
                entrenamiento = [datos[i] for i in indices]
                if {v for *_, v in entrenamiento} == {"MALICIOSO", "LEGITIMO"}:
                    break
            else:
                continue
            reservados = [d for i, d in enumerate(datos) if i not in indices]
            elegido, _ = _elegir(tabla_costos(entrenamiento, costos), actual)
            cp, ca = costo_medio(reservados, elegido, costos), costo_medio(reservados, actual, costos)
            propuestos.append(cp)
            vigentes.append(ca)
            no_peor += cp <= ca + 1e-9
        if not propuestos:
            continue
        filas.append({
            "n_entrenamiento": n, "repeticiones": len(propuestos),
            "costo_reservado_propuesto": round(statistics.fmean(propuestos), 4),
            "desvio_propuesto": round(statistics.pstdev(propuestos), 4),
            "costo_reservado_vigente": round(statistics.fmean(vigentes), 4),
            "mejora_media": round(statistics.fmean(vigentes) - statistics.fmean(propuestos), 4),
            "proporcion_no_peor": round(no_peor / len(propuestos), 3),
        })
    return filas


def evidencia_real(reportes: list[Reporte], verdades: dict[str, str], costos: Costos,
                   actual: tuple[int, int], muestra_minima: int) -> dict:
    """Curva sobre los veredictos humanos reales, cuando alcanzan para reservar casos."""
    datos = datos_etiquetados(reportes, verdades)
    if len(datos) < 2 * muestra_minima:
        return {"estado": "muestra_insuficiente", "n": len(datos),
                "requiere": f"al menos {2 * muestra_minima} veredictos para aprender con una parte y medir con otra"}
    tamanos = sorted({max(muestra_minima, int(len(datos) * f)) for f in (0.2, 0.35, 0.5, 0.65, 0.8)})
    return {"estado": "calculada", "n": len(datos),
            "curva": curva_aprendizaje(datos, costos, actual, tamanos, repeticiones=20)}
