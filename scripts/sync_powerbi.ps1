# ============================================================
#  sync_powerbi.ps1 - Sincroniza el sugerido desde Power BI
#
#  Uso manual:   ./scripts/sync_powerbi.ps1
#  Programado:   agendar en el Programador de tareas de Windows (ver docs/powerbi-sync.md)
#
#  Requiere las variables POWERBI_* configuradas en el archivo .env de la raiz.
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$venvPy = "$root\apps\api\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "No encuentro el entorno de Python. Ejecuta primero ./setup.ps1" -ForegroundColor Red
    exit 1
}

Push-Location "$root\apps\api"
try {
    & $venvPy -m src.jobs.sync_powerbi
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $code
