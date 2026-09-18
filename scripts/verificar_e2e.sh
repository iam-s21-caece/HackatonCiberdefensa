#!/usr/bin/env bash
# =====================================================================================================
#  CENTINELA · verificación de extremo a extremo con evidencia — RNF-05
#
#    bash scripts/verificar_e2e.sh                         # todas las muestras de samples/esperados.json
#    bash scripts/verificar_e2e.sh --muestra samples/legitimo.json [--muestra ...]
#    bash scripts/verificar_e2e.sh --registrar-verdad      # además carga la verdad de cada muestra como
#                                                          # veredicto humano (cierra el bucle de aprendizaje)
#
#  Por muestra, con las hipótesis de samples/esperados.json:
#    C1 flujo      scripts/analizar.sh (el script de Pablo) -> n8n responde con un report_id
#    C2 patrón     veredicto dentro de lo aceptado y reglas duras requeridas presentes
#    C3 reporte    n8n persistió data/reports/<id>.json y no contiene ninguna clave de .env
#    C4 agente 1   correo: analizó (ok/parcial), conclusión aceptada y traza propia (GET /trazas/<id>);
#                  WhatsApp/SMS: NO_APLICA y el agente no tiene traza (no se lo llamó)
#    C5 agente 2   lo percibió en un ciclo AUTÓNOMO (traza ciclos.jsonl, motivo=autonomo) y lo sirve
#    C6 interfaz   el mismo reporte llega al dashboard por nginx (/api/reportes/<id>), sin claves
#  Al final guarda lo que recibe el dashboard de cada endpoint.
#
#  Condiciones controladas: no abrir el dashboard mientras corre (sus consultas dispararían ciclos del
#  Agente 2 y la percepción no quedaría atribuida al ciclo autónomo).
#  Evidencia: evidencias/<fecha UTC>-<commit>/ (entorno.json, resultados.jsonl, resumen.md, respuestas...).
#  Sale con 1 si alguna comprobación falla.
# =====================================================================================================
set -euo pipefail
. "$(dirname "$0")/_comun.sh"
cd "$RAIZ"

REGISTRAR_VERDAD=0; MUESTRAS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --muestra) MUESTRAS+=("${2:?--muestra <archivo>}"); shift 2 ;;
    --registrar-verdad) REGISTRAR_VERDAD=1; shift ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) fallar "opción desconocida: $1" ;;
  esac
done
for h in curl jq docker; do tiene "$h" || fallar "falta $h (bash scripts/preparar_maquina.sh)"; done

ESPERADOS="samples/esperados.json"
A1="$(url_agente1)"; A2="$(url_agente2)"; UI="$(url_interfaz)"
REPORTES_DIR="$(env_valor CENTINELA_REPORTES_DIR ./data/reports)"
ESPERA_A2_S=90   # el Agente 2 revisa cada AGENTE2_INTERVALO_S (10 s por defecto)

# ------------------------------------------------------------------------------------------- 0
paso "0 · Ecosistema"
for s in n8n agente-identidad agente-aprendizaje interfaz; do
  e="$(estado_servicio "$s")"
  [ "$e" = "healthy" ] && ok "$s: $e" || fallar "$s: $e. Primero: bash scripts/levantar.sh"
done
# Proveedor efectivo: lo que recibió el contenedor de n8n (no lo que dice .env)
N8N_ENV="$(docker inspect --format '{{json .Config.Env}}' "$(contenedor n8n)")"
env_n8n() { jq -r --arg k "$1" 'map(select(startswith($k + "="))) | first // "" | sub("^[^=]*="; "")' <<<"$N8N_ENV"; }
PROVEEDOR="$(env_n8n IA_PROVEEDOR)"
[ "$PROVEEDOR" = "auto" ] && { [ -n "$(env_n8n DEEPSEEK_API_KEY)" ] && PROVEEDOR="deepseek" || PROVEEDOR="ollama"; }
IA_ACTIVA=false
case "$PROVEEDOR" in
  deepseek) IA_ACTIVA=true; ok "IA: DeepSeek ($(env_n8n DEEPSEEK_MODEL)), externa" ;;
  *) [ "$(estado_servicio ollama)" = "healthy" ] && IA_ACTIVA=true
     ok "IA: $([ "$IA_ACTIVA" = true ] && echo "Ollama local ($(env_valor OLLAMA_MODEL llama3.2:3b))" || echo "inactiva (decide el motor de reglas)")" ;;
