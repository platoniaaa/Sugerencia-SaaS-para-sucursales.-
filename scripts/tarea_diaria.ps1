# ============================================================
#  tarea_diaria.ps1 - Lo que corre la tarea programada de Windows
#
#  Calcula el sugerido con el motor y lo publica. No pregunta nada (corre sin
#  nadie delante) y deja un log por dia, para poder revisar despues si algo fallo
#  de madrugada.
#
#  Las credenciales salen del .env de la raiz. Si un crudo esta desactualizado el
#  job se niega a cargar: mejor dejar el dato de ayer que publicar uno vencido.
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$logDir = "$root\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = "$logDir\motor_$(Get-Date -Format 'yyyy-MM-dd').log"

"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $log -Append -Encoding utf8
try {
    Push-Location "$root\apps\api"
    & "$root\apps\api\.venv\Scripts\python.exe" -m src.jobs.correr_motor_real --oficial 2>&1 |
        Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($code -eq 0) { "RESULTADO: OK" | Out-File $log -Append -Encoding utf8 }
else { "RESULTADO: FALLO (codigo $code)" | Out-File $log -Append -Encoding utf8 }

# Se borran los logs de mas de 30 dias para que la carpeta no crezca sin fin.
Get-ChildItem $logDir -Filter "motor_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $code
