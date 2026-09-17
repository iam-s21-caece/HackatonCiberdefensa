"""Caracterización de actores y campañas — RA2-10.

Agrupa correos maliciosos que comparten infraestructura. **Sin atribución nominal**: un actor es un
conjunto de indicadores técnicos observados en nuestros propios correos, no una organización con
nombre. Es atribución técnica, no política.

Indicadores que UNEN reportes (fuertes):
- `ip_origen`: IP que entregó el correo a nuestro MX según el Agente 1 (ruta confiable); si el
  Agente 1 no está, la primera IP pública de la cadena que registró el flujo.
- `reply_to`: dirección completa (una casilla que controla el atacante).
- `dominio`: dominio registrable del From, del Return-Path y de los enlaces, excluidos los dominios
  propios, los proveedores gratuitos y las plataformas masivas (unirían actores sin relación).
- `adjunto`: SHA-256.
- `destino_pago`: huella del CBU/CVU/alias calculada por el Agente 1. El dato en claro nunca llega acá.
  (RG-06: `ip_origen` y `destino_pago` se leen de `fuentes.agente_identidad.resultados` del reporte.)

Indicadores descriptivos (se muestran, no unen): host del Message-ID (suele delatar el kit de envío),
remitentes visibles y asuntos.

Qué reportes se consideran: los que el analista marcó MALICIOSO y los que el flujo no entregó y
todavía no tienen veredicto. Un veredicto humano LEGITIMO saca al reporte del análisis.
"""

from __future__ import annotations

import hashlib
from collections import Counter

from .percepcion import Reporte

SLD2 = frozenset({
    "com.ar", "gob.ar", "gov.ar", "mil.ar", "org.ar", "net.ar", "edu.ar", "tur.ar", "int.ar",
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.br", "gov.br", "com.mx", "gob.mx", "com.co", "gov.co",
    "com.pe", "gob.pe", "com.uy", "gub.uy", "com.cl", "gob.cl", "com.au", "co.jp", "co.nz", "com.es",
    "com.ve", "gob.ve", "com.bo", "gob.bo", "com.py", "gov.py", "com.ec", "gob.ec", "co.za", "com.tr",
    "com.cn", "co.in",
})
# Misma lista que FREEMAIL del flujo n8n.
FREEMAIL = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "hotmail.com.ar", "live.com", "msn.com",
    "yahoo.com", "yahoo.com.ar", "ymail.com", "protonmail.com", "proton.me", "icloud.com", "me.com", "aol.com",
    "gmx.com", "gmx.net", "mail.com", "yandex.com", "yandex.ru", "zoho.com", "fibertel.com.ar", "speedy.com.ar",
    "arnet.com.ar",
})
PLATAFORMAS = frozenset({
    "google.com", "gstatic.com", "googleapis.com", "microsoft.com", "office.com", "office365.com",
    "windows.net", "sharepoint.com", "apple.com", "facebook.com", "instagram.com", "whatsapp.com", "youtube.com",
    "linkedin.com", "twitter.com", "x.com", "amazonaws.com", "cloudflare.com", "mercadopago.com.ar",
    "mercadolibre.com.ar", "afip.gob.ar",
})
TIPOS_FUERTES = ("ip_origen", "reply_to", "dominio", "adjunto", "destino_pago")


def registrable(host: str | None) -> str:
    partes = [p for p in (host or "").strip().lower().rstrip(".").split(".") if p]
    if len(partes) <= 2:
        return ".".join(partes)
    return ".".join(partes[-3:]) if ".".join(partes[-2:]) in SLD2 else ".".join(partes[-2:])


def defang(valor: str) -> str:
    return valor.replace("http", "hxxp").replace(".", "[.]")


def _es_propio(dominio: str, propios: set[str]) -> bool:
    return any(dominio == p or dominio.endswith("." + p) for p in propios)


def indicadores(r: Reporte, propios: set[str]) -> dict[str, set[str]]:
    datos, correo = r.datos, r.datos.get("correo") or {}
    artefactos = datos.get("artefactos") or {}
    resultados_a1 = r.agente1.get("resultados") or {}
    ind: dict[str, set[str]] = {t: set() for t in TIPOS_FUERTES}

    origen = resultados_a1.get("origen") or {}
    if origen.get("confiable") and origen.get("ip"):
        ind["ip_origen"].add(origen["ip"])
    elif artefactos.get("ips"):
        ind["ip_origen"].add(artefactos["ips"][0])

    reply = ((correo.get("reply_to") or {}).get("direccion") or "").lower()
    if reply:
        ind["reply_to"].add(reply)

    candidatos = [(correo.get("de") or {}).get("dominio"), (correo.get("return_path") or {}).get("dominio")]
    candidatos += [u.get("dominio") for u in artefactos.get("urls") or [] if not u.get("es_ip")]
    for host in candidatos:
        dom = registrable(host)
        if dom and not _es_propio(dom, propios) and dom not in FREEMAIL and dom not in PLATAFORMAS:
            ind["dominio"].add(dom)

    ind["adjunto"].update(h for h in artefactos.get("hashes") or [] if h)
    ind["destino_pago"].update((resultados_a1.get("bec") or {}).get("destinos_hash") or [])
    return ind