esac
# Valores de las claves configuradas: ninguno puede aparecer en un reporte ni en el dashboard (RNF-03)
SECRETOS=()
for s in VT_API_KEY ABUSEIPDB_API_KEY ABUSECH_API_KEY DEEPSEEK_API_KEY SOC_WEBHOOK_URL AGENTE2_TOKEN; do
  v="$(env_valor "$s")"; [ "${#v}" -ge 8 ] && SECRETOS+=("$v")
done
sin_secretos() { local f="$1" s; for s in "${SECRETOS[@]:-}"; do [ -n "$s" ] && grep -qF -- "$s" "$f" && return 1; done; return 0; }

FECHA="$(date -u +%Y%m%dT%H%M%SZ)"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo sin-git)"
CAMBIOS="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
EVID="evidencias/${FECHA}-${COMMIT}"
[ "$CAMBIOS" != "0" ] && EVID="${EVID}-con-cambios"
mkdir -p "$EVID/respuestas" "$EVID/agente1" "$EVID/agente2" "$EVID/interfaz"
ok "evidencia en $EVID"

# ------------------------------------------------------------------------------------------- entorno
imagen_de() {
  local id; id="$(contenedor "$1")"
  [ -z "$id" ] && { echo null; return; }
  docker image inspect "$(docker inspect --format '{{.Image}}' "$id")" \
    | jq -c '.[0] | {id: .Id, tags: .RepoTags, digests: .RepoDigests, creada: .Created,
                     version: (.Config.Labels["org.opencontainers.image.version"] // null)}'
}
# Configuración real con la que corrió cada contenedor, sin secretos.
config_de() {
  local id; id="$(contenedor "$1")"
  [ -z "$id" ] && { echo null; return; }
  docker inspect --format '{{json .Config.Env}}' "$id" | jq -c '
    map(capture("^(?<k>[^=]+)=(?<v>.*)$")) | map({(.k): .v}) | add
    | with_entries(select(.key | test("^(PATH|HOME|LANG|GPG_KEY|PYTHON_|PYTHONDONTWRITEBYTECODE|PYTHONUNBUFFERED|NODE_|YARN_|NGINX_|NJS_|PKG_|DYNPKG_|ACME_|HOSTNAME|OLLAMA_HOST|LD_LIBRARY|NVIDIA|SHLVL)") | not))
    | with_entries(if (.key | test("TOKEN|KEY|HASH|PASSWORD|SECRET")) then .value = (if .value == "" then "(vacío)" else "(configurado)" end) else . end)'
}
MODELOS=null
[ "$PROVEEDOR" = "ollama" ] && [ "$IA_ACTIVA" = true ] && MODELOS="$(curl -sf "$(url_ollama)/api/tags" | jq -c '[.models[] | {name, digest, size}]' || echo null)"
[ "$PROVEEDOR" = "deepseek" ] && MODELOS="$(jq -nc --arg m "$(env_n8n DEEPSEEK_MODEL)" --arg u "$(env_n8n DEEPSEEK_URL)" '[{name: $m, digest: "no aplica (API externa, versión controlada por el proveedor)", url: $u}]')"
MUESTRAS_SHA="$(jq -r '.muestras[].archivo' "$ESPERADOS" | while read -r f; do printf '{"%s":"%s"}\n' "$f" "$(sha256_de "$f")"; done | jq -sc add)"

jq -n \
  --arg fecha "$FECHA" --arg commit "$(git rev-parse HEAD 2>/dev/null || echo sin-git)" \
  --arg rama "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo sin-git)" --argjson cambios "$CAMBIOS" \
  --arg so "$(uname -srm)" --arg docker "$(docker version --format '{{.Server.Version}}')" \
  --arg compose "$(docker compose version --short)" --arg proyecto "$(dc config --format json | jq -r .name)" \
  --argjson ia "$IA_ACTIVA" --argjson modelos "$MODELOS" --arg proveedor "$PROVEEDOR" \
  --arg flujo_sha "$(sha256_de workflow/centinela_workflow.json)" --arg esperados_sha "$(sha256_de "$ESPERADOS")" \
  --argjson muestras "$MUESTRAS_SHA" \
  --argjson img_n8n "$(imagen_de n8n)" --argjson img_ollama "$(imagen_de ollama)" \
  --argjson img_a1 "$(imagen_de agente-identidad)" --argjson img_a2 "$(imagen_de agente-aprendizaje)" \
  --argjson img_ui "$(imagen_de interfaz)" \
  --argjson cfg_n8n "$(config_de n8n)" --argjson cfg_a1 "$(config_de agente-identidad)" \
  --argjson cfg_a2 "$(config_de agente-aprendizaje)" --argjson cfg_ui "$(config_de interfaz)" \
  '{fecha_utc: $fecha, repositorio: {commit: $commit, rama: $rama, archivos_con_cambios_sin_commit: $cambios},
    maquina: {so: $so, docker: $docker, compose: $compose, proyecto_compose: $proyecto},
    ia: {proveedor: $proveedor, activa: $ia, modelos: $modelos},
    entradas: {flujo_sha256: $flujo_sha, esperados_sha256: $esperados_sha, muestras_sha256: $muestras},
    imagenes: {n8n: $img_n8n, ollama: $img_ollama, agente_identidad: $img_a1, agente_aprendizaje: $img_a2, interfaz: $img_ui},
    configuracion: {n8n: $cfg_n8n, agente_identidad: $cfg_a1, agente_aprendizaje: $cfg_a2, interfaz: $cfg_ui}}' \
  > "$EVID/entorno.json"
