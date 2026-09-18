# Levanta CENTINELA completo en Windows: n8n + Ollama + Agente 1 + Agente 2 + interfaz (docker-compose.yml).
# Uso:  .\scripts\levantar_todo.ps1            # con IA local
#       .\scripts\levantar_todo.ps1 -SinIA     # sin Ollama (decide el motor de reglas)
#
# No duplica lógica: ejecuta scripts/levantar.sh con el bash de Git for Windows, que es un requisito
# (ver docs/DESPLIEGUE.md). Así Windows, Linux y macOS corren exactamente los mismos pasos.
param([switch]$SinIA)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot

# El bash de Git for Windows (no el de WSL, que no ve las rutas ni el Docker de la misma forma)
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) { throw "Falta Git for Windows: winget install -e --id Git.Git" }
$bash = Join-Path (Split-Path -Parent (Split-Path -Parent $git.Source)) "bin\bash.exe"
if (-not (Test-Path $bash)) { throw "No encontré el bash de Git for Windows en $bash" }

$argumentos = @((Join-Path $raiz "scripts/levantar.sh"))
if ($SinIA) { $argumentos += "--sin-ia" }
& $bash @argumentos
exit $LASTEXITCODE
