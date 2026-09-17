#!/usr/bin/env bash
# Funciones compartidas por los scripts de CENTINELA — RNF-04. Se incluye con `. scripts/_comun.sh`;
# no se ejecuta sola. Funciona en Linux, macOS y Git Bash (Windows).

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Git Bash convierte argumentos con forma de ruta al llamar a un .exe (/workflow/x -> C:/Program Files/Git/workflow/x).
# Para docker hay que desactivarlo (las rutas son del contenedor), pero SÓLO para docker: curl.exe y jq.exe
# necesitan la conversión para escribir y leer archivos locales (p. ej. los de mktemp). Sin efecto en Linux/macOS.
docker_sin_conversion() { MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' docker "$@"; }

# El jq.exe nativo de Windows (winget, releases oficiales) escribe CRLF: `$(jq -r ...)` quedaría con un
# `\r` al final y toda comparación fallaría. Se normaliza la salida sólo en Git Bash / MSYS / Cygwin.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) jq() { command jq "$@" | tr -d '\r'; return "${PIPESTATUS[0]}"; } ;;
esac

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  ROJO=$'\033[31m'; VERDE=$'\033[32m'; AMARILLO=$'\033[33m'; CIAN=$'\033[36m'; GRIS=$'\033[90m'; NEGRITA=$'\033[1m'; NORMAL=$'\033[0m'
else
  ROJO=""; VERDE=""; AMARILLO=""; CIAN=""; GRIS=""; NEGRITA=""; NORMAL=""
fi

paso()   { printf '\n%s==>%s %s%s%s\n' "$CIAN" "$NORMAL" "$NEGRITA" "$*" "$NORMAL"; }
ok()     { printf '  %s[ok]%s %s\n' "$VERDE" "$NORMAL" "$*"; }
aviso()  { printf '  %s[!]%s  %s\n' "$AMARILLO" "$NORMAL" "$*" >&2; }
falla()  { printf '  %s[x]%s  %s\n' "$ROJO" "$NORMAL" "$*" >&2; }
fallar() { printf '\n%s[x] %s%s\n' "$ROJO" "$*" "$NORMAL" >&2; exit 1; }
tiene()  { command -v "$1" >/dev/null 2>&1; }

# Valor de una variable: entorno > .env > defecto. No se hace `source .env`: el hash bcrypt tiene `$`.
env_valor() {
  local nombre="$1" defecto="${2:-}" valor=""
  if [ -n "${!nombre:-}" ]; then printf '%s' "${!nombre}"; return; fi
  if [ -f "$RAIZ/.env" ]; then
    valor="$(grep -E "^${nombre}=" "$RAIZ/.env" | tail -n 1 | cut -d= -f2- | tr -d '\r')" || true
    valor="${valor#\'}"; valor="${valor%\'}"; valor="${valor#\"}"; valor="${valor%\"}"
  fi
  printf '%s' "${valor:-$defecto}"
}

# Reemplaza (o agrega) NOMBRE=valor en .env conservando el orden y los comentarios. Sin `sed -i`
# (difiere entre GNU y BSD).
env_escribir() {
  local nombre="$1" valor="$2" tmp
  tmp="$(mktemp)"
  NOMBRE="$nombre" VALOR="$valor" awk '
    BEGIN { n = ENVIRON["NOMBRE"]; v = ENVIRON["VALOR"]; hecho = 0 }
    index($0, n "=") == 1 { print n "=" v; hecho = 1; next }
    { print }
    END { if (!hecho) print n "=" v }' "$RAIZ/.env" > "$tmp"
  cat "$tmp" > "$RAIZ/.env"
  rm -f "$tmp"
}

# Host para hablar con los puertos publicados desde esta máquina.
host_local() {
  local b; b="$(env_valor CENTINELA_BIND 127.0.0.1)"
  [ "$b" = "0.0.0.0" ] && b="127.0.0.1"
  printf '%s' "$b"
}
url_n8n()      { printf 'http://%s:%s' "$(host_local)" "$(env_valor N8N_PUERTO 5678)"; }
url_ollama()   { printf 'http://%s:%s' "$(host_local)" "$(env_valor OLLAMA_PUERTO 11434)"; }
url_agente1()  { printf 'http://%s:%s' "$(host_local)" "$(env_valor AGENTE1_PUERTO 8101)"; }
url_agente2()  { printf 'http://%s:%s' "$(host_local)" "$(env_valor AGENTE2_PUERTO 8102)"; }
url_interfaz() { printf 'http://%s:%s' "$(host_local)" "$(env_valor INTERFAZ_PUERTO 8088)"; }

dc() { (cd "$RAIZ" && docker_sin_conversion compose "$@"); }

# ID del contenedor de un servicio (incluye los que ya terminaron).
contenedor() { dc ps -a -q "$1" 2>/dev/null | head -n 1; }

# Estado de un servicio: healthy | unhealthy | starting | running | exited:<código> | ausente
estado_servicio() {
  local id; id="$(contenedor "$1")"
  [ -z "$id" ] && { printf 'ausente'; return; }
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else if eq .State.Status "exited"}}exited:{{.State.ExitCode}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null || printf 'ausente'
}

# Espera a que un servicio quede sano (o, si es de una sola vez, termine con código 0).
esperar_servicio() {
  local servicio="$1" limite_s="${2:-180}" inicio estado
  inicio="$(date +%s)"
  while :; do
    estado="$(estado_servicio "$servicio")"
    case "$estado" in
      healthy|exited:0) ok "$servicio: $estado"; return 0 ;;
      exited:*|unhealthy) falla "$servicio: $estado (docker compose logs $servicio)"; return 1 ;;
    esac
    if [ $(( $(date +%s) - inicio )) -ge "$limite_s" ]; then
      falla "$servicio: sigue en '$estado' después de ${limite_s}s (docker compose logs $servicio)"; return 1
    fi
    sleep 3
  done
}

sha256_de() {
  if tiene sha256sum; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

# Aleatorio hexadecimal sin tuberías que corten con SIGPIPE (set -o pipefail).
aleatorio_hex() { od -An -N"${1:-24}" -tx1 /dev/urandom | tr -d ' \n'; }
