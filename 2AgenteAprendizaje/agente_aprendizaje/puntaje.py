"""Réplica en Python del motor de puntaje del flujo ("Consolidar evidencia y puntuar") — RA2-04, RA2-09.

Permite dos cosas que el flujo no hace: simular otros umbrales sobre reportes ya decididos, y
calcular qué habría decidido el motor sin los hallazgos del Agente 1. Sólo es válido mientras sea
idéntico al original, por eso cada uso verifica paridad contra el puntaje registrado en el reporte
(`test_ra2_09_paridad_*`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

TOPES = {"ingenieria_social": 30, "url": 35, "html": 35, "cabeceras": 20, "autenticacion": 40, "identidad": 40,
         "lookalike": 45, "adjunto": 50, "inteligencia": 100, "infraestructura": 40, "dns": 40, "contexto": 20}
RANGO = {"FALSO_POSITIVO": 0, "ESCALAR": 1, "VERDADERO_POSITIVO": 2}
LIMPIO = "interno_autenticado_limpio"


def _round_js(x: float) -> int:
    return math.floor(x + 0.5)  # Math.round de JavaScript (no el redondeo bancario de Python)


@dataclass
class Puntaje:
    score: int
    por_categoria: dict[str, int]
    reglas_duras: list[str]
    veredicto_reglas: str


def decidir(score: int, reglas_duras: list[str], umbral_escalar: int, umbral_bloquear: int) -> str:
    veredicto = ("VERDADERO_POSITIVO" if score >= umbral_bloquear
                 else "ESCALAR" if score >= umbral_escalar else "FALSO_POSITIVO")
    if any(r != LIMPIO for r in reglas_duras):
        return "VERDADERO_POSITIVO"
    if LIMPIO in reglas_duras:
        return "FALSO_POSITIVO"
    return veredicto


def puntuar(hallazgos: list[dict], umbral_escalar: int = 30, umbral_bloquear: int = 65) -> Puntaje:
    por_categoria: dict[str, list[float]] = {}
    for h in hallazgos:
        por_categoria.setdefault(h["categoria"], []).append(h["peso"])
    score, detalle = 0.0, {}
    for categoria, pesos in por_categoria.items():
        positivos = sorted((p for p in pesos if p > 0), reverse=True)
        negativos = sum(p for p in pesos if p < 0)
        sub = 0.0
        for i, p in enumerate(positivos):
            sub += p * (1 if i == 0 else 0.7 if i == 1 else 0.5 if i == 2 else 0.3)
        sub = min(sub, TOPES.get(categoria, 30)) + negativos
        detalle[categoria] = _round_js(sub)
        score += sub
    score = max(0, min(100, _round_js(score)))

    tipos = {h["tipo"] for h in hallazgos}
    reglas = []
    if tipos & {"malwarebazaar_muestra_conocida", "vt_archivo_malicioso"}:
        reglas.append("adjunto_malware_conocido")
    if tipos & {"urlhaus_url_maliciosa", "threatfox_ioc", "vt_url_maliciosa", "vt_dominio_malicioso"}:
        reglas.append("ioc_confirmado_por_inteligencia")
    if tipos & {"ejecutable", "doble_extension", "unicode_rtl"}:
        reglas.append("adjunto_ejecutable")
    if "campo_password" in tipos:
        reglas.append("captura_de_credenciales_embebida")
    if "dominio_propio_similar" in tipos and tipos & {"spf_fail", "dmarc_fail", "dkim_fail", "spf_ausente"}:
        reglas.append("suplantacion_de_dominio_propio")
    if "dominio_inexistente" in tipos:
        reglas.append("remitente_inexistente")
    if "interno_autenticado" in tipos and score < 25:
        reglas.append(LIMPIO)
    return Puntaje(score, detalle, reglas, decidir(score, reglas, umbral_escalar, umbral_bloquear))
