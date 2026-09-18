from __future__ import annotations

import re

from .percepcion import Reporte
from .puntaje import puntuar

_TECNICA = re.compile(r"^\s*(T\d{4}(?:\.\d{3})?)\b\s*(.*)$")
FUENTE_A1 = "agente_identidad"


def agregar_attack(reportes: list[Reporte]) -> dict:
    tecnicas: dict[str, dict] = {}
    for r in reportes:
        for texto in r.ia.get("mitre_attack") or []:
            m = _TECNICA.match(str(texto))
            if not m:
                continue
            t = tecnicas.setdefault(m.group(1), {"id": m.group(1), "nombre": m.group(2).strip(), "n": 0,
                                                 "reportes": [], "por_veredicto": {}, "ultimo": ""})
            t["nombre"] = t["nombre"] or m.group(2).strip()
            t["n"] += 1
            t["reportes"].append(r.id)
            t["por_veredicto"][r.veredicto_final] = t["por_veredicto"].get(r.veredicto_final, 0) + 1
            t["ultimo"] = max(t["ultimo"], r.recibido_en)
    return {"fuente": "mapeo del flujo n8n (el Agente 2 no re-mapea)",
            "tecnicas": sorted(tecnicas.values(), key=lambda t: (-t["n"], t["id"]))}


def capa_navigator(agregado: dict) -> dict:
    maximo = max((t["n"] for t in agregado["tecnicas"]), default=1)
    return {
        "name": "CENTINELA · técnicas observadas",
        "versions": {"layer": "4.5", "navigator": "5.1.0"},
        "domain": "enterprise-attack",
        "description": "Técnicas ATT&CK reportadas por el flujo CENTINELA; score = cantidad de correos.",
        "techniques": [{"techniqueID": t["id"], "score": t["n"], "enabled": True,
                        "comment": f"{t['n']} correo(s): " + ", ".join(f"{k}={v}" for k, v in t["por_veredicto"].items())}
                       for t in agregado["tecnicas"]],
        "gradient": {"colors": ["#fff3b0", "#e76f51"], "minValue": 0, "maxValue": maximo},
        "legendItems": [],
        "showTacticRowBackground": False,
        "selectTechniquesAcrossTactics": True,
    }


def aporte_agente1(r: Reporte, umbrales: tuple[int, int]) -> dict:
    hallazgos = r.datos.get("hallazgos") or []
    propios = [h for h in hallazgos if h.get("fuente") == FUENTE_A1]
    if not r.agente1 and not propios:
        return {"integrado": False}
    con = puntuar(hallazgos, *umbrales)
    paridad = (con.score == r.score and sorted(con.reglas_duras) == sorted(r.reglas_duras)
               and con.veredicto_reglas == r.veredicto_reglas)
    sin = puntuar([h for h in hallazgos if h.get("fuente") != FUENTE_A1], *umbrales)
    return {
        "integrado": True, "estado": r.agente1.get("estado"),
        "conclusion": (r.agente1.get("resultados") or {}).get("conclusion"),
        "paridad": paridad, "score_con": con.score, "score_sin": sin.score,
        "veredicto_reglas_con": con.veredicto_reglas, "veredicto_reglas_sin": sin.veredicto_reglas,
        "reglas_duras_sin": sin.reglas_duras,
        "cambio_veredicto": paridad and con.veredicto_reglas != sin.veredicto_reglas,
        "hallazgos": [{"tipo": h["tipo"], "peso": h["peso"]} for h in propios],
    }


def resumen_aporte(reportes: list[Reporte], umbrales: tuple[int, int]) -> dict:
    integrados, sin_paridad, cambios, direcciones = 0, [], [], {}
    for r in reportes:
        a = aporte_agente1(r, umbrales)
        if not a["integrado"]:
            continue
        integrados += 1
        if not a["paridad"]:
            sin_paridad.append(r.id)
        elif a["cambio_veredicto"]:
            cambios.append(r.id)
            clave = f"{a['veredicto_reglas_sin']}→{a['veredicto_reglas_con']}"
            direcciones[clave] = direcciones.get(clave, 0) + 1
    return {"reportes_con_agente1": integrados, "cambios_de_veredicto": len(cambios),
            "por_direccion": direcciones, "reportes_con_cambio": cambios, "sin_paridad": sin_paridad}
