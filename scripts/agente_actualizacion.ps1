# ============================================================
#  agente_actualizacion.ps1 - Atiende el boton "Actualizar ahora" de la plataforma
#
#  La plataforma corre en la nube y NO ve los Excel de "Bases de datos", que estan en
#  este PC. Cuando alguien aprieta "Actualizar ahora" en la web, la plataforma solo deja
#  una solicitud anotada. Este script es quien la va a buscar: pregunta cada minuto si
#  hay algo pendiente, corre el motor y devuelve el resultado para que la web lo muestre.
#
#  No lo ejecuta una persona: lo dispara una tarea programada de Windows cada minuto
#  (la crea instalar_agente.ps1). Corre oculto, sin ventanas.
#
#  Uso manual (para probar):
#    .\agente_actualizacion.ps1 -Verboso     -> una pasada, mostrando lo que hace
# ============================================================
param(
    # Muestra en pantalla lo que va haciendo. Sin esto solo escribe en el log.
    [switch]$Verboso
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path $PSScriptRoot -Parent
$logDir = "$root\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = "$logDir\agente_$(Get-Date -Format 'yyyy-MM-dd').log"

function Escribir($texto) {
    $linea = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $texto
    Add-Content -Path $log -Value $linea -Encoding utf8
    if ($Verboso) { Write-Host $linea }
}

# --- Configuracion: se lee del .env (lo deja instalar_agente.ps1) ---
$envFile = "$root\.env"
if (Test-Path $envFile) {
    foreach ($linea in Get-Content $envFile) {
        if ($linea -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
            $valor = $matches[2].Trim().Trim('"').Trim("'")
            if ($valor) { Set-Item -Path "env:$($matches[1])" -Value $valor }
        }
    }
}
$apiUrl = $env:PLATAFORMA_API_URL
if (-not $apiUrl) { $apiUrl = "https://sugerido-api.onrender.com" }
$secreto = $env:AGENTE_SECRET
if (-not $secreto) {
    Escribir "Sin AGENTE_SECRET en el .env: el agente no puede identificarse. Corre instalar_agente.ps1."
    exit 1
}

# Una corrida del motor tarda ~3 min y la tarea despierta cada minuto: sin este candado
# se lanzarian tres motores encima del mismo Excel. La tarea ademas esta configurada
# como IgnorarNueva; el candado cubre el caso de ejecuciones a mano.
$candado = "$root\.agente.lock"
if (Test-Path $candado) {
    $desde = (Get-Item $candado).LastWriteTime
    if ((Get-Date) - $desde -lt [TimeSpan]::FromMinutes(30)) {
        Escribir "Ya hay una corrida en curso (desde $($desde.ToString('HH:mm:ss'))). No hago nada."
        exit 0
    }
    # Candado viejo: quedo de una corrida que murio a medias (se apago el PC).
    Escribir "Candado vencido de las $($desde.ToString('HH:mm:ss')): lo descarto."
    Remove-Item $candado -Force
}

$cabeceras = @{ "X-Agente-Secret" = $secreto }

# --- 1) Hay algo pendiente? ---
try {
    $url = "$apiUrl/api/actualizacion/pendiente?agente=$([uri]::EscapeDataString($env:COMPUTERNAME))"
    $pendiente = Invoke-RestMethod -Uri $url -Headers $cabeceras -Method Get -TimeoutSec 60
}
catch {
    # El servidor gratuito de Render se duerme: el primer intento puede fallar por
    # timeout. Es normal y no vale la pena ensuciar el log todos los minutos.
    Escribir "No pude consultar la plataforma: $($_.Exception.Message)"
    exit 0
}

if (-not $pendiente.hay) {
    if ($Verboso) { Escribir "Sin solicitudes pendientes." }
    exit 0
}

$idSolicitud = $pendiente.id
Escribir "Solicitud $idSolicitud tomada (la pidio $($pendiente.solicitado_por)). Corriendo el motor..."
New-Item -ItemType File -Path $candado -Force | Out-Null

# --- 2) Correr el motor ---
$ok = $false
$mensaje = "El motor no alcanzo a reportar."
try {
    $venvPy = "$root\apps\api\.venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        throw "Falta el entorno de Python en este PC. Hay que correr instalar_agente.ps1."
    }

    Push-Location "$root\apps\api"
    try {
        # Se llama al modulo directo y no a correr_motor.ps1: ese pide confirmar
        # escribiendo SI por teclado, y aca no hay nadie mirando la pantalla.
        $salida = & $venvPy -m src.jobs.correr_motor_real --oficial 2>&1 | ForEach-Object { "$_" }
        $codigo = $LASTEXITCODE
    }
    finally { Pop-Location }

    Add-Content -Path $log -Value $salida -Encoding utf8

    if ($codigo -eq 0) {
        $ok = $true
        # El mensaje va tal cual a la tarjeta de la web, asi que se arma en lenguaje
        # de usuario a partir de lo que el motor imprimio.
        $filas = ($salida | Select-String -Pattern 'CARGA OFICIAL:\s*([\d\.]+)\s*filas' |
                  Select-Object -First 1).Matches.Groups[1].Value
        if ($filas) { $mensaje = "Se publicaron $filas filas." }
        else { $mensaje = "El motor terminó correctamente." }
    }
    else {
        # Los errores utiles del motor salen como "ERROR ..." o como la ultima linea
        # de un traceback; cualquiera de los dos le dice al usuario que revisar.
        $err = ($salida | Select-String -Pattern '^(ERROR|ValueError|FileNotFoundError|.*Error:)' |
                Select-Object -Last 1)
        if (-not $err) { $err = ($salida | Where-Object { $_ -match '\S' } | Select-Object -Last 1) }
        $mensaje = "$err".Trim()
        if ($mensaje.Length -gt 400) { $mensaje = $mensaje.Substring(0, 400) + "…" }
        if (-not $mensaje) { $mensaje = "El motor terminó con error (código $codigo)." }
    }
}
catch {
    $mensaje = $_.Exception.Message
}
finally {
    Remove-Item $candado -Force -ErrorAction SilentlyContinue
}

# --- 3) Reportar el resultado a la plataforma ---
try {
    $cuerpo = @{ id = $idSolicitud; ok = $ok; mensaje = $mensaje } | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri "$apiUrl/api/actualizacion/terminar" -Headers $cabeceras -Method Post `
        -ContentType "application/json" -Body $cuerpo -TimeoutSec 60 | Out-Null
    Escribir "Reportado: ok=$ok - $mensaje"
}
catch {
    # Si no se puede avisar, la solicitud queda "en curso" y la plataforma la cierra
    # sola a los 20 minutos con un aviso. Peor seria dejarla girando para siempre.
    Escribir "No pude reportar el resultado: $($_.Exception.Message)"
}