ok "entorno registrado (commit, versiones, imágenes, configuración sin secretos, hashes de entradas)"
curl -sf "$A1/salud" > "$EVID/agente1/salud_antes.json" || true

trazas_agente2() { dc exec -T agente-aprendizaje sh -c 'cat /data/agente2/trazas/ciclos.jsonl 2>/dev/null' || true; }

# ------------------------------------------------------------------------------------------- muestras
RESULTADOS="$EVID/resultados.jsonl"; : > "$RESULTADOS"
IDS=()
N="$(jq '.muestras | length' "$ESPERADOS")"
for i in $(seq 0 $((N - 1))); do
  esp="$(jq -c ".muestras[$i]" "$ESPERADOS")"
  archivo="$(jq -r .archivo <<<"$esp")"
  if [ "${#MUESTRAS[@]}" -gt 0 ] && ! printf '%s\n' "${MUESTRAS[@]}" | grep -qxF "$archivo"; then continue; fi
  canal="$(jq -r .canal <<<"$esp")"
  nombre="$(basename "$archivo")"; nombre="${nombre%.*}"
  paso "$nombre · canal $canal · verdad $(jq -r .verdad <<<"$esp")"

  C1=false; C2=false; C3=false; C4=false; C5=false; C6=false; DET=(); RID=""; MOTIVO_A2=null; CICLO_A2=null
  RESP="$EVID/respuestas/$nombre.json"
  t0="$(date +%s)"

  # C1 · el flujo responde (se usa el script de Pablo, tal cual lo usaría un analista)
  if bash scripts/analizar.sh --json "$archivo" > "$RESP" 2> "$EVID/respuestas/$nombre.err" && jq -e '.report_id | length > 0' "$RESP" >/dev/null; then
    RID="$(jq -r .report_id "$RESP")"; C1=true; IDS+=("$RID")
    rm -f "$EVID/respuestas/$nombre.err"
    ok "C1 flujo: report_id $RID ($(( $(date +%s) - t0 )) s)"
  else
    falla "C1 flujo: sin respuesta válida ($(tr '\n' ' ' < "$EVID/respuestas/$nombre.err" | cut -c1-200))"
    DET+=("C1: el flujo no respondió")
  fi
  DURACION=$(( $(date +%s) - t0 ))

  if [ "$C1" = true ]; then
    # C2 · patrón identificado
    veredicto="$(jq -r .veredicto_final "$RESP")"
    faltan_reglas="$(jq -c --argjson e "$esp" '[$e.reglas_duras_requeridas[] as $r | select((.reglas_duras // []) | index($r) | not) | $r]' "$RESP")"
    canal_resp="$(jq -r '.canal // "email"' "$RESP")"
    if jq -e --arg v "$veredicto" '.veredictos_aceptados | index($v)' <<<"$esp" >/dev/null && [ "$faltan_reglas" = "[]" ] && [ "$canal_resp" = "$canal" ]; then
      C2=true; ok "C2 patrón: $veredicto, score $(jq -r .score "$RESP"), reglas duras [$(jq -r '(.reglas_duras // []) | join(", ")' "$RESP")]"
    else
      falla "C2 patrón: veredicto $veredicto (aceptados $(jq -c .veredictos_aceptados <<<"$esp")), faltan reglas $faltan_reglas, canal $canal_resp"
      DET+=("C2: veredicto $veredicto, faltan reglas $faltan_reglas, canal $canal_resp")
    fi

    # C3 · reporte persistido (n8n responde antes de escribir el archivo)
    for _ in $(seq 1 30); do [ -s "$REPORTES_DIR/$RID.json" ] && break; sleep 1; done
    if [ -s "$REPORTES_DIR/$RID.json" ] && jq -e --arg id "$RID" '.report_id == $id' "$REPORTES_DIR/$RID.json" >/dev/null; then
      if sin_secretos "$REPORTES_DIR/$RID.json" && sin_secretos "$RESP"; then
        C3=true; ok "C3 reporte: $REPORTES_DIR/$RID.json (sin claves)"
      else
        falla "C3 reporte: contiene el valor de una clave de .env"; DET+=("C3: el reporte expone una clave")
      fi
    else
      falla "C3 reporte: no apareció $REPORTES_DIR/$RID.json"; DET+=("C3: reporte no persistido")
    fi

    # C4 · Agente 1
    a1_estado="$(jq -r '.fuentes.agente_identidad.estado // "ausente"' "$RESP")"
    a1_concl="$(jq -r '.fuentes.agente_identidad.resultados.conclusion // "ninguna"' "$RESP")"
    a1_traza_http="$(curl -s -o "$EVID/agente1/${nombre}_traza.json" -w '%{http_code}' "$A1/trazas/$RID" || echo 000)"
    acepta_a1="$(jq -r --arg c "$a1_concl" '.agente1_aceptadas | index($c) != null' <<<"$esp")"
    if [ "$canal" = "email" ]; then
      if [[ "$a1_estado" =~ ^(ok|parcial)$ ]] && [ "$acepta_a1" = true ] && [ "$a1_traza_http" = "200" ]; then
        C4=true; ok "C4 agente 1: $a1_concl ($a1_estado) · $(jq -r '.pasos | length? // 0' "$EVID/agente1/${nombre}_traza.json" 2>/dev/null || echo "?") pasos en su traza"
      else
        falla "C4 agente 1: estado $a1_estado, conclusión $a1_concl (aceptadas $(jq -c .agente1_aceptadas <<<"$esp")), traza HTTP $a1_traza_http"
        DET+=("C4: estado $a1_estado, conclusión $a1_concl, traza HTTP $a1_traza_http")
      fi
    else
      rm -f "$EVID/agente1/${nombre}_traza.json"
      if [ "$a1_concl" = "NO_APLICA" ] && [ "$a1_traza_http" = "404" ]; then
        C4=true; ok "C4 agente 1: NO_APLICA en $canal (no se lo llamó: sin traza)"
      else
        falla "C4 agente 1: en $canal se esperaba NO_APLICA sin traza; hay $a1_concl, traza HTTP $a1_traza_http"
        DET+=("C4: $canal con conclusión $a1_concl, traza HTTP $a1_traza_http")
      fi
    fi

    # C5 · Agente 2: percepción en su propio ciclo (sin consultarle nada antes)
    ciclo=""
    for _ in $(seq 1 $((ESPERA_A2_S / 3))); do
      ciclo="$(trazas_agente2 | jq -c --arg id "$RID" 'select(.percibido.nuevos | index($id))' 2>/dev/null | head -n 1)"
      [ -n "$ciclo" ] && break
      sleep 3
    done
    if [ -n "$ciclo" ]; then
      MOTIVO_A2="$(jq -c .motivo <<<"$ciclo")"; CICLO_A2="$(jq -c .ciclo_id <<<"$ciclo")"
      printf '%s\n' "$ciclo" > "$EVID/agente2/${nombre}_ciclo.json"
    fi
    a2_http="$(curl -s -o "$EVID/agente2/${nombre}_detalle.json" -w '%{http_code}' "$A2/api/reportes/$RID" || echo 000)"
    if [ "$MOTIVO_A2" = '"autonomo"' ] && [ "$a2_http" = "200" ] && jq -e --arg id "$RID" '.reporte.report_id == $id' "$EVID/agente2/${nombre}_detalle.json" >/dev/null; then
      C5=true; ok "C5 agente 2: ciclo autónomo $(jq -r . <<<"$CICLO_A2") lo percibió · cola: $(jq -r 'if .prioridad then "prioridad \(.prioridad.prioridad)" else "no prioritario" end' "$EVID/agente2/${nombre}_detalle.json")"
    else
      falla "C5 agente 2: ciclo con el reporte: ${MOTIVO_A2} (se espera \"autonomo\"; ¿dashboard abierto?), detalle HTTP $a2_http"
      DET+=("C5: motivo del ciclo $MOTIVO_A2, detalle HTTP $a2_http")
    fi

    # C6 · el dashboard recibe el reporte (nginx -> Agente 2), con la traza del Agente 1 si es correo
    ui_http="$(curl -s -o "$EVID/interfaz/${nombre}_detalle.json" -w '%{http_code}' "$UI/api/reportes/$RID" || echo 000)"
    traza_ok=true
    [ "$canal" = "email" ] && ! jq -e --arg id "$RID" '.traza_agente1.report_id == $id' "$EVID/interfaz/${nombre}_detalle.json" >/dev/null 2>&1 && traza_ok=false
    sin_secretos "$EVID/interfaz/${nombre}_detalle.json" || { traza_ok=false; DET+=("C6: el dashboard recibe una clave"); }
    if [ "$ui_http" = "200" ] && jq -e --arg id "$RID" --arg v "$veredicto" '.reporte.report_id == $id and .reporte.veredicto_final == $v' "$EVID/interfaz/${nombre}_detalle.json" >/dev/null && [ "$traza_ok" = true ]; then
      C6=true; ok "C6 interfaz: $UI/api/reportes/$RID$([ "$canal" = email ] && echo " (con la traza del Agente 1)")"
    else
      falla "C6 interfaz: HTTP $ui_http, traza del Agente 1 presente: $traza_ok"
      DET+=("C6: HTTP $ui_http, traza del Agente 1: $traza_ok")
    fi
  fi

  jq -nc --argjson esp "$esp" --arg rid "$RID" --argjson dur "$DURACION" \
     --argjson resp "$( [ "$C1" = true ] && cat "$RESP" || echo null )" \
     --argjson c1 "$C1" --argjson c2 "$C2" --argjson c3 "$C3" --argjson c4 "$C4" --argjson c5 "$C5" --argjson c6 "$C6" \
     --argjson motivo "$MOTIVO_A2" --argjson ciclo "$CICLO_A2" \
     --argjson det "$(printf '%s\n' "${DET[@]:-}" | jq -R . | jq -sc 'map(select(length > 0))')" \
     '{muestra: $esp.archivo, canal: $esp.canal, verdad: $esp.verdad, report_id: $rid, duracion_s: $dur,
       veredicto: $resp.veredicto_final, veredicto_esperado: $esp.veredicto_esperado,
       coincide_esperado: ($resp.veredicto_final == $esp.veredicto_esperado),
       score: $resp.score, reglas_duras: $resp.reglas_duras,
       ia: (if $resp then {proveedor: $resp.ia.proveedor, disponible: $resp.ia.disponible, veredicto: $resp.ia.veredicto,
                           confianza: $resp.ia.confianza, modelo: $resp.ia.modelo, error: $resp.ia.error} else null end),
       mitre: $resp.ia.mitre_attack,
       agente1: (if $resp then {estado: $resp.fuentes.agente_identidad.estado, conclusion: $resp.fuentes.agente_identidad.resultados.conclusion} else null end),
       agente2: {ciclo_id: $ciclo, motivo: $motivo},
       comprobaciones: {C1_flujo: $c1, C2_patron: $c2, C3_reporte: $c3, C4_agente1: $c4, C5_agente2: $c5, C6_interfaz: $c6},
       pasa: ($c1 and $c2 and $c3 and $c4 and $c5 and $c6), fallas: $det}' >> "$RESULTADOS"
