# ============================================================
#  push_to_cloud.ps1 - Empuja el sugerido a la nube (1 clic)
#
#  Lee el Power BI Desktop ABIERTO en este PC y carga los datos en la base
#  de la nube (Supabase). Para usarlo:
#    1. Ten Power BI Desktop abierto con el modelo del sugerido.
#    2. Asegurate de que el .env de la raiz tenga DATABASE_URL apuntando a Supabase.
#    3. Doble clic a este archivo (o ejecutarlo en PowerShell).
#
#  Programar diario: Programador de tareas de Windows (ver docs/deploy.md).
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$venvPy = "$root\apps\api\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "No encuentro el entorno de Python. Ejecuta primero ./setup.ps1" -ForegroundColor Red
    Read-Host "Enter para salir"
    exit 1
}

Write-Host "==> Empujando datos del Power BI a la nube..." -ForegroundColor Cyan
Push-Location "$root\apps\api"
try {
    & $venvPy -m src.jobs.sync_powerbi_desktop
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($code -eq 0) {
    Write-Host "`nListo. Los trabajadores ya ven los datos actualizados." -ForegroundColor Green
}
else {
    Write-Host "`nHubo un problema. Revisa que Power BI Desktop este abierto." -ForegroundColor Red
}
Read-Host "Enter para cerrar"
exit $code
