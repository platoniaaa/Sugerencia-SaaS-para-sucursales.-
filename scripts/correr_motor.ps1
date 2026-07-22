# ============================================================
#  correr_motor.ps1 - Calcula el sugerido y lo publica (1 clic)
#
#  Reemplaza a push_to_cloud.ps1: ese leia el Power BI Desktop abierto en este PC;
#  este lee los Excel de la carpeta de datos y calcula el sugerido con el motor,
#  sin necesitar Power BI.
#
#  Uso:
#    .\correr_motor.ps1              -> modo SOMBRA: compara contra lo que hay
#                                       publicado y guarda un reporte. No toca lo
#                                       que ven los compradores.
#    .\correr_motor.ps1 -Oficial     -> CARGA de verdad. Esto si cambia la
#                                       plataforma para todo el equipo.
#
#  Credenciales: se leen del .env de la raiz (PLATAFORMA_EMAIL / PLATAFORMA_PASSWORD
#  / PLATAFORMA_API_URL). Si no estan, las pide y NO las guarda.
# ============================================================
param(
    [switch]$Oficial,
    [switch]$IgnorarFrescura
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$venvPy = "$root\apps\api\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "No encuentro el entorno de Python. Ejecuta primero ./setup.ps1" -ForegroundColor Red
    Read-Host "Enter para salir"
    exit 1
}

# --- Credenciales: del .env si estan, si no se piden ---
$envFile = "$root\.env"
if (Test-Path $envFile) {
    foreach ($linea in Get-Content $envFile) {
        if ($linea -match '^\s*(PLATAFORMA_[A-Z_]+)\s*=\s*(.*)$') {
            $valor = $matches[2].Trim().Trim('"').Trim("'")
            if ($valor) { Set-Item -Path "env:$($matches[1])" -Value $valor }
        }
    }
}
if (-not $env:PLATAFORMA_API_URL) { $env:PLATAFORMA_API_URL = "https://sugerido-api.onrender.com" }
if (-not $env:PLATAFORMA_EMAIL) {
    $env:PLATAFORMA_EMAIL = Read-Host "Correo de la plataforma"
}
if (-not $env:PLATAFORMA_PASSWORD) {
    # Se pide oculta y queda solo en memoria de este proceso.
    $sec = Read-Host "Clave de $($env:PLATAFORMA_EMAIL)" -AsSecureString
    $env:PLATAFORMA_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}

$modo = if ($Oficial) { "CARGA OFICIAL" } else { "modo sombra (no toca la plataforma)" }
Write-Host "==> Calculando el sugerido con el motor - $modo" -ForegroundColor Cyan
if ($Oficial) {
    Write-Host "    Esto cambia lo que ve todo el equipo." -ForegroundColor Yellow
    if ((Read-Host "    Escribe SI para continuar") -ne "SI") {
        Write-Host "Cancelado." -ForegroundColor Yellow
        exit 0
    }
}

$argumentos = @("-m", "src.jobs.correr_motor_real")
if ($Oficial) { $argumentos += "--oficial" }
if ($IgnorarFrescura) { $argumentos += "--ignorar-frescura" }

Push-Location "$root\apps\api"
try {
    & $venvPy @argumentos
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
    # Que la clave no quede en el entorno despues de correr.
    Remove-Item env:PLATAFORMA_PASSWORD -ErrorAction SilentlyContinue
}

if ($code -eq 0) {
    if ($Oficial) { Write-Host "`nListo. Los compradores ya ven los datos nuevos." -ForegroundColor Green }
    else { Write-Host "`nListo. Mira el resultado en 'Cargar datos' de la plataforma." -ForegroundColor Green }
}
else {
    Write-Host "`nHubo un problema. Revisa el detalle de arriba." -ForegroundColor Red
}
Read-Host "Enter para cerrar"
exit $code
