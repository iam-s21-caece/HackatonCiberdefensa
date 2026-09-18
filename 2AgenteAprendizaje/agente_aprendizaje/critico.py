from __future__ import annotations

from dataclasses import asdict, dataclass

from .percepcion import ACCION, Reporte


@dataclass
class Costos:
    falso_negativo: float = 20.0
    falso_positivo: float = 1.0
    escalar: float = 0.2

    def de(self, accion: str, verdad: str) -> float:
        if accion == "escalar":
            return self.escalar
        if accion == "bloquear":
            return self.falso_positivo if verdad == "LEGITIMO" else 0.0
        return self.falso_negativo if verdad == "MALICIOSO" else 0.0


def _metricas(tp: int, fp: int, fn: int, tn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1}


def evaluar(pares: list[tuple[str, str]], costos: Costos) -> dict:
    """`pares` = [(veredicto del flujo, verdad humana)]."""
    matriz = {a: {"MALICIOSO": 0, "LEGITIMO": 0} for a in ("bloquear", "escalar", "entregar")}
    costo = 0.0
    for veredicto, verdad in pares:
        accion = ACCION[veredicto]
        matriz[accion][verdad] += 1
        costo += costos.de(accion, verdad)
    m, l = (lambda a: matriz[a]["MALICIOSO"]), (lambda a: matriz[a]["LEGITIMO"])
    n = len(pares)
    return {
        "n": n,
        "matriz": matriz,
        "deteccion": _metricas(tp=m("bloquear") + m("escalar"), fp=l("bloquear") + l("escalar"),
                               fn=m("entregar"), tn=l("entregar")),
        "bloqueo_automatico": _metricas(tp=m("bloquear"), fp=l("bloquear"),
                                        fn=m("escalar") + m("entregar"), tn=l("escalar") + l("entregar")),
        "tasa_escalamiento": (m("escalar") + l("escalar")) / n if n else None,
        "costo_total": round(costo, 3),
        "costo_medio": round(costo / n, 4) if n else None,
    }


def criticar(reportes: list[Reporte], verdades: dict[str, str], costos: Costos) -> dict:
    etiquetados = [r for r in reportes if r.id in verdades]
    return {
        "n_reportes": len(reportes),
        "n_etiquetados": len(etiquetados),
        "costos": asdict(costos),
        "flujo_final": evaluar([(r.veredicto_final, verdades[r.id]) for r in etiquetados], costos),
        "solo_motor_reglas": evaluar([(r.veredicto_reglas, verdades[r.id]) for r in etiquetados], costos),
    }
