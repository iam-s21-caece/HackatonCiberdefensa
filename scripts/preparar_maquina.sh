#!/usr/bin/env bash
# =====================================================================================================
#  CENTINELA · preparar una máquina — RNF-04
#
#  Verifica que la máquina pueda correr el ecosistema y dice cómo instalar lo que falta.
#
#    ./scripts/preparar_maquina.sh              # sólo verifica (no cambia nada)
#    ./scripts/preparar_maquina.sh --instalar   # instala lo que falta: apt/dnf (con sudo), brew o winget
#    ./scripts/preparar_maquina.sh --sin-ia     # umbrales de recursos sin Ollama
#
#  Sale con 1 si falta algo imprescindible. Ver docs/DESPLIEGUE.md § Verificado en.
# =====================================================================================================
set -euo pipefail
. "$(dirname "$0")/_comun.sh"

INSTALAR=0; SIN_IA=0
for arg in "$@"; do
  case "$arg" in
    --instalar) INSTALAR=1 ;;
    --sin-ia) SIN_IA=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) fallar "opción desconocida: $arg" ;;
  esac
done

# Mínimos (ver docs/DESPLIEGUE.md § Requisitos)
COMPOSE_MIN="2.24.0"
MEMORIA_MIN_GB=$([ "$SIN_IA" = 1 ] && echo 3 || echo 6)
DISCO_MIN_GB=$([ "$SIN_IA" = 1 ] && echo 6 || echo 15)
FALTANTES=0

# ------------------------------------------------------------------------------------------- sistema
SO="desconocido"; DISTRO=""
case "$(uname -s)" in
  Linux*)
    if grep -qi microsoft /proc/version 2>/dev/null; then SO="wsl"; else SO="linux"; fi
    [ -r /etc/os-release ] && DISTRO="$(. /etc/os-release && echo "${ID:-}:${ID_LIKE:-}")"
    ;;
  Darwin*) SO="macos" ;;
  MINGW*|MSYS*|CYGWIN*) SO="windows" ;;
esac

gestor() {
  case "$SO" in
    linux|wsl)
      case "$DISTRO" in
        *debian*|*ubuntu*) echo apt ;;
        *fedora*|*rhel*|*centos*) echo dnf ;;
        *arch*) echo pacman ;;
        *) echo "" ;;
      esac ;;
    macos) tiene brew && echo brew || echo "" ;;
    windows) tiene winget && echo winget || echo "" ;;
  esac
}
GESTOR="$(gestor)"

# Comando de instalación de referencia por herramienta y gestor (vacío = no hay uno desatendido).
comando_instalar() {
  case "$GESTOR:$1" in
    apt:docker|dnf:docker) echo 'curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker "$USER"' ;;
    pacman:docker) echo 'sudo pacman -S --needed docker docker-compose docker-buildx && sudo systemctl enable --now docker && sudo usermod -aG docker "$USER"' ;;
    apt:*) echo "sudo apt-get update && sudo apt-get install -y $1" ;;
    dnf:*) echo "sudo dnf install -y $1" ;;
    pacman:*) echo "sudo pacman -S --needed $1" ;;
    brew:docker) echo "brew install --cask docker" ;;
    brew:*) echo "brew install $1" ;;
    winget:git) echo "winget install -e --id Git.Git" ;;
    winget:jq) echo "winget install -e --id jqlang.jq" ;;
    *) echo "" ;;
  esac
}

# Cómo hacerlo a mano: comando + nota, o la página oficial de descarga.
como_instalar() {
  local cmd; cmd="$(comando_instalar "$1")"
  case "$GESTOR:$1" in
    apt:docker|dnf:docker|pacman:docker) echo "$cmd  (después cerrar sesión y volver a entrar)"; return ;;
    brew:docker) echo "$cmd  (abrir Docker Desktop una vez)"; return ;;
    winget:docker) echo "winget install -e --id Docker.DockerDesktop  (requiere WSL 2, reiniciar y abrir Docker Desktop)"; return ;;
    winget:jq|winget:git) echo "$cmd  (abrir una terminal nueva)"; return ;;
  esac
  if [ -n "$cmd" ]; then echo "$cmd"; return; fi
  case "$1" in
    docker) echo "https://docs.docker.com/get-started/get-docker/" ;;
    jq) echo "https://jqlang.org/download/" ;;
    git) echo "https://git-scm.com/downloads" ;;
    curl) echo "https://curl.se/download.html" ;;
  esac
}

instalar() {
  local cmd; cmd="$(comando_instalar "$1")"
  [ "$INSTALAR" = 1 ] && [ -n "$cmd" ] || return 1
  paso "Instalando $1: $cmd"
  bash -c "$cmd"
}

# Compara versiones x.y.z: devuelve 0 si $1 >= $2
version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -t. -k1,1n -k2,2n -k3,3n | head -n 1)" = "$2" ]; }

requerir() {
  local h="$1" para="$2"
  if tiene "$h"; then ok "$h — $para"; return 0; fi
  if instalar "$h" && tiene "$h"; then ok "$h instalado — $para"; return 0; fi
  falla "$h no está — $para. Instalar: $(como_instalar "$h")"
  FALTANTES=$((FALTANTES + 1))
}

