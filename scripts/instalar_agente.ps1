# ============================================================
#  instalar_agente.ps1 - Deja este PC atendiendo el boton "Actualizar ahora"
#
#  Se corre UNA VEZ, en el computador que tiene la carpeta "Bases de datos".
#  Hace todo: instala Python si falta, arma el entorno, pregunta los 3 datos que
#  necesita, guarda la configuracion y deja la tarea de Windows que revisa cada
#  minuto si alguien apreto el boton en la web.
#
#  Forma facil de ejecutarlo: doble clic en INSTALAR AGENTE.cmd (esta al lado).
# ============================================================
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path $PSScriptRoot -Parent
$TAREA = "Sugerido Curifor - Agente"

function Titulo($t) { Write-Host "`n==> $t" -ForegroundColor Cyan }
function Bien($t)   { Write-Host "    OK  $t" -ForegroundColor Green }
function Ojo($t)    { Write-Host "    !   $t" -ForegroundColor Yellow }

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Sugerido de Compras - instalar el agente" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Este computador va a quedar atendiendo el boton 'Actualizar ahora' de la"
Write-Host "plataforma. Toma unos minutos y se hace una sola vez."

# ------------------------------------------------------------------ 1) Python
Titulo "[1/5] Python"
$py = $null
foreach ($cmd in @("python", "py")) {
    try {
        $v = & $cmd --version 2>&1
        if ($v -match "Python 3\.(\d+)" -and [int]$matches[1] -ge 10) { $py = $cmd; break }
    } catch { }
}
if (-not $py) {
    Ojo "No hay Python instalado. Lo instalo con winget (puede tardar unos minutos)."
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    # winget deja el nuevo PATH en el registro, no en esta ventana.
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
    foreach ($cmd in @("python", "py")) {
        try { if ((& $cmd --version 2>&1) -match "Python 3") { $py = $cmd; break } } catch { }
    }
    if (-not $py) {
        Write-Host "`nPython quedo instalado pero esta ventana no lo ve todavia." -ForegroundColor Yellow
        Write-Host "Cierra esta ventana y vuelve a ejecutar el instalador." -ForegroundColor Yellow
        Read-Host "Enter para salir"; exit 1
    }
}
Bien "$(& $py --version)"

# ------------------------------------------------------- 2) Entorno del motor
Titulo "[2/5] Preparando el motor (esto es lo que mas tarda)"
$venvPy = "$root\apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { & $py -m venv "$root\apps\api\.venv" }
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r "$root\apps\api\requirements.txt" --quiet
Bien "Motor listo"

# --------------------------------------------------------- 3) Los tres datos
Titulo "[3/5] Configuracion"

# Carpeta de los Excel: se elige con el explorador, no escribiendo la ruta a mano.
Add-Type -AssemblyName System.Windows.Forms
Write-Host "    Elige la carpeta 'Bases de datos' (donde estan los Excel)..."
$dlg = New-Object System.Windows.Forms.FolderBrowserDialog
$dlg.Description = "Carpeta 'Bases de datos' con los Excel del sugerido"
$dlg.ShowNewFolderButton = $false
if ($dlg.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
    Write-Host "Cancelado: sin esa carpeta el motor no puede calcular." -ForegroundColor Red
    Read-Host "Enter para salir"; exit 1
}
$crudos = $dlg.SelectedPath
$nExcel = (Get-ChildItem -Path $crudos -Filter *.xlsx -Recurse -ErrorAction SilentlyContinue).Count
if ($nExcel -eq 0) { Ojo "En esa carpeta no veo ningun .xlsx. Revisa que sea la correcta." }
else { Bien "$nExcel archivos Excel encontrados" }

Write-Host ""
Write-Host "    Ahora la cuenta de la plataforma que va a publicar los datos."
Write-Host "    (la misma con la que se entra a la web; queda guardada solo en este PC)"
$correo = Read-Host "    Correo"
$claveSec = Read-Host "    Clave" -AsSecureString
$clave = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($claveSec))