done
[ -s "$RESULTADOS" ] || fallar "ninguna muestra coincidió con --muestra"

# ------------------------------------------------------------------------------------------- dashboard
paso "Lo que recibe el dashboard (por nginx, igual que el navegador)"
ENDPOINTS=(api/salud api/reportes api/cola api/metricas api/calibracion api/supervision api/actores api/aprendizaje api/attack api/attack/navigator agente1/salud)
UI_ESTADOS="{}"
for ep in "${ENDPOINTS[@]}"; do
  archivo_ep="$EVID/interfaz/$(tr '/' '_' <<<"$ep").json"
  http="$(curl -s -o "$archivo_ep" -w '%{http_code}' "$UI/$ep" || echo 000)"
  UI_ESTADOS="$(jq -c --arg ep "/$ep" --arg h "$http" '. + {($ep): ($h | tonumber)}' <<<"$UI_ESTADOS")"
  [ "$http" = "200" ] && ok "/$ep" || falla "/$ep: HTTP $http"
done
FALTAN_EN_UI="$(jq -c --args '[$ARGS.positional[] as $id | select(map(.report_id) | index($id) | not) | $id]' "$EVID/interfaz/api_reportes.json" "${IDS[@]:-}" 2>/dev/null || echo '["no se pudo leer /api/reportes"]')"
[ "$FALTAN_EN_UI" = "[]" ] && ok "los ${#IDS[@]} reportes de esta corrida están en la lista del dashboard" || falla "faltan en la lista del dashboard: $FALTAN_EN_UI"
sleep 20   # un ciclo de aprendizaje del Agente 1 (15 s) sobre los reportes nuevos
curl -sf "$A1/salud" > "$EVID/agente1/salud_despues.json" || true

