"""Supervisión del decisor IA — RA2-05, RA2-11.

Aplica al LLM del flujo la idea del meta-agente de comportamiento: la entidad es
`decisor-ia:<dimensión>` y se aprende cómo se comporta.

La dimensión que importa es la **degradación**: la IA propone una acción menos severa que el motor de
reglas. Es la firma de una inyección de prompt ("este correo fue verificado por Sistemas").

Qué aprende del veredicto humano (RA2-11): la **confiabilidad de las degradaciones**, es decir, qué
proporción de los correos que la IA rebajó resultaron maliciosos, con intervalo de Wilson al 95 %.
Ese conocimiento cambia el comportamiento del supervisor: cuanto más riesgosa demostró ser una
degradación, menor es el margen tolerado antes de alertar por aumento de degradaciones. Y produce la
recomendación con evidencia para el guardrail del flujo.

Alertas:
- `degradacion_ia_en_aumento`: la tasa reciente supera la línea base aprendida
  (base + 2 desvíos binomiales, con un margen mínimo reducido por el riesgo aprendido).
- `ia_degrado_un_malicioso`: una degradación que el humano confirmó maliciosa; crítica si llegó al usuario.
- `ia_no_disponible`: la IA cayó en la mayoría de la ventana. Una IA omitida a propósito por el flujo
  (`ia.omitida: true`) no cuenta como caída.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .percepcion import Reporte


@dataclass
class ParametrosSupervision:
    ventana: int = 20
    minimo: int = 5
    tasa_previa: float = 0.10
    margen_minimo: float = 0.15
    z: float = 2.0
    tasa_caida: float = 0.5
    tolerancia_degradacion: float = 0.10


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centro - margen), min(1.0, centro + margen)


def _tasa(reportes: list[Reporte], condicion) -> float | None:
    return sum(1 for r in reportes if condicion(r)) / len(reportes) if reportes else None


def _percentil(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    valores = sorted(valores)
    return valores[min(len(valores) - 1, max(0, math.ceil(p * len(valores)) - 1))]


def _caida(r: Reporte) -> bool:
    return r.ia_veredicto is None and not r.ia_omitida


def _tasas(reportes: list[Reporte]) -> dict:
    latencias = [r.ia.get("duracion_ms") for r in reportes if r.ia.get("duracion_ms")]
    return {
        "n": len(reportes),
        "ia_disponible": _tasa(reportes, lambda r: r.ia_veredicto is not None),
        "ia_omitida": _tasa(reportes, lambda r: r.ia_omitida),
        "ia_caida": _tasa(reportes, _caida),
        "degradacion": _tasa(reportes, lambda r: r.degradacion_ia),
        "escalamiento": _tasa(reportes, lambda r: r.escalamiento_ia),
        "guardrail_activado": _tasa(reportes, lambda r: r.guardrail_activado),
        "liberado_por_ia": sum(1 for r in reportes if r.liberado_por_ia),
        "latencia_ms_p50": _percentil(latencias, 0.5),
        "latencia_ms_p95": _percentil(latencias, 0.95),
    }


def confiabilidad_degradacion(reportes: list[Reporte], verdades: dict[str, str],
                              p: ParametrosSupervision) -> dict:
    revisadas = [r for r in reportes if r.degradacion_ia and r.id in verdades]
    k = sum(1 for r in revisadas if verdades[r.id] == "MALICIOSO")
    n = len(revisadas)
    inferior, superior = wilson(k, n)
    if n < p.minimo:
        estado, riesgo = "evidencia_insuficiente", 0.0
        recomendacion = (f"Hay {n} degradaciones de la IA revisadas por un analista; se necesitan al menos "
                         f"{p.minimo} para concluir.")
    elif inferior > p.tolerancia_degradacion:
        estado, riesgo = "riesgosa", inferior
        recomendacion = (f"Al menos el {inferior:.0%} de las degradaciones revisadas eran maliciosas (IC95 "
                         f"{inferior:.0%}–{superior:.0%}, {k}/{n}). Recomendación: impedir que la IA baje el "
                         "veredicto del motor de reglas (guardrail monótono).")
    elif superior < p.tolerancia_degradacion:
        estado, riesgo = "confiable", 0.0
        recomendacion = (f"Las degradaciones revisadas fueron legítimas (IC95 {inferior:.0%}–{superior:.0%}): "
                         "la IA reduce escalamientos sin dejar pasar maliciosos en lo observado.")
    else:
        estado, riesgo = "incierta", inferior
        recomendacion = (f"{k}/{n} degradaciones revisadas eran maliciosas (IC95 {inferior:.0%}–{superior:.0%}): "
                         "todavía no alcanza para concluir en ningún sentido.")
    return {"revisadas": n, "maliciosas": k, "tasa": k / n if n else None, "ic95": [inferior, superior],
            "tolerancia": p.tolerancia_degradacion, "estado": estado, "riesgo_aprendido": riesgo,
            "recomendacion": recomendacion}


def supervisar(reportes: list[Reporte], verdades: dict[str, str], p: ParametrosSupervision) -> dict:
    """`reportes` ordenados del más antiguo al más reciente."""
    ventana, base = reportes[-p.ventana:], reportes[:-p.ventana]
    alertas: list[dict] = []
    confiabilidad = confiabilidad_degradacion(reportes, verdades, p)
    margen = p.margen_minimo * (1 - confiabilidad["riesgo_aprendido"])

    p_base = _tasa(base, lambda r: r.degradacion_ia) if len(base) >= p.minimo else p.tasa_previa
    umbral = None
    if len(ventana) >= p.minimo:
        umbral = max(p_base + p.z * math.sqrt(p_base * (1 - p_base) / len(ventana)), p_base + margen)
        tasa = _tasa(ventana, lambda r: r.degradacion_ia)
        if tasa > umbral:
            alertas.append({
                "tipo": "degradacion_ia_en_aumento", "severidad": "alta",
                "clave": f"degradacion:{ventana[-1].id}",
                "detalle": f"La IA propuso una acción menos severa que el motor de reglas en {tasa:.0%} de los últimos "
                           f"{len(ventana)} correos (línea base {p_base:.0%}, umbral {umbral:.0%}). "
                           "Posible inyección de prompt o deriva del modelo.",
                "reportes": [r.id for r in ventana if r.degradacion_ia],
            })
        caida = _tasa(ventana, _caida)
        if caida >= p.tasa_caida:
            alertas.append({
                "tipo": "ia_no_disponible", "severidad": "media", "clave": f"ia_caida:{ventana[-1].id}",
                "detalle": f"La IA no respondió en {caida:.0%} de los últimos {len(ventana)} correos: "
                           "el flujo está decidiendo sólo con el motor de reglas.",
                "reportes": [r.id for r in ventana if _caida(r)],
            })

    for r in reportes:
        if r.degradacion_ia and verdades.get(r.id) == "MALICIOSO":
            entregado = r.veredicto_final == "FALSO_POSITIVO"
            alertas.append({
                "tipo": "ia_degrado_un_malicioso", "severidad": "critica" if entregado else "alta",
                "clave": f"ia_malicioso:{r.id}",
                "detalle": f"La IA propuso {r.ia_veredicto} donde el motor de reglas decía {r.veredicto_reglas}, "
                           f"y el analista confirmó que era malicioso. Acción final: {r.veredicto_final}"
                           + (" (llegó al usuario)." if entregado else " (los guardrails lo contuvieron)."),
                "reportes": [r.id],
            })

    return {
        "entidad": "decisor-ia",
        "global": _tasas(reportes),
        "ventana": _tasas(ventana),
        "linea_base": {**_tasas(base), "degradacion_usada": p_base,
                       "origen": "aprendida" if len(base) >= p.minimo else "tasa_previa"},
        "confiabilidad_degradacion": confiabilidad,
        "margen_usado": margen,
        "umbral_degradacion": umbral,
        "alertas": alertas,
    }
