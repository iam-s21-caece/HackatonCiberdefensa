"""Traducción de las creencias finales a hallazgos del flujo — RA1-11, RA1-12, RA1-13.

Criterios:
1. Tipos nuevos con prefijo `a1_`: nunca se reemite un hallazgo que el flujo ya produce.
2. Un recálculo que coincide con lo declarado no suma puntaje (el flujo ya lo contó); sólo suma
   cuando el recálculo AGREGA información: contradice lo declarado o lo reemplaza porque faltaba.
3. Sólo se emite sobre resultados concluyentes. Lo que no se pudo verificar no genera hallazgos.
4. Verificar la identidad no resta puntaje: una cuenta interna comprometida también pasa DMARC.
5. Sin técnicas MITRE ATT&CK: ese mapeo es responsabilidad del flujo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .contrato import FUENTE, Hallazgo

if TYPE_CHECKING:
    from .agente import Creencias

# Topes por categoría del motor de puntaje del flujo ("Consolidar evidencia y puntuar").
TOPES_FLUJO = {"ingenieria_social": 30, "url": 35, "html": 35, "cabeceras": 20, "autenticacion": 40,
               "identidad": 40, "lookalike": 45, "adjunto": 50, "inteligencia": 100,
               "infraestructura": 40, "dns": 40, "contexto": 20}

# tipo -> (categoría, severidad, peso)
CATALOGO: dict[str, tuple[str, str, int]] = {
    "a1_autenticacion_forjada": ("autenticacion", "critica", 40),
    "a1_spf_recalculado_fail": ("autenticacion", "alta", 20),
    "a1_spf_recalculado_softfail": ("autenticacion", "media", 10),
    "a1_dkim_firma_invalida": ("autenticacion", "alta", 18),
    "a1_dmarc_recalculado_fail_reject": ("autenticacion", "alta", 25),
    "a1_dmarc_recalculado_fail_quarantine": ("autenticacion", "alta", 18),
    "a1_dmarc_recalculado_fail_none": ("autenticacion", "media", 8),
    "a1_suplantacion_dominio_propio": ("identidad", "critica", 40),
    "a1_suplantacion_dominio_externo": ("identidad", "alta", 30),
    "a1_patron_bec_primer_contacto": ("contexto", "critica", 20),
    "a1_patron_bec": ("contexto", "alta", 15),
    "a1_instruccion_pago": ("contexto", "media", 8),
    "a1_identidad_verificada": ("identidad", "info", 0),
    "a1_origen_no_verificable": ("cabeceras", "info", 0),
}


def _h(tipo: str, valor: str, detalle: str) -> Hallazgo:
    categoria, severidad, peso = CATALOGO[tipo]
    return Hallazgo(categoria=categoria, tipo=tipo, valor=str(valor)[:200], severidad=severidad,
                    peso=peso, detalle=detalle, fuente=FUENTE)


def construir(c: "Creencias") -> list[Hallazgo]:
    hz: list[Hallazgo] = []
    dec = c.declarada

    # --- contradicción entre lo declarado y lo recalculado (RA1-07) ---
    contradicciones = []
    if dec.get("spf") == "pass" and c.spf and c.spf.resultado in ("fail", "softfail"):
        contradicciones.append(f"SPF declarado pass, recalculado {c.spf.resultado}")
    if dec.get("dmarc") == "pass" and c.dmarc and c.dmarc.resultado == "fail":
        contradicciones.append("DMARC declarado pass, recalculado fail")
    if dec.get("dkim") == "pass" and c.dkim and all(f.valida is False for f in c.dkim):
        contradicciones.append("DKIM declarado pass, ninguna firma verifica")
    if contradicciones:
        hz.append(_h("a1_autenticacion_forjada", "; ".join(contradicciones),
                     "La cabecera Authentication-Results afirma una autenticación que el recálculo "
                     "refuta: la cabecera fue escrita por el remitente, no por nuestro servidor."))

    # --- SPF recalculado: sólo si difiere de lo que el flujo ya leyó ---
    if c.spf and c.spf.resultado in ("fail", "softfail") and dec.get("spf") != c.spf.resultado:
        hz.append(_h(f"a1_spf_recalculado_{c.spf.resultado}", f"{c.spf.ip} → {c.spf.dominio}",
                     f"SPF recalculado: la IP {c.spf.ip} (entregó el correo a {c.origen.mx}) no está "
                     f"autorizada por {c.spf.dominio} ({c.spf.registro})."))

    # --- DKIM verificado criptográficamente ---
    invalidas = [f for f in (c.dkim or []) if f.valida is False]
    if invalidas and dec.get("dkim") != "fail":
        hz.append(_h("a1_dkim_firma_invalida", ", ".join(f"d={f.dominio}" for f in invalidas),
                     "Firma DKIM presente que no verifica criptográficamente: "
                     + "; ".join(f"d={f.dominio} s={f.selector}: {f.error}" for f in invalidas)))

    # --- DMARC recalculado ---
    if c.dmarc and c.dmarc.resultado == "fail":
        politica = c.dmarc.politica or "none"
        if dec.get("dmarc") != "fail":
            hz.append(_h(f"a1_dmarc_recalculado_fail_{politica}", f"{c.from_dom} p={politica}",
                         f"DMARC recalculado falla: {c.dmarc.detalle}. El dueño del dominio pide "
                         f"'{politica}' para estos correos."))
        if c.dominio_propio:
            hz.append(_h("a1_suplantacion_dominio_propio", c.from_dir,
                         f"El correo dice venir de {c.from_dom}, dominio de la organización, pero ni "
                         "SPF ni DKIM lo respaldan: suplantación verificada del dominio propio."))
        elif politica in ("reject", "quarantine"):
            hz.append(_h("a1_suplantacion_dominio_externo", c.from_dir,
                         f"{c.from_dom} publica DMARC p={politica} y este correo no lo cumple: "
                         "el dominio del From está suplantado."))
    elif c.dmarc and c.dmarc.resultado == "pass":
        hz.append(_h("a1_identidad_verificada", c.from_dir,
                     f"Identidad verificada por recálculo: {c.dmarc.detalle}. No implica que el "
                     "contenido sea benigno (una cuenta legítima puede estar comprometida)."))

    if c.conclusion == "NO_VERIFICABLE" and c.origen and not c.origen.confiable and not c.dkim:
        hz.append(_h("a1_origen_no_verificable", c.origen_entrada, c.origen.motivo))

    # --- patrón BEC compuesto (RA1-09) ---
    if c.bec:
        identidad_debil = c.conclusion in ("SUPLANTACION_CONFIRMADA", "NO_VERIFICABLE")
        if identidad_debil and c.bec.se_presenta_como_autoridad and c.bec.instruccion_pago:
            tipo = "a1_patron_bec_primer_contacto" if c.primer_contacto else "a1_patron_bec"
            hz.append(_h(tipo, ", ".join(c.bec.autoridad[:3]),
                         "Se presenta como autoridad (" + ", ".join(c.bec.autoridad[:3]) + "), da una "
                         "instrucción de pago y su identidad no está verificada"
                         + (", y es la primera vez que le escribe a este destinatario." if c.primer_contacto
                            else ".")))
        elif c.bec.cbu or c.bec.cvu or c.bec.alias:
            destinos = c.bec.cbu + c.bec.cvu + c.bec.alias
            hz.append(_h("a1_instruccion_pago", ", ".join(destinos),
                         "Instrucción de pago con destino bancario válido (CBU/CVU con dígito "
                         "verificador correcto o alias)."))
    return hz
