#!/usr/bin/env bash
# =====================================================================================================
#  CENTINELA · levantar el ecosistema — RNF-02, RNF-04
#
#    bash scripts/levantar.sh            # n8n + IA local (Ollama) + Agente 1 + Agente 2 + interfaz
#    bash scripts/levantar.sh --sin-ia   # sin IA: decide el motor de reglas (menos memoria, sin bajar 2 GB)
#  Con DEEPSEEK_API_KEY en .env (IA_PROVEEDOR=auto|deepseek) decide DeepSeek y no se levanta Ollama.
#
#  Idempotente: se puede volver a correr. Reconstruye lo que cambió y vuelve a importar el flujo.
#  Pasos: requisitos -> .env y secretos -> seguridad -> ./data -> imágenes -> contenedores -> salud -> webhooks
# =====================================================================================================
set -euo pipefail
. "$(dirname "$0")/_comun.sh"
cd "$RAIZ"

SIN_IA=0
for arg in "$@"; do
  case "$arg" in
    --sin-ia) SIN_IA=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) fallar "opción desconocida: $arg" ;;
  esac
done
# Proveedor de la IA: --sin-ia manda; si no, IA_PROVEEDOR (auto = deepseek si hay DEEPSEEK_API_KEY).
if [ "$SIN_IA" = 1 ]; then
  PROVEEDOR="ninguno"; export IA_PROVEEDOR=ollama   # el entorno pisa a .env: n8n no llama a DeepSeek aunque haya key
else
  PROVEEDOR="$(env_valor IA_PROVEEDOR auto)"
  [ "$PROVEEDOR" = "auto" ] && { [ -n "$(env_valor DEEPSEEK_API_KEY)" ] && PROVEEDOR="deepseek" || PROVEEDOR="ollama"; }
  case "$PROVEEDOR" in ollama|deepseek) ;; *) fallar "IA_PROVEEDOR inválido: $PROVEEDOR (ollama | deepseek | auto)" ;; esac
fi
USAR_OLLAMA=0; [ "$PROVEEDOR" = "ollama" ] && USAR_OLLAMA=1
OPC_IA=""; [ "$USAR_OLLAMA" = 0 ] && OPC_IA="--sin-ia"   # umbrales de recursos sin Ollama

# ------------------------------------------------------------------------------------------- 1
paso "1/8 Requisitos de la máquina"
if salida="$(bash scripts/preparar_maquina.sh $OPC_IA 2>&1)"; then
  printf '%s\n' "$salida" | grep -F '[!]' || true
  ok "requisitos cumplidos (detalle: bash scripts/preparar_maquina.sh)"
else
  printf '%s\n' "$salida"
  fallar "la máquina no cumple los requisitos"
fi

# ------------------------------------------------------------------------------------------- 2
paso "2/8 Configuración (.env)"
if [ -f .env ]; then ok ".env existente (no se pisa)"; else cp .env.example .env; ok ".env creado desde .env.example"; fi
git check-ignore -q .env 2>/dev/null && ok ".env está en .gitignore" || aviso ".env no figura en .gitignore: no versionarlo"

if [ -z "$(env_valor AGENTE2_TOKEN)" ]; then
  env_escribir AGENTE2_TOKEN "$(aleatorio_hex 24)"
  ok "AGENTE2_TOKEN generado y guardado en .env"
fi

CLAVE_N8N=""
if [ -n "$(env_valor N8N_OWNER_EMAIL)" ] && [ -z "$(env_valor N8N_OWNER_PASSWORD_HASH)" ]; then
  CLAVE_N8N="Centinela-$(aleatorio_hex 10)"
  # El hash lo calcula el propio bcrypt de n8n; la contraseña viaja por variable, no por argumentos.
  hash="$(CLAVE="$CLAVE_N8N" docker_sin_conversion run --rm -e CLAVE --entrypoint sh "docker.n8n.io/n8nio/n8n:$(env_valor N8N_VERSION 2.39.7)" \
    -c 'cd /usr/local/lib/node_modules/n8n && node -e "process.stdout.write(require(\"bcryptjs\").hashSync(process.env.CLAVE, 10))"')"
  case "$hash" in \$2*) ;; *) fallar "no se pudo generar el hash bcrypt del administrador de n8n" ;; esac
  env_escribir N8N_OWNER_PASSWORD_HASH "'$hash'"   # comillas simples: Compose no interpola los `$` del hash
  env_escribir N8N_OWNER_DESDE_ENTORNO true
  ok "administrador de n8n $(env_valor N8N_OWNER_EMAIL): hash guardado en .env (la contraseña se muestra al final, una vez)"
