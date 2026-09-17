#!/usr/bin/env bash
# Envía un correo (JSON o .eml), un WhatsApp o un SMS a CENTINELA y muestra el veredicto (requiere curl + jq).
# Uso: bash scripts/analizar.sh samples/phishing_credenciales.json
#      bash scripts/analizar.sh samples/phishing_reembolso.eml
#      bash scripts/analizar.sh samples/whatsapp_secuestro_cuenta.json   # la puerta sale del nombre (whatsapp_* / sms_*)
#      bash scripts/analizar.sh --canal sms mensaje.json                 # o se fuerza
#      bash scripts/analizar.sh --json samples/legitimo.json             # respuesta cruda (la usa verificar_e2e.sh)
# Misma lógica que analizar.ps1. URL: CENTINELA_URL (completa) o N8N_PUERTO de .env.
set -euo pipefail
. "$(dirname "$0")/_comun.sh"

JSON=0; CANAL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --json) JSON=1; shift ;;
    --canal) CANAL="${2:?--canal email|whatsapp|sms}"; shift 2 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) break ;;
  esac
done
ARCHIVO="${1:?uso: analizar.sh [--json] [--canal email|whatsapp|sms] <archivo.json|archivo.eml>}"
[ -f "$ARCHIVO" ] || fallar "no existe: $ARCHIVO"
if [ -z "$CANAL" ]; then
  case "$(basename "$ARCHIVO")" in *whatsapp*) CANAL=whatsapp ;; *sms*) CANAL=sms ;; *) CANAL=email ;; esac
fi
case "$CANAL" in email) PUERTA=analizar ;; whatsapp|sms) PUERTA="$CANAL" ;; *) fallar "canal inválido: $CANAL" ;; esac
URL="${CENTINELA_URL:-$(url_n8n)/webhook/centinela/$PUERTA}"

RESPUESTA="$(mktemp)"; trap 'rm -f "$RESPUESTA"' EXIT
# El cuerpo va por stdin: un .eml con adjuntos supera el largo máximo de una línea de comandos.
if [[ "$ARCHIVO" == *.eml ]]; then
  jq -Rs '{raw: .}' "$ARCHIVO"
else
  cat "$ARCHIVO"
fi | curl -sS --max-time 600 -X POST "$URL" -H 'Content-Type: application/json; charset=utf-8' \
       --data-binary @- -o "$RESPUESTA" -w '%{http_code}' > "$RESPUESTA.http" || { rm -f "$RESPUESTA.http"; fallar "no se pudo conectar con $URL (¿bash scripts/levantar.sh?)"; }
HTTP="$(cat "$RESPUESTA.http")"; rm -f "$RESPUESTA.http"
[ "$HTTP" = "200" ] || { cat "$RESPUESTA" >&2; fallar "n8n respondió HTTP $HTTP en $URL"; }

if [ "$JSON" = 1 ]; then cat "$RESPUESTA"; exit 0; fi

jq -r '"\n=============== CENTINELA ===============",
       "Reporte   : \(.report_id)   canal: \(.canal // "email")",
       "De        : \(.correo.de.raw // .correo.de.direccion)",
       "Asunto    : \(.correo.asunto // "")",
       "VEREDICTO : \(.veredicto_final)  ->  \(.accion)",
       "Score     : \(.score) / 100 (\(.nivel))   reglas duras: \((.reglas_duras // []) | join(", "))",
       "Motivo    : \((.motivo_veredicto // []) | join(" | "))",
       "IA        : \(if .ia.disponible then "\(.ia.veredicto) (conf \(.ia.confianza)) - \(.ia.resumen)" else "no disponible (\(.ia.error))" end)",
       "MITRE     : \((.ia.mitre_attack // []) | join("; "))",
       "Agente 1  : \(.fuentes.agente_identidad as $a
                      | if $a == null then "sin datos"
                        elif $a.resultados.conclusion == "NO_APLICA" then "no aplica (\($a.resultados.canal)): verifica identidad de correo"
                        elif ($a.estado == "ok" or $a.estado == "parcial") then "\($a.resultados.conclusion) - \($a.resultados.motivo_conclusion // "")"
                        else "no disponible (\($a.nota // $a.estado)): el flujo decidió sin él" end)",
       "Fuentes OK: \((.fuentes_ok // []) | join(", "))",
       "",
       "Hallazgos (\(.n_hallazgos)):",
       (.hallazgos[] | "  [\(.severidad | ascii_upcase)] \(.peso)  \(.tipo)  \(.detalle)")' "$RESPUESTA"
printf '\nReporte en data/reports/%s.json -> Agente 2 y dashboard: %s\n' "$(jq -r .report_id "$RESPUESTA")" "$(url_interfaz)"