Write-Host ""
Write-Host "    Por ultimo, la clave del agente (te la pasa quien administra la"
Write-Host "    plataforma; es la misma que esta configurada en el servidor)."
$secreto = Read-Host "    Clave del agente"

$apiUrl = $env:PLATAFORMA_API_URL
if (-not $apiUrl) { $apiUrl = "https://sugerido-api.onrender.com" }

# El .env vive fuera de OneDrive y esta en .gitignore: no se sincroniza ni se sube.
$envFile = "$root\.env"
$lineas = @()
if (Test-Path $envFile) {
    $lineas = Get-Content $envFile |
        Where-Object { $_ -notmatch '^\s*(PLATAFORMA_|AGENTE_SECRET|MOTOR_CRUDOS_DIR)' }
}
$lineas += "PLATAFORMA_API_URL=$apiUrl"
$lineas += "PLATAFORMA_EMAIL=$correo"
$lineas += "PLATAFORMA_PASSWORD=$clave"
$lineas += "AGENTE_SECRET=$secreto"
$lineas += "MOTOR_CRUDOS_DIR=$crudos"
Set-Content -Path $envFile -Value $lineas -Encoding utf8
Bien "Configuracion guardada"

# ------------------------------------------------------------ 4) Tarea de Windows
Titulo "[4/5] Dejando el agente atento"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass " +
    "-File `"$root\scripts\agente_actualizacion.ps1`"")
# Dos disparadores: al iniciar sesion (para que reviva solo despues de reiniciar) y
# uno que se repite cada minuto indefinidamente (la cadencia real).
$t1 = New-ScheduledTaskTrigger -AtLogOn
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 1)
# IgnorarNueva: el motor tarda ~3 min y la tarea despierta cada 1, no deben encimarse.
$config = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName $TAREA -Action $accion -Trigger $t1, $t2 -Settings $config `
    -Description "Atiende el boton 'Actualizar ahora' de la plataforma de sugerido." -Force | Out-Null
Bien "Tarea '$TAREA' creada (revisa cada minuto)"

# ------------------------------------------------------------------ 5) Prueba
Titulo "[5/5] Probando la conexion"
try {
    $r = Invoke-RestMethod -Uri "$apiUrl/api/actualizacion/pendiente?agente=$env:COMPUTERNAME" `
        -Headers @{ "X-Agente-Secret" = $secreto } -Method Get -TimeoutSec 90
    Bien "La plataforma responde y acepta la clave del agente"
    if ($r.hay) { Ojo "Ademas habia una solicitud pendiente: el agente la tomara enseguida." }
}
catch {
    if ("$($_.Exception.Message)" -match "403") {
        Write-Host "    X   La plataforma rechazo la clave del agente." -ForegroundColor Red
        Write-Host "        Verifica que sea la misma configurada en el servidor (AGENTE_SECRET)." -ForegroundColor Red
    }
    else {
        Ojo "No pude hablar con la plataforma: $($_.Exception.Message)"
        Ojo "Si el servidor estaba dormido, prueba de nuevo en un minuto."
    }
}

Write-Host "`n============================================" -ForegroundColor Green
Write-Host " Listo. Este computador ya atiende el boton." -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "Desde ahora, quien tenga permiso aprieta 'Actualizar ahora' en la plataforma"
Write-Host "y los datos se recalculan aca, sin abrir nada."
Write-Host ""
Write-Host "Dos cosas que conviene saber:" -ForegroundColor Yellow
Write-Host " - Este PC tiene que estar encendido y con la sesion iniciada."
Write-Host " - Los Excel de 'Bases de datos' tienen que estar al dia; si estan vencidos"
Write-Host "   el motor no publica y la web lo avisa."
Write-Host ""
Write-Host "Registro de lo que hace el agente: $root\logs\agente_<fecha>.log"
Read-Host "`nEnter para cerrar"