fi

# ------------------------------------------------------------------------------------------- 3
paso "3/8 Seguridad"
BIND="$(env_valor CENTINELA_BIND 127.0.0.1)"
ORIGENES="$(env_valor ORIGENES_CONFIABLES imap)"
if [ "$BIND" != "127.0.0.1" ] && [[ "$ORIGENES" =~ eml_crudo|json_estructurado ]]; then
  [ "$(env_valor CENTINELA_ACEPTO_EXPOSICION)" = 1 ] || fallar "CENTINELA_BIND=$BIND publica webhooks sin autenticación y ORIGENES_CONFIABLES=$ORIGENES confía en lo que se sube: cualquiera en la red podría forjar un correo 'autenticado'. Usar CENTINELA_BIND=127.0.0.1 o ORIGENES_CONFIABLES=imap (forzar: CENTINELA_ACEPTO_EXPOSICION=1)."
  aviso "exposición aceptada explícitamente (CENTINELA_ACEPTO_EXPOSICION=1)"
fi
ok "puertos publicados en $BIND"
[ "$ORIGENES" = "imap" ] && ok "ORIGENES_CONFIABLES=imap (producción)" \
  || aviso "ORIGENES_CONFIABLES=$ORIGENES: perfil DEMO, las muestras las sube esta máquina (ver .env.example)"
case "$PROVEEDOR" in
  deepseek) [ -n "$(env_valor DEEPSEEK_API_KEY)" ] || fallar "IA_PROVEEDOR=deepseek sin DEEPSEEK_API_KEY en .env"
            aviso "IA: DeepSeek ($(env_valor DEEPSEEK_MODEL deepseek-chat)). La evidencia de cada mensaje sale hacia $(env_valor DEEPSEEK_URL https://api.deepseek.com)" ;;
  ollama)   ok "IA: Ollama local ($(env_valor OLLAMA_MODEL llama3.2:3b)), nada sale de la máquina" ;;
  ninguno)  aviso "IA desactivada (--sin-ia): decide el motor de reglas" ;;
esac

# ------------------------------------------------------------------------------------------- 4
paso "4/8 Datos del flujo (./data)"
mkdir -p data/reports data/bitacora
if [ "$(uname -s)" = "Linux" ]; then
  # n8n corre como uid 1000 y escribe ./data; los agentes sólo leen.
  if ! dc run --rm --no-deps -T --entrypoint sh n8n -c 'touch /data/reports/.w && rm /data/reports/.w' >/dev/null 2>&1; then
    dc run --rm --no-deps -T --user 0 --entrypoint chown n8n -R 1000:1000 /data >/dev/null
    ok "permisos de ./data ajustados para n8n (uid 1000)"
  fi
fi
ok "data/reports (reportes) y data/bitacora (bitácora)"

# ------------------------------------------------------------------------------------------- 5
paso "5/8 Imágenes (versiones fijas + build de agentes e interfaz)"
dc config -q || fallar "docker-compose.yml inválido"
SERVICIOS="n8n-importar n8n agente-identidad agente-aprendizaje interfaz"
[ "$USAR_OLLAMA" = 1 ] && SERVICIOS="$SERVICIOS ollama ollama-modelo"
dc pull --ignore-buildable --quiet $SERVICIOS
dc build --quiet agente-identidad agente-aprendizaje interfaz
ok "imágenes listas"

# ------------------------------------------------------------------------------------------- 6
paso "6/8 Contenedores"
if [ "$(estado_servicio n8n)" != "ausente" ]; then
  # El importador escribe la base de n8n: se detiene n8n para que arranque con el flujo recién importado.
  dc stop n8n >/dev/null 2>&1 || true
fi
if [ "$USAR_OLLAMA" = 0 ]; then
  dc rm -s -f ollama ollama-modelo >/dev/null 2>&1 || true   # no se usa: no ocupa memoria
fi
dc up -d --remove-orphans $SERVICIOS