def _descriptivos(r: Reporte) -> dict:
    correo = r.datos.get("correo") or {}
    mid = correo.get("message_id") or ""
    return {"remitente": (correo.get("de") or {}).get("direccion"), "asunto": correo.get("asunto"),
            "kit_message_id": mid.strip("<>").rsplit("@", 1)[1].lower() if "@" in mid else None}


def es_candidato(r: Reporte, verdades: dict[str, str]) -> bool:
    verdad = verdades.get(r.id)
    if verdad:
        return verdad == "MALICIOSO"
    return r.veredicto_final != "FALSO_POSITIVO"


def agrupar(reportes: list[Reporte], verdades: dict[str, str], propios: set[str]) -> dict:
    candidatos = [r for r in reportes if es_candidato(r, verdades)]
    padre = list(range(len(candidatos)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    por_indicador: dict[tuple[str, str], list[int]] = {}
    inds = [indicadores(r, propios) for r in candidatos]
    for i, ind in enumerate(inds):
        for tipo, valores in ind.items():
            for valor in valores:
                por_indicador.setdefault((tipo, valor), []).append(i)
    for miembros in por_indicador.values():
        for j in miembros[1:]:
            padre[raiz(j)] = raiz(miembros[0])

    grupos: dict[int, list[int]] = {}
    for i in range(len(candidatos)):
        grupos.setdefault(raiz(i), []).append(i)

    actores = []
    for miembros in grupos.values():
        rs = sorted((candidatos[i] for i in miembros), key=lambda r: (r.recibido_en, r.id))
        vinculos = sorted(
            ({"tipo": t, "valor": v if t in ("adjunto", "destino_pago") else defang(v), "reportes": len(set(m) & set(miembros))}
             for (t, v), m in por_indicador.items() if len(set(m) & set(miembros)) >= 2),
            key=lambda x: (-x["reportes"], x["tipo"]))
        todos = {t: sorted({v if t in ("adjunto", "destino_pago") else defang(v)
                            for i in miembros for v in inds[i][t]}) for t in TIPOS_FUERTES}
        desc = [_descriptivos(r) for r in rs]
        tecnicas = Counter(t.split()[0] for r in rs for t in r.ia.get("mitre_attack") or [] if t.strip())
        actores.append({
            "id": "actor-" + hashlib.sha1(rs[0].id.encode()).hexdigest()[:8],
            "n_reportes": len(rs), "reportes": [r.id for r in rs],
            "primer_visto": rs[0].recibido_en, "ultimo_visto": rs[-1].recibido_en,
            "vinculos": vinculos, "indicadores": todos,
            "remitentes_visibles": sorted({d["remitente"] for d in desc if d["remitente"]}),
            "asuntos": sorted({d["asunto"] for d in desc if d["asunto"]}),
            "kits_message_id": sorted({d["kit_message_id"] for d in desc if d["kit_message_id"]}),
            "veredictos_flujo": dict(Counter(r.veredicto_final for r in rs)),
            "veredictos_humanos": dict(Counter(verdades.get(r.id, "SIN_REVISAR") for r in rs)),
            "conclusiones_agente1": dict(Counter((r.agente1.get("resultados") or {}).get("conclusion", "SIN_AGENTE1")
                                                 for r in rs)),
            "tecnicas_attack_del_flujo": dict(tecnicas.most_common()),
            "score_maximo": max(r.score for r in rs),
            "correos_distintos_por_contenido": len({(d["remitente"], d["asunto"]) for d in desc}),
        })
    actores.sort(key=lambda a: a["ultimo_visto"], reverse=True)          # más reciente primero...
    actores.sort(key=lambda a: (a["n_reportes"] == 1, -a["n_reportes"]))  # ...dentro de campañas por tamaño
    return {
        "criterio": "reportes maliciosos o no entregados que comparten IP de origen, Reply-To, dominio, "
                    "adjunto o destino de pago; sin atribución nominal",
        "n_reportes_considerados": len(candidatos),
        "n_actores": len(actores),
        "n_con_varios_reportes": sum(1 for a in actores if a["n_reportes"] > 1),
        "actores": actores,
    }
