# ============================================================
#  dev.ps1 - Levanta backend + frontend juntos
#  Uso diario:  ./dev.ps1
#  Detener: cerrar las dos ventanas que se abren, o Ctrl+C en cada una.
# ============================================================
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venvPy = "$root\apps\api\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "No encuentro el entorno de Python. Ejecuta primero:  ./setup.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "==> Levantando BACKEND (http://localhost:8000) ..." -ForegroundColor Cyan
$apiCmd = "cd `"$root\apps\api`"; & `"$venvPy`" -m uvicorn src.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd

Start-Sleep -Seconds 2

Write-Host "==> Levantando FRONTEND (http://localhost:3000) ..." -ForegroundColor Cyan
$webCmd = "cd `"$root`"; npm run dev:web"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $webCmd

Write-Host ""
Write-Host "Backend:  http://localhost:8000/docs" -ForegroundColor Green
Write-Host "Frontend: http://localhost:3000" -ForegroundColor Green
Write-Host ""
Write-Host "Se abrieron dos ventanas de PowerShell (una por servicio)." -ForegroundColor Yellow
Write-Host "Para detener, cierra esas ventanas." -ForegroundColor Yellow
