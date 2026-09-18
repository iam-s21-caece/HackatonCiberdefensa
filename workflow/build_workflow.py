#!/usr/bin/env python3
"""
Arma el workflow de n8n (centinela_workflow.json) a partir de los archivos
de nodos en ./nodes. Cada nodo Code = un archivo .js legible; _common.js se
inyecta al inicio de todos.

Uso:  python build_workflow.py
"""
import json
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent
NODES = BASE / "nodes"
OUT = BASE / "centinela_workflow.json"

COMMON = (NODES / "_common.js").read_text(encoding="utf-8")


def code(name: str) -> str:
    return COMMON + "\n" + (NODES / name).read_text(encoding="utf-8")


def nid() -> str:
    return str(uuid.uuid4())


nodes = []
connections = {}


def add(name, type_, version, params, pos, **extra):
    n = {"parameters": params, "id": nid(), "name": name, "type": type_, "typeVersion": version, "position": list(pos)}
    n.update(extra)
    nodes.append(n)
    return name


def code_node(name, file, pos, **extra):
    return add(name, "n8n-nodes-base.code", 2, {"jsCode": code(file)}, pos, **extra)


def link(src, dst, src_index=0, dst_index=0):
    outs = connections.setdefault(src, {"main": []})["main"]
    while len(outs) <= src_index:
        outs.append([])
    outs[src_index].append({"node": dst, "type": "main", "index": dst_index})


# ---------------------------------------------------------------- entradas
WEBHOOK = add("Webhook: recibir correo", "n8n-nodes-base.webhook", 2,
              {"httpMethod": "POST", "path": "centinela/analizar", "responseMode": "responseNode", "options": {}},
              (0, 40), webhookId="c3n71n3l4-0001-4000-8000-000000000001")
WH_WA = add("Webhook: recibir WhatsApp", "n8n-nodes-base.webhook", 2,
            {"httpMethod": "POST", "path": "centinela/whatsapp", "responseMode": "responseNode", "options": {}},
            (0, 220), webhookId="c3n71n3l4-0003-4000-8000-000000000003")
WH_SMS = add("Webhook: recibir SMS", "n8n-nodes-base.webhook", 2,
             {"httpMethod": "POST", "path": "centinela/sms", "responseMode": "responseNode", "options": {}},
             (0, 400), webhookId="c3n71n3l4-0004-4000-8000-000000000004")
IMAP = add("IMAP: bandeja de entrada (opcional)", "n8n-nodes-base.emailReadImap", 2,
           {"mailbox": "INBOX", "postProcessAction": "read", "options": {}},
           (0, 580), disabled=True)

# ---------------------------------------------------------------- configuración
env = lambda k, d="": f"={{{{ $env.{k} || '{d}' }}}}"
assignments = [
    {"id": nid(), "name": "vt_api_key", "value": env("VT_API_KEY"), "type": "string"},
    {"id": nid(), "name": "abuseipdb_api_key", "value": env("ABUSEIPDB_API_KEY"), "type": "string"},
    {"id": nid(), "name": "abusech_api_key", "value": env("ABUSECH_API_KEY"), "type": "string"},
    {"id": nid(), "name": "ollama_url", "value": env("OLLAMA_URL", "http://ollama:11434"), "type": "string"},
    {"id": nid(), "name": "ollama_model", "value": env("OLLAMA_MODEL", "llama3.2:3b"), "type": "string"},
    {"id": nid(), "name": "ia_proveedor", "value": env("IA_PROVEEDOR", "auto"), "type": "string"},
    {"id": nid(), "name": "deepseek_url", "value": env("DEEPSEEK_URL", "https://api.deepseek.com"), "type": "string"},
    {"id": nid(), "name": "deepseek_model", "value": env("DEEPSEEK_MODEL", "deepseek-chat"), "type": "string"},
    # Sólo si hay key (booleano): la key misma no entra en el ítem, la lee el nodo HTTP de $env
    {"id": nid(), "name": "deepseek_configurada", "value": "={{ !!$env.DEEPSEEK_API_KEY }}", "type": "boolean"},
    {"id": nid(), "name": "dominios_propios", "value": env("DOMINIOS_PROPIOS", "ejercito.mil.ar,argentina.gob.ar,mil.ar"), "type": "string"},
    {"id": nid(), "name": "numeros_propios", "value": env("NUMEROS_PROPIOS"), "type": "string"},
    {"id": nid(), "name": "pais_propio", "value": env("PAIS_PROPIO", "54"), "type": "string"},
    {"id": nid(), "name": "soc_webhook_url", "value": env("SOC_WEBHOOK_URL"), "type": "string"},
]
CONFIG = add("Configuración", "n8n-nodes-base.set", 3.4,
             {"assignments": {"assignments": assignments}, "includeOtherFields": True, "options": {"includeBinary": True}},
             (260, 300))