# ------------------------------------------------------------------------------------------- 7
paso "7/8 Salud de cada servicio"
esperar_servicio n8n-importar 240
esperar_servicio agente-identidad 120
esperar_servicio agente-aprendizaje 120
esperar_servicio interfaz 120
esperar_servicio n8n 300
if [ "$PROVEEDOR" = "deepseek" ]; then
  # La key viaja por stdin (curl -K -), no por argumentos visibles en la lista de procesos. /models no consume tokens.
  http="$(printf 'header = "Authorization: Bearer %s"\n' "$(env_valor DEEPSEEK_API_KEY)" \
    | curl -s -o /dev/null -w '%{http_code}' --max-time 20 -K - "$(env_valor DEEPSEEK_URL https://api.deepseek.com)/models" || true)"
  [ "$http" = "200" ] && ok "DeepSeek responde y acepta la key" \
    || fallar "DeepSeek respondió HTTP ${http:-000} (401 = key inválida; 000 = sin salida a Internet desde esta máquina)"
fi
if [ "$USAR_OLLAMA" = 1 ]; then
  esperar_servicio ollama 180
  MODELO="$(env_valor OLLAMA_MODEL llama3.2:3b)"
  aviso "descargando el modelo $MODELO si hace falta (~2 GB la primera vez). Progreso: docker compose logs -f ollama-modelo"
  esperar_servicio ollama-modelo 3600
  curl -sf "$(url_ollama)/api/tags" | jq -e --arg m "$MODELO" '.models[] | select(.name == $m)' >/dev/null \
    && ok "modelo $MODELO disponible" || fallar "el modelo $MODELO no quedó disponible en Ollama"
fi

# ------------------------------------------------------------------------------------------- 8
paso "8/8 Flujo publicado"
# Un GET a un webhook POST publicado responde 'This webhook is not registered for GET requests. Did you mean
# to make a POST request?'; uno sin publicar, 'The requested webhook "GET ..." is not registered.' (los dos dicen GET).
diagnostico_n8n() {
  echo "  --- quién publica el puerto $(env_valor N8N_PUERTO 5678):" >&2
  docker ps --format '    {{.Names}}  {{.Ports}}' | grep ":$(env_valor N8N_PUERTO 5678)->" >&2 || echo "    (ningún contenedor: puede ser un proceso del host; ver: ss -ltnp | grep $(env_valor N8N_PUERTO 5678))" >&2
  echo "  --- importador:" >&2; dc logs --no-log-prefix n8n-importar 2>&1 | tail -n 4 | sed 's/^/    /' >&2
  echo "  --- activación en n8n:" >&2; dc logs --no-log-prefix n8n 2>&1 | grep -iE "activat|problem|error" | tail -n 6 | sed 's/^/    /' >&2
}
publicado="$(dc port n8n 5678 2>/dev/null || true)"
[ "${publicado##*:}" = "$(env_valor N8N_PUERTO 5678)" ] || { diagnostico_n8n; fallar "el n8n de CENTINELA no publica el puerto $(env_valor N8N_PUERTO 5678) (publica: '${publicado:-nada}')"; }
for puerta in analizar whatsapp sms; do
  respuesta="$(curl -s "$(url_n8n)/webhook/centinela/$puerta" || true)"
  if printf '%s' "$respuesta" | grep -q 'not registered for GET'; then ok "webhook POST $(url_n8n)/webhook/centinela/$puerta"
  else
    diagnostico_n8n
    fallar "el webhook centinela/$puerta no está publicado en $(url_n8n). Respuesta: $respuesta"
  fi
done
dc logs n8n 2>&1 | grep -q 'Activated workflow "CENTINELA' && ok "n8n activó el flujo CENTINELA (log)" \
  || aviso "no encontré 'Activated workflow \"CENTINELA' en el log de n8n: docker compose logs n8n | grep -i activ"

cat <<EOF

${VERDE}${NEGRITA}CENTINELA está corriendo.${NORMAL}

  Interfaz (dashboard)   $(url_interfaz)
  n8n (flujo)            $(url_n8n)   usuario: $(env_valor N8N_OWNER_EMAIL "(crear en la UI)")
  Agente 1 · identidad   $(url_agente1)/salud
  Agente 2 · aprendizaje $(url_agente2)/api/salud
  IA                     $(case "$PROVEEDOR" in deepseek) echo "DeepSeek ($(env_valor DEEPSEEK_MODEL deepseek-chat))";; ollama) echo "Ollama local $(url_ollama)  modelo $(env_valor OLLAMA_MODEL llama3.2:3b)";; *) echo "desactivada (--sin-ia)";; esac)
  Datos del flujo        ./data/reports  ./data/bitacora
EOF
if [ -n "$CLAVE_N8N" ]; then
  printf '\n  %sContraseña de n8n (se muestra UNA vez, en .env sólo queda el hash): %s%s\n' "$AMARILLO" "$CLAVE_N8N" "$NORMAL"
fi
cat <<EOF

  Probar una muestra:    bash scripts/analizar.sh samples/phishing_credenciales.json
  Verificación completa: bash scripts/verificar_e2e.sh      (guarda evidencia en ./evidencias)
  Detener:               docker compose stop
  Eliminar todo:         bash scripts/eliminar.sh
EOF
