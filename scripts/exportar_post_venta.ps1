# ============================================================
#  exportar_post_venta.ps1 - Exporta la Planilla Post Venta a Excel (1 clic)
#
#  Lee el Power BI Desktop ABIERTO en este PC y genera un Excel de la
#  "Planilla Post Venta", filtrado por periodo y (opcional) sucursal.
#  El archivo se guarda en el Escritorio y se abre solo al terminar.
#
#  Uso: doble clic. Te pregunta el periodo (AAAAMM) y la sucursal.
#       Enter en todo = ultimos 12 meses, todas las sucursales.
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$venvPy = "$root\apps\api\.venv\Scripts\python.exe"
$motor = "$PSScriptRoot\exportar_post_venta.py"

if (-not (Test-Path $venvPy)) {
    Write-Host "No encuentro el entorno de Python. Ejecuta primero ./setup.ps1" -ForegroundColor Red
    Read-Host "Enter para salir"; exit 1
}

Write-Host "=== Exportar Planilla Post Venta a Excel ===" -ForegroundColor Cyan
Write-Host "Asegurate de tener Power BI Desktop ABIERTO con el modelo del sugerido." -ForegroundColor Yellow
Write-Host ""
Write-Host "Formato de periodo: AAAAMM (ej. 202505 = mayo 2025). Enter = valor por defecto." -ForegroundColor DarkGray

$desde = Read-Host "Periodo DESDE (Enter = hace 12 meses)"
$hasta = Read-Host "Periodo HASTA (Enter = mes actual)"
$sucursal = Read-Host "Sucursal (Enter = todas; ej. RANCAGUA, TALCA, CURICO)"

# Nombre de archivo en el Escritorio.
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$desk = [Environment]::GetFolderPath("Desktop")
$salida = Join-Path $desk "planilla_post_venta_$stamp.xlsx"

# Argumentos (solo se pasan los que el usuario completo).
$argumentos = @($motor, "--salida", $salida)
if ($desde.Trim())    { $argumentos += @("--desde", $desde.Trim()) }
if ($hasta.Trim())    { $argumentos += @("--hasta", $hasta.Trim()) }
if ($sucursal.Trim()) { $argumentos += @("--sucursal", $sucursal.Trim()) }

Write-Host ""
Write-Host "Generando... (puede tardar segundos a un par de minutos segun el tamano)" -ForegroundColor Cyan
& $venvPy @argumentos
$code = $LASTEXITCODE

if ($code -eq 0 -and (Test-Path $salida)) {
    Write-Host ""
    Write-Host "Listo. Archivo: $salida" -ForegroundColor Green
    Invoke-Item $salida          # abre el Excel
}
else {
    Write-Host ""
    Write-Host "No se genero el archivo. Revisa que Power BI Desktop este abierto y el periodo." -ForegroundColor Red
}
Read-Host "Enter para cerrar"
exit $code