# ------------------------------------------------------------------------------------------- verdad
VERDAD_ESTADO=null
if [ "$REGISTRAR_VERDAD" = 1 ]; then
  paso "Veredictos humanos (verdad de cada muestra) -> Agente 2 -> Agente 1"
  TOKEN="$(env_valor AGENTE2_TOKEN)"
  [ -n "$TOKEN" ] || fallar "AGENTE2_TOKEN vacío en .env"
  registrados=0
  while read -r fila; do
    rid="$(jq -r .report_id <<<"$fila")"; [ -z "$rid" ] && continue
    cuerpo="$(jq -c '{veredicto: .verdad, analista: "verificar_e2e", comentario: "verdad de la muestra \(.muestra) (samples/esperados.json)"}' <<<"$fila")"
    http="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$UI/api/reportes/$rid/veredicto" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' --data-binary "$cuerpo" || echo 000)"
    [ "$http" = "201" ] && registrados=$((registrados + 1)) || falla "veredicto de $rid: HTTP $http"
  done < "$RESULTADOS"
  ok "$registrados veredictos registrados por el dashboard (con token)"
  sleep 20
  curl -sf "$UI/api/metricas" > "$EVID/interfaz/api_metricas_con_verdad.json" || true
  curl -sf "$A1/salud" > "$EVID/agente1/salud_con_verdad.json" || true
  VERDAD_ESTADO="$(jq -nc --argjson n "$registrados" '{registrados: $n}')"