paso "Sistema: $SO${DISTRO:+ ($DISTRO)}${GESTOR:+ · gestor de paquetes: $GESTOR}"

paso "Herramientas"
requerir git "clonar el repositorio"
requerir curl "los scripts hablan HTTP con n8n y los agentes"
requerir jq "los scripts leen las respuestas JSON"
requerir docker "todos los componentes corren en contenedores"

paso "Docker"
if tiene docker; then
  if docker info >/dev/null 2>&1; then
    ok "el daemon responde ($(docker version --format '{{.Server.Version}}' 2>/dev/null))"
    if docker compose version >/dev/null 2>&1; then
      v="$(docker compose version --short 2>/dev/null | sed 's/^v//')"
      if version_ge "$v" "$COMPOSE_MIN"; then ok "Docker Compose $v (>= $COMPOSE_MIN)"
      else falla "Docker Compose $v: se necesita >= $COMPOSE_MIN. Actualizar Docker"; FALTANTES=$((FALTANTES + 1)); fi
    else
      falla "falta el plugin Docker Compose v2: $(como_instalar docker)"; FALTANTES=$((FALTANTES + 1))
    fi

    mem_gb=$(( $(docker info --format '{{.MemTotal}}') / 1024 / 1024 / 1024 ))
    cpus="$(docker info --format '{{.NCPU}}')"
    if [ "$mem_gb" -ge "$MEMORIA_MIN_GB" ]; then ok "memoria para contenedores: ${mem_gb} GB (>= ${MEMORIA_MIN_GB})"
    else aviso "memoria para contenedores: ${mem_gb} GB (< ${MEMORIA_MIN_GB}). $([ "$SIN_IA" = 1 ] && echo "Puede fallar." || echo "La IA local puede no entrar: usar --sin-ia o darle más memoria a Docker.")"; fi
    if [ "$cpus" -ge 4 ]; then ok "CPUs para contenedores: $cpus"; else aviso "CPUs para contenedores: $cpus (recomendado >= 4; la IA en CPU tarda 1-2 min por muestra)"; fi
  else
    falla "Docker está instalado pero el daemon no responde. Abrir Docker Desktop, o: sudo systemctl start docker"
    [ "$SO" = linux ] && aviso "si es un problema de permisos: sudo usermod -aG docker \"\$USER\" y volver a iniciar sesión"
    FALTANTES=$((FALTANTES + 1))
  fi
fi

paso "Disco y puertos"
libre_gb=$(( $(df -Pk "$RAIZ" | awk 'NR==2 {print $4}') / 1024 / 1024 ))
if [ "$libre_gb" -ge "$DISCO_MIN_GB" ]; then ok "disco libre: ${libre_gb} GB (>= ${DISCO_MIN_GB}: imágenes$([ "$SIN_IA" = 1 ] || echo " + modelo de IA"))"
else aviso "disco libre: ${libre_gb} GB (< ${DISCO_MIN_GB}). Docker Desktop guarda las imágenes en su propio disco virtual."; fi

for par in N8N_PUERTO:5678 OLLAMA_PUERTO:11434 AGENTE1_PUERTO:8101 AGENTE2_PUERTO:8102 INTERFAZ_PUERTO:8088; do
  var="${par%%:*}"; puerto="$(env_valor "$var" "${par##*:}")"
  [ "$SIN_IA" = 1 ] && [ "$var" = OLLAMA_PUERTO ] && continue
  if (exec 3<>"/dev/tcp/127.0.0.1/$puerto") 2>/dev/null; then
    # Si lo publica un contenedor de este mismo proyecto, no es un conflicto.
    if tiene docker && dc ps --format '{{.Ports}}' 2>/dev/null | grep -q ":$puerto->"; then
      ok "puerto $puerto en uso por CENTINELA (ya levantado)"
    else
      aviso "puerto $puerto ocupado por otro proceso: definir $var=<otro puerto> en .env"
    fi
  else
    ok "puerto $puerto libre ($var)"
  fi
done

paso "Repositorio"
if grep -lI $'\r' "$RAIZ"/scripts/*.sh >/dev/null 2>&1; then
  falla "scripts con fin de línea CRLF (checkout anterior a .gitattributes). Corregir: rm scripts/*.sh && git checkout -- scripts/  (o volver a clonar)"
  FALTANTES=$((FALTANTES + 1))
else
  ok "scripts con fin de línea LF"
fi
[ -f "$RAIZ/workflow/centinela_workflow.json" ] && ok "flujo versionado: workflow/centinela_workflow.json" || { falla "falta workflow/centinela_workflow.json (python workflow/build_workflow.py)"; FALTANTES=$((FALTANTES + 1)); }

echo
if [ "$FALTANTES" -gt 0 ]; then
  fallar "faltan $FALTANTES requisito(s). $([ "$INSTALAR" = 0 ] && echo "Probar: ./scripts/preparar_maquina.sh --instalar")"
fi
printf '%sMáquina lista.%s Siguiente paso: ./scripts/levantar.sh%s\n' "$VERDE" "$NORMAL" "$([ "$SIN_IA" = 1 ] && echo " --sin-ia")"
