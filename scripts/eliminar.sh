#!/usr/bin/env bash
# =====================================================================================================
#  CENTINELA · eliminar el ecosistema de esta máquina — RNF-04
#
#    bash scripts/eliminar.sh              # contenedores, red, volúmenes (base de n8n, modelo de IA, datos
#                                          # de los agentes) e imágenes del proyecto
#    bash scripts/eliminar.sh --datos      # además borra ./data/reports y ./data/bitacora
#    bash scripts/eliminar.sh --todo       # además .env y ./evidencias y las imágenes base del build
#                                          # (python, node, nginx) si ningún otro contenedor las usa
#
#  No toca contenedores, volúmenes ni imágenes de otros proyectos. Pide confirmación (salvo -y).
# =====================================================================================================
set -euo pipefail
. "$(dirname "$0")/_comun.sh"
cd "$RAIZ"

DATOS=0; TODO=0; SI=0
for arg in "$@"; do
  case "$arg" in
    --datos) DATOS=1 ;;
    --todo) DATOS=1; TODO=1 ;;
    -y|--si) SI=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) fallar "opción desconocida: $arg" ;;
  esac
done

PROYECTO="$(dc config --format json 2>/dev/null | jq -r .name)"
echo "Se va a eliminar el proyecto Compose '${PROYECTO}': contenedores, red, volúmenes (incluye el modelo de IA"
echo "y lo aprendido por los agentes) e imágenes de sus servicios."
[ "$DATOS" = 1 ] && echo "También: ./data/reports y ./data/bitacora."
[ "$TODO" = 1 ] && echo "También: .env (token y hash del administrador), ./evidencias e imágenes base del build."
if [ "$SI" = 0 ]; then
  read -r -p "¿Continuar? [s/N] " r
  [[ "$r" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }
fi

if [ "$DATOS" = 1 ]; then
  paso "Datos del flujo"
  # n8n los escribe como uid 1000: en Linux puede hacer falta borrarlos con su propia imagen (antes de quitarla).
  find data/reports data/bitacora -type f ! -name .gitkeep -delete 2>/dev/null     || dc run --rm --no-deps -T --user 0 --entrypoint sh n8n -c 'find /data/reports /data/bitacora -type f ! -name .gitkeep -delete'
  ok "data/reports y data/bitacora vacíos"
fi

paso "Contenedores, red, volúmenes e imágenes del proyecto"
dc down --volumes --rmi all --remove-orphans
ok "proyecto $PROYECTO eliminado"

if [ "$TODO" = 1 ]; then
  paso "Configuración, evidencias e imágenes base"
  rm -f .env && ok ".env eliminado"
  find evidencias -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} + 2>/dev/null || true
  ok "evidencias locales eliminadas (evidencias/README.md queda)"
  for base in python:3.13-slim node:22-alpine nginx:1.27-alpine; do
    if docker image inspect "$base" >/dev/null 2>&1; then
      docker rmi "$base" >/dev/null 2>&1 && ok "imagen base $base" || aviso "$base la usa otro contenedor o imagen: se deja"
    fi
  done
  aviso "la caché de build de Docker no se borra sola (es compartida con otros proyectos): docker builder prune"
fi