fi

# ------------------------------------------------------------------------------------------- resumen
jq -s --argjson ui "$UI_ESTADOS" --argjson faltan "$FALTAN_EN_UI" --argjson verdad "$VERDAD_ESTADO" --slurpfile entorno "$EVID/entorno.json" '
  {muestras: length, pasan: map(select(.pasa)) | length, coinciden_con_lo_esperado: map(select(.coincide_esperado)) | length,
   dashboard: {endpoints: $ui, todos_200: ($ui | to_entries | all(.value == 200)), reportes_faltantes: $faltan},
   verdad_registrada: $verdad, ia_activa: $entorno[0].ia.activa, commit: $entorno[0].repositorio.commit}' "$RESULTADOS" > "$EVID/resumen.json"

{
  echo "# Verificación de extremo a extremo · $FECHA"
  echo
  echo "Generado por \`scripts/verificar_e2e.sh\` (RNF-05). Hipótesis: \`$ESPERADOS\`. Entorno completo: \`entorno.json\`."
  echo
  jq -r '"- Commit: `\(.repositorio.commit)` (\(.repositorio.rama)), archivos con cambios sin commit: \(.repositorio.archivos_con_cambios_sin_commit)",
         "- Máquina: \(.maquina.so) · Docker \(.maquina.docker) · Compose \(.maquina.compose) · proyecto `\(.maquina.proyecto_compose)`",
         "- n8n \(.imagenes.n8n.version // "?") · IA: \(.ia.proveedor) \(if .ia.activa then (.ia.modelos // [] | map("\(.name) (\(.digest[0:12]))") | join(", ")) else "inactiva" end)",
         "- ORIGENES_CONFIABLES del Agente 1: `\(.configuracion.agente_identidad.ORIGENES_CONFIABLES)`"' "$EVID/entorno.json"
  echo
  echo "| Muestra | Canal | Verdad | Veredicto (esperado) | Score | Reglas duras | IA | Agente 1 | Agente 2 | C1 | C2 | C3 | C4 | C5 | C6 | s |"
  echo "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
  jq -r 'def m: if . then "ok" else "**FALLA**" end;
    "| \(.muestra | split("/") | last) | \(.canal) | \(.verdad) | \(.veredicto // "-")\(if .coincide_esperado then "" else " (\(.veredicto_esperado))" end) | \(.score // "-") | \((.reglas_duras // []) | join(", ")) | \(if .ia.disponible then "\(.ia.veredicto) \(.ia.confianza)" else "no" end) | \(.agente1.conclusion // "-") | \(.agente2.motivo // "-") | \(.comprobaciones.C1_flujo | m) | \(.comprobaciones.C2_patron | m) | \(.comprobaciones.C3_reporte | m) | \(.comprobaciones.C4_agente1 | m) | \(.comprobaciones.C5_agente2 | m) | \(.comprobaciones.C6_interfaz | m) | \(.duracion_s) |"' "$RESULTADOS"
  echo
  jq -r '"**\(.pasan) de \(.muestras) muestras pasan las 6 comprobaciones**; \(.coinciden_con_lo_esperado) de \(.muestras) con el veredicto esperado exacto (el resto, dentro de lo aceptado o fallado arriba).",
         "",
         "Dashboard (por nginx): \(if .dashboard.todos_200 then "todos los endpoints respondieron 200" else "endpoints con error: \(.dashboard.endpoints | to_entries | map(select(.value != 200)) | map("\(.key)=\(.value)") | join(", "))" end); reportes de la corrida ausentes en la lista: \(.dashboard.reportes_faltantes | length).",
         (if .verdad_registrada then "Veredictos humanos registrados: \(.verdad_registrada.registrados)." else "Veredictos humanos: no se registraron (usar --registrar-verdad)." end)' "$EVID/resumen.json"
  echo
  jq -r 'select(.pasa | not) | "- `\(.muestra)`: \(.fallas | join("; "))"' "$RESULTADOS"
} > "$EVID/resumen.md"

echo
cat "$EVID/resumen.md"
echo
if jq -e '.pasan == .muestras and .dashboard.todos_200 and (.dashboard.reportes_faltantes | length == 0)' "$EVID/resumen.json" >/dev/null; then
  printf '%sVerificación completa: todo pasó.%s Evidencia: %s\n' "$VERDE" "$NORMAL" "$EVID"
else
  printf '%sLa verificación encontró fallas.%s Evidencia: %s\n' "$ROJO" "$NORMAL" "$EVID"
  exit 1
fi
