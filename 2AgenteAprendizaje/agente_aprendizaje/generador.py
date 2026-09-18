from __future__ import annotations

from .percepcion import Reporte


def priorizar(reportes: list[Reporte], verdades: dict[str, str], umbrales: tuple[int, int]) -> list[dict]:
    cola = []
    for r in reportes:
        if r.id in verdades:
            continue
        prioridad, motivos = 0, []
        conclusion_a1 = (r.agente1.get("resultados") or {}).get("conclusion") if r.agente1 else None
        if r.liberado_por_ia:
            prioridad += 100
            motivos.append("la IA llevó a entregar un correo que el motor de reglas no entregaba")
        elif r.degradacion_ia:
            prioridad += 60
            motivos.append(f"la IA propuso {r.ia_veredicto}, menos severo que el motor de reglas ({r.veredicto_reglas})")
        elif r.escalamiento_ia:
            prioridad += 25
            motivos.append(f"la IA propuso {r.ia_veredicto}, más severo que el motor de reglas ({r.veredicto_reglas})")
        if conclusion_a1 == "SUPLANTACION_CONFIRMADA" and r.veredicto_final == "FALSO_POSITIVO":
            prioridad += 80
            motivos.append("el Agente 1 confirmó suplantación y el correo se entregó")
        if r.veredicto_final == "ESCALAR":
            prioridad += 40
            motivos.append("escalado: espera una decisión humana")
        if not r.reglas_duras:
            distancia = min(abs(r.score - umbrales[0]), abs(r.score - umbrales[1]))
            if distancia <= 10:
                prioridad += 10 - distancia
                motivos.append(f"score {r.score} a {distancia} puntos de un umbral")
        confianza = r.ia.get("confianza")
        if r.ia_veredicto and isinstance(confianza, (int, float)) and confianza < 0.6:
            prioridad += 10
            motivos.append(f"confianza baja de la IA ({confianza})")
        if not motivos:
            prioridad, motivos = 1, ["sin conflictos: control por muestreo"]
        cola.append({**r.resumen(), "prioridad": prioridad, "motivos": motivos})
    return sorted(cola, key=lambda c: (-c["prioridad"], c["recibido_en"]))  # a igual prioridad, el más antiguo primero
