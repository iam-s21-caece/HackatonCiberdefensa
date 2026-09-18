# Envía un correo (JSON estructurado o .eml crudo) a CENTINELA y muestra el veredicto.
# Uso:  .\scripts\analizar.ps1 .\samples\phishing_credenciales.json
#       .\scripts\analizar.ps1 .\samples\phishing_reembolso.eml
param(
    [Parameter(Mandatory = $true)][string]$Archivo,
    [string]$Url = "",
    [ValidateSet("", "email", "whatsapp", "sms")][string]$Canal = ""
)
$ErrorActionPreference = "Stop"
$Archivo = (Resolve-Path $Archivo).Path
# Puerta de entrada según el canal: se deduce del nombre del archivo (whatsapp_*.json / sms_*.json) salvo que se indique
if (-not $Canal) { $Canal = if ($Archivo -match "whatsapp") { "whatsapp" } elseif ($Archivo -match "sms") { "sms" } else { "email" } }
if (-not $Url) { $Url = "http://localhost:5678/webhook/centinela/" + $(if ($Canal -eq "email") { "analizar" } else { $Canal }) }
if ($Archivo -like "*.eml") {
    $raw = [System.IO.File]::ReadAllText($Archivo)
    $body = @{ raw = $raw } | ConvertTo-Json -Compress
} else {
    $body = Get-Content $Archivo -Raw -Encoding utf8
}
$t0 = Get-Date
$r = Invoke-RestMethod -Method Post -Uri $Url -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 600
$dt = [int]((Get-Date) - $t0).TotalSeconds

Write-Host ""
Write-Host "=============== CENTINELA ===============" -ForegroundColor Cyan
Write-Host ("Reporte    : {0}   ({1}s)   canal: {2}" -f $r.report_id, $dt, $r.canal)
Write-Host ("De         : {0}" -f $r.correo.de.raw)
Write-Host ("Asunto     : {0}" -f $r.correo.asunto)
$color = switch ($r.veredicto_final) { "VERDADERO_POSITIVO" { "Red" } "ESCALAR" { "Yellow" } default { "Green" } }
Write-Host ("VEREDICTO  : {0}  ->  {1}" -f $r.veredicto_final, $r.accion) -ForegroundColor $color
Write-Host ("Score      : {0} / 100  ({1})   reglas duras: {2}" -f $r.score, $r.nivel, ($r.reglas_duras -join ", "))
Write-Host ("Motivo     : {0}" -f ($r.motivo_veredicto -join " | "))
if ($r.ia.disponible) {
    Write-Host ("IA ({0}) : {1} (confianza {2}) - {3}" -f $r.ia.modelo, $r.ia.veredicto, $r.ia.confianza, $r.ia.resumen) -ForegroundColor Magenta
    if ($r.ia.mitre_attack) { Write-Host ("MITRE      : {0}" -f ($r.ia.mitre_attack -join "; ")) }
    if ($r.ia.mensaje_para_usuario) { Write-Host ("Al usuario : {0}" -f $r.ia.mensaje_para_usuario) }
} else { Write-Host ("IA         : no disponible ({0})" -f $r.ia.error) -ForegroundColor DarkGray }
$a1 = $r.fuentes.agente_identidad
if (-not $a1) { Write-Host "Agente 1   : sin datos" -ForegroundColor DarkGray }
elseif ($a1.resultados.conclusion -eq "NO_APLICA") { Write-Host ("Agente 1   : no aplica ({0}): verifica identidad de correo" -f $a1.resultados.canal) -ForegroundColor DarkGray }
elseif ($a1.estado -in @("ok", "parcial")) { Write-Host ("Agente 1   : {0} - {1}" -f $a1.resultados.conclusion, $a1.resultados.motivo_conclusion) -ForegroundColor Cyan }
else { Write-Host ("Agente 1   : no disponible ({0}): el flujo decidio sin el" -f $(if ($a1.nota) { $a1.nota } else { $a1.estado })) -ForegroundColor DarkGray }
Write-Host ("Fuentes OK : {0}" -f ($r.fuentes_ok -join ", "))
if ($r.fuentes_sin_key) { Write-Host ("Sin key    : {0}" -f ($r.fuentes_sin_key -join ", ")) -ForegroundColor DarkGray }
Write-Host ""
Write-Host ("Hallazgos ({0}):" -f $r.n_hallazgos)
foreach ($h in $r.hallazgos) {
    $c = switch ($h.severidad) { "critica" { "Red" } "alta" { "DarkYellow" } "media" { "Yellow" } "baja" { "Gray" } default { "DarkGray" } }
    Write-Host ("  [{0,-7}] {1,3}  {2,-32} {3}" -f $h.severidad.ToUpper(), $h.peso, $h.tipo, $h.detalle) -ForegroundColor $c
}