# ---------------------------------------------------------------- desarmar
PARSE = code_node("Desarmar correo", "01_desarmar_correo.js", (520, 300))

# ---------------------------------------------------------------- análisis en paralelo (10 fuentes)
fuentes = [
    ("Cabeceras y autenticación (SPF/DKIM/DMARC)", "02_cabeceras_auth.js"),
    ("Heurísticas: cuerpo, URLs y adjuntos", "03_heuristicas.js"),
    ("VirusTotal: IPs, dominios, URLs y hashes", "04_virustotal.js"),
    ("AbuseIPDB: reputación de IPs", "05_abuseipdb.js"),
    ("crt.sh: certificados de dominios", "06_crtsh.js"),
    ("RDAP/WHOIS: antigüedad de dominios", "07_rdap.js"),
    ("URLhaus: URLs maliciosas", "08_urlhaus.js"),
    ("MalwareBazaar: hashes de adjuntos", "09_malwarebazaar.js"),
    ("ThreatFox: IOCs (dominios/IPs/hashes)", "10_threatfox.js"),
    ("DNS: MX / SPF / DMARC", "11_dns.js"),
    # Agente 1 de Elián (servicio externo, puerto 8101): entrada 11 del Merge, mismo formato que los demás
    ("Agente 1: identidad del remitente", "17_agente1.js"),
]
MERGE = add("Unir inteligencia", "n8n-nodes-base.merge", 3, {"numberInputs": len(fuentes)}, (1100, 300))
for i, (name, file) in enumerate(fuentes):
    y = 300 + (i - (len(fuentes) - 1) / 2) * 170
    code_node(name, file, (820, int(y)), onError="continueRegularOutput")
    link(PARSE, name)
    link(name, MERGE, 0, i)

# ---------------------------------------------------------------- decisión
CONSOL = code_node("Consolidar evidencia y puntuar", "12_consolidar.js", (1340, 300))
IA = add("IA: decisión (Ollama local o DeepSeek)", "n8n-nodes-base.httpRequest", 4.2,
         {"method": "POST", "url": "={{ $json.ia_request.url }}",
          "sendHeaders": True,
          "headerParameters": {"parameters": [{"name": "Authorization",
                                               "value": "={{ $json.ia_request.proveedor === 'deepseek' ? 'Bearer ' + $env.DEEPSEEK_API_KEY : 'Bearer local' }}"}]},
          "sendBody": True, "specifyBody": "json",
          "jsonBody": "={{ JSON.stringify($json.ia_request.body) }}", "options": {"timeout": 300000}},
         (1580, 300), onError="continueRegularOutput")
INTERP = code_node("Interpretar veredicto IA + guardrails", "13_interpretar_ia.js", (1820, 300))
RESPOND = add("Responder al webhook", "n8n-nodes-base.respondToWebhook", 1.1,
              {"respondWith": "firstIncomingItem", "options": {}}, (2060, 300), onError="continueRegularOutput")
TOFILE = add("Reporte → archivo JSON", "n8n-nodes-base.convertToFile", 1.1,
             {"operation": "toJson", "mode": "each", "options": {"fileName": "reporte.json"}}, (2300, 300))
SAVE = add("Guardar reporte en /data/reports", "n8n-nodes-base.readWriteFile", 1,
           {"operation": "write", "fileName": "=/data/reports/{{ $('" + INTERP + "').first().json.report_id }}.json",
            "dataPropertyName": "data", "options": {}}, (2540, 300), onError="continueRegularOutput")
SWITCH = add("Enrutar por veredicto", "n8n-nodes-base.switch", 3,
             {"mode": "expression", "numberOutputs": 3,
              "output": "={{ { VERDADERO_POSITIVO: 0, ESCALAR: 1, FALSO_POSITIVO: 2 }[$('" + INTERP + "').first().json.veredicto_final] ?? 1 }}",
              "options": {}}, (2780, 300))
