# ============================================================
#  setup.ps1 - Instalacion de una sola vez
#  Ejecutar UNA VEZ antes del primer uso:  ./setup.ps1
# ============================================================
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "==> Configurando 'Sugerido de Compras' (primera vez)..." -ForegroundColor Cyan

# 0) .env
if (-not (Test-Path "$root\.env")) {
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host "    .env creado a partir de .env.example" -ForegroundColor Green
}

# 1) Backend: entorno virtual de Python + dependencias
Write-Host "==> [1/4] Backend: creando entorno virtual de Python..." -ForegroundColor Cyan
$py = "python"
& $py --version
if (-not (Test-Path "$root\apps\api\.venv")) {
    & $py -m venv "$root\apps\api\.venv"
}
$venvPy = "$root\apps\api\.venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r "$root\apps\api\requirements.txt"

# 2) Sembrar la base de datos SQLite con datos fake
Write-Host "==> [2/4] Sembrando base de datos con datos de ejemplo..." -ForegroundColor Cyan
Push-Location "$root\apps\api"
& $venvPy -m src.seeds.fake_data
Pop-Location

# 3) Frontend: dependencias de Node
Write-Host "==> [3/4] Frontend: instalando dependencias de Node (puede tardar)..." -ForegroundColor Cyan
Push-Location $root
npm install
Pop-Location

# 4) Listo
Write-Host "==> [4/4] Listo!" -ForegroundColor Green
Write-Host ""
Write-Host "Ahora ejecuta:  ./dev.ps1   para levantar la aplicacion." -ForegroundColor Yellow
Write-Host "Luego abre:     http://localhost:3000" -ForegroundColor Yellow