VP = code_node("VERDADERO POSITIVO: cuarentena + alerta SOC", "14_accion_vp.js", (3040, 100))
ESC = code_node("ESCALAR: cola del investigador", "15_accion_escalar.js", (3040, 300))
FP = code_node("FALSO POSITIVO: entregar y registrar", "16_accion_fp.js", (3040, 500))
TOTXT = add("Línea de bitácora → texto", "n8n-nodes-base.convertToFile", 1.1,
            {"operation": "toText", "sourceProperty": "linea", "options": {"fileName": "linea.txt"}}, (3300, 300))
LOG = add("Registrar en bitácora (/data/bitacora)", "n8n-nodes-base.readWriteFile", 1,
          {"operation": "write", "fileName": "=/data/bitacora/{{ $json.veredicto || $('" + INTERP + "').first().json.veredicto_final }}.jsonl",
           "dataPropertyName": "data", "options": {"append": True}}, (3540, 300), onError="continueRegularOutput")

link(WEBHOOK, CONFIG); link(WH_WA, CONFIG); link(WH_SMS, CONFIG); link(IMAP, CONFIG); link(CONFIG, PARSE)
link(MERGE, CONSOL); link(CONSOL, IA); link(IA, INTERP); link(INTERP, RESPOND); link(RESPOND, TOFILE); link(TOFILE, SAVE); link(SAVE, SWITCH)
link(SWITCH, VP, 0); link(SWITCH, ESC, 1); link(SWITCH, FP, 2)
for a in (VP, ESC, FP):
    link(a, TOTXT)
link(TOTXT, LOG)

# ---------------------------------------------------------------- notas visuales
NOTA = ("## CENTINELA — Triage de phishing multicanal con IA (100% local)\n"
        "1. Entrada por **correo** (JSON o .eml crudo, o IMAP), **WhatsApp** (Meta Cloud API / Twilio / JSON) o **SMS** (Twilio / JSON).\n"
        "2. **Desarmar correo** normaliza cualquier canal a las mismas piezas: remitente (dominio o número), autenticación, IPs, dominios, URLs, adjuntos+hashes, cuerpo.\n"
        "3. 11 analizadores en paralelo: heurísticas, identidad (SPF/DKIM/DMARC o número de teléfono), VirusTotal, AbuseIPDB, crt.sh, RDAP, URLhaus, MalwareBazaar, ThreatFox, DNS y el **Agente 1** (recalcula SPF/DKIM/DMARC contra DNS; servicio externo :8101).\n"
        "4. Se consolida todo, se puntúa (0-100) y se aplican reglas duras.\n"
        "5. Una IA (Ollama local, o DeepSeek con DEEPSEEK_API_KEY) decide: VERDADERO_POSITIVO / FALSO_POSITIVO / ESCALAR, con guardrails.\n"
        "6. Se enruta: cuarentena + alerta SOC, cola de investigador (Agente 2 + interfaz), o entrega. Todo queda en /data.\n\n"
        "Keys en `.env` (opcionales): VT_API_KEY, ABUSEIPDB_API_KEY, ABUSECH_API_KEY, DEEPSEEK_API_KEY. Agente 1: AGENTE1_URL.")
nodes.append({"parameters": {"content": NOTA, "height": 330, "width": 560, "color": 4}, "id": nid(),
              "name": "Nota", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": [0, -330]})

workflow = {
    "name": "CENTINELA - Triage de phishing con IA",
    "id": "CentinelaPhish01",
    "nodes": nodes,
    "connections": connections,
    "active": False,  # `n8n import:workflow` siempre lo deja inactivo: activar con `n8n update:workflow --id=CentinelaPhish01 --active=true` + restart (o el toggle de la UI)
    "settings": {"executionOrder": "v1", "saveManualExecutions": True, "saveExecutionProgress": True},
    "pinData": {},
    "tags": [],
    "meta": {"instanceId": "centinela-hackathon-ejercito-argentino"},
}
OUT.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
# Copia con el nombre que usa el repositorio del equipo (raíz: centinela.json)
(BASE / "centinela.json").write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK -> {OUT}  ({len(nodes)} nodos, {sum(len(v['main']) for v in connections.values())} salidas conectadas)")
print(f"OK -> {BASE / 'centinela.json'}  (copia para el repo)")
