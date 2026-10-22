# ============================================================
#  actualizar_plataforma.ps1 - El acceso "Actualizar plataforma" del Escritorio
#
#  Un doble clic hace las dos cosas del día, una detrás de la otra:
#    1) El programa del ERP baja las tablas (stock Curifor y Frontera, y los tres
#       seguimientos de compras). Maneja el mouse y el teclado: ~9 minutos.
#    2) Si bajaron todas, el motor calcula el sugerido y lo publica en la
#       plataforma: el mismo tarea_diaria.ps1 de las 09:30, con su log del día.
#       25 a 35 minutos; ahí ya se puede usar el PC.
#  La ventana muestra el avance y al final dice qué pasó y qué hacer.
#
#  Como deja la línea RESULTADO en el log del día, la tarea de las 09:30 del PC del
#  dueño (tarea_si_no_corrio_hoy.ps1) ya no calcula otra vez si salió bien; si falló,
#  la vuelve a intentar.
#
#  YA NO lo deja instalar_pc_jefa.ps1: en el PC de la jefa el motor corre solo con el
#  botón de la plataforma, y su programa del ERP lo corre ella. Queda para quien lo
#  cree a mano; la carpeta del programa sale del .env (ROBOT_ERP_DIR).
#
#  Va en UTF-8 con BOM: los textos de pantalla llevan tildes.
# ============================================================
param(
    # Solo para probar este script: -SinRobot no corre el programa del ERP; -SinPausa
    # no espera los 10 segundos antes del programa ni el Enter del final.
    [switch]$SinRobot,
    [switch]$SinPausa
)
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
. "$PSScriptRoot\salida_motor.ps1"
. "$PSScriptRoot\robot_erp.ps1"

try { $Host.UI.RawUI.WindowTitle = "Actualizar plataforma" } catch { }
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"

function Titulo($t) { Write-Host "`n==> $t" -ForegroundColor Cyan }
function Bien($t)   { Write-Host "    OK  $t" -ForegroundColor Green }
function Ojo($t)    { Write-Host "    !   $t" -ForegroundColor Yellow }
function Mal($t)    { Write-Host "    X   $t" -ForegroundColor Red }
# Mientras esta ventana trabaja, su candado (.actualizar_plataforma.lock, con el PID de
# esta ventana) le avisa a la tarea de las 09:30 y al agente que no lancen el motor
# encima del programa del ERP. Se suelta antes de esperar el Enter: si no, una
# ventana olvidada abierta dejaria esperando a la tarea de las 09:30.
$candado = "$root\.actualizar_plataforma.lock"
$candadoPropio = $false
function Terminar($codigo) {
    if ($script:candadoPropio) { Remove-Item $candado -Force -ErrorAction SilentlyContinue }
    if (-not $SinPausa) { Read-Host "`nEnter para cerrar esta ventana" | Out-Null }
    exit $codigo
}

# El .env en UTF-8: la ruta de Data BI lleva tilde (ver agente_actualizacion.ps1).
$cfg = @{}
if (Test-Path "$root\.env") {
    foreach ($linea in Get-Content "$root\.env" -Encoding UTF8) {
        if ($linea -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
            $cfg[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
        }
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Actualizar plataforma: tablas del ERP y sugerido de compras" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
$inicio = Get-Date
Write-Host "Empezó: $($inicio.ToString('HH:mm')). En total tarda entre 35 y 45 minutos."

$otra = Actualizacion-EnCurso $root
if ($otra) {
    Mal "Ya hay otra ventana de 'Actualizar plataforma' trabajando (desde $otra)."
    Write-Host "    Deja que esa termine; esta no hace nada."
    Terminar 1
}
$enCurso = Corrida-EnCurso $root
if ($enCurso) {
    Mal "El motor ya está calculando en este PC (desde $enCurso)."
    Write-Host "    Espera a que termine (unos 30 minutos) y vuelve a intentarlo si hace falta."
    Write-Host "    Lo que está corriendo va a publicar solo."
    Terminar 1
}
# Un admin apretó "Actualizar motor" en la web: el agente está bajando la versión nueva
# y quizás reinstalando librerías. Un motor ahora importaría código a medio cambiar.
$motorAct = ActualizacionMotor-EnCurso $root
if ($motorAct) {
    Mal "En este PC se está instalando una versión nueva del motor (la pidió un admin desde la web, a las $(([datetime]$motorAct).ToString('HH:mm')))."
    Write-Host "    Tarda 1 a 3 minutos. Espera a que termine y vuelve a hacer doble clic en este acceso."
    Terminar 1
}
Set-Content -Path $candado -Value "$PID $($inicio.ToString('yyyy-MM-dd HH:mm:ss'))" -Encoding ascii
$candadoPropio = $true

# ------------------------------------------------------- 1) Programa del ERP
Titulo "[1/2] Bajando las tablas del ERP (unos 9 minutos)"
if ($SinRobot) {
    Ojo "Prueba: no se corre el programa del ERP."
}
else {
    $robot = $cfg["ROBOT_ERP_DIR"]
    if (-not (Es-CarpetaRobot $robot)) {
        Mal "No encuentro el programa del ERP (carpeta: '$robot')."
        Write-Host "    Vuelve a hacer doble clic en 'INSTALAR PLATAFORMA' y elige la carpeta"
        Write-Host "    'automatizacion' del programa del ERP."
        Terminar 1
    }
    $pyRobot = Buscar-PythonRobot $robot
    if (-not $pyRobot) {
        Mal "El programa del ERP no tiene su Python listo en este PC."
        Write-Host "    Abre la carpeta '$robot' y haz doble clic en instalar.bat."
        Write-Host "    Cuando diga TODO LISTO, vuelve a usar este acceso."
        Terminar 1
    }
    Write-Host ""
    Write-Host "    ***************************************************************" -ForegroundColor Red
    Write-Host "    *  NO TOQUES EL MOUSE NI EL TECLADO hasta que diga LISTO.     *" -ForegroundColor Red
    Write-Host "    *  El programa abre Flexline y hace clics de verdad.          *" -ForegroundColor Red
    Write-Host "    ***************************************************************" -ForegroundColor Red
    if (-not $SinPausa) {
        for ($i = 10; $i -gt 0; $i--) {
            Write-Host "`r    Empieza en $i segundos (para cancelar, cierra esta ventana)...  " -NoNewline
            Start-Sleep -Seconds 1
        }
        Write-Host ""
    }

    Push-Location $robot
    try {
        $salidaRobot = & $pyRobot -u flexline_flows.py descargar --tablas $TABLAS_ROBOT 2>&1 |
            ForEach-Object {
                $l = "$_"
                # El programa avisa cuándo se puede usar el PC con "§PC§|<0|1>|<motivo>".
                if ($l -match 'PC\S{0,3}\|([01])\|(.*)$') {
                    if ($matches[1] -eq "1") { Write-Host "    >>> Ya puedes usar el PC: $($matches[2])" -ForegroundColor Green }
                    else { Write-Host "    >>> NO TOQUES EL PC: $($matches[2])" -ForegroundColor Red }
                }
                else { Write-Host "    $l" -ForegroundColor DarkGray }
                $l
            }
        $codigoRobot = $LASTEXITCODE
    }
    finally { Pop-Location }
    if ($null -eq $codigoRobot) { $codigoRobot = 1 }

    if ($codigoRobot -ne 0) {
        Write-Host ""
        Mal "El programa del ERP no bajó todas las tablas."
        $fallos = @($salidaRobot | Where-Object { $_ -match '(FALLO|OMITIDO)\s+\S' } | Select-Object -Last 5)
        foreach ($f in $fallos) { Write-Host "      $($f.Trim())" -ForegroundColor Yellow }
        Write-Host ""
        Write-Host "    El sugerido NO se calculó, para no publicar con tablas de ayer." -ForegroundColor Yellow
        Write-Host "    Qué hacer:"
        Write-Host "     1. Vuelve a hacer doble clic en 'Actualizar plataforma'."
        Write-Host "     2. Si vuelve a fallar, abre panel.bat en '$robot' y baja las tablas desde ahí."
        Write-Host "        La tarea de las 09:30 calcula igual con lo que haya."
        Terminar 1
    }
    # El programa sale con 0 si bajó todo, aunque no haya podido dejar la copia en
    # 'Bases de datos' (por ejemplo, el archivo estaba abierto en Excel): solo lo anota.
    # El motor lee esa copia: con la de ayer, que pasa la guarda de frescura, publicaba
    # datos viejos y esta ventana decía LISTO.
    $copiasMal = @($salidaRobot | Where-Object { $_ -match 'Copia local FALLO|Copia local: no existe' })
    if ($copiasMal.Count -gt 0) {
        Write-Host ""
        Mal "El programa del ERP bajó las tablas, pero no pudo dejar la copia en 'Bases de datos'."
        foreach ($c in ($copiasMal | Select-Object -Last 5)) {
            Write-Host "      $(($c -replace '^\S+ \S+ \[\w+\]\s*', '').Trim())" -ForegroundColor Yellow
        }
        Write-Host ""
        Write-Host "    El sugerido NO se calculó: el motor habría leído el archivo de ayer." -ForegroundColor Yellow
        Write-Host "    Qué hacer: cierra los Excel de la carpeta 'Bases de datos' y vuelve a usar este acceso."
        Terminar 1
    }
    Bien "Tablas del ERP listas. Ya puedes usar el PC."
}

# ------------------------------------------------------------------ 2) Motor
Titulo "[2/2] Calculando y publicando el sugerido (25 a 35 minutos)"
Write-Host "    Puedes usar el PC. No lo apagues ni cierres la sesión hasta que termine."
Write-Host "    Si cierras esta ventana, el cálculo sigue igual (solo dejas de ver el avance)."
$log = "$root\logs\motor_$(Get-Date -Format 'yyyy-MM-dd').log"
$desde = if (Test-Path $log) { (Get-Item $log).Length } else { 0 }

# tarea_diaria.ps1 escribe solo en el log: se lanza aparte y se va mostrando lo que
# agrega, sin cambiar nada de cómo corre a las 09:30. En su propia consola oculta y
# no en esta: cerrar esta ventana a mitad mataba al motor en plena publicación. El
# log queda en UTF-8 (tarea_diaria.ps1 se encarga), y aquí se lee igual.
$proceso = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSScriptRoot\tarea_diaria.ps1`"")
$null = $proceso.Handle  # sin esto, ExitCode queda vacío al terminar (PowerShell 5.1)

$posicion = $desde
$resto = ""
$lineasCorrida = New-Object System.Collections.Generic.List[string]
function Mostrar-Nuevo {
    if (-not (Test-Path $log)) { return }
    try {
        $fs = [IO.File]::Open($log, 'Open', 'Read', 'ReadWrite')
        try {
            if ($fs.Length -lt $script:posicion) { $script:posicion = 0 }
            $n = [int]($fs.Length - $script:posicion)
            if ($n -le 0) { return }
            $buf = New-Object byte[] $n
            $null = $fs.Seek($script:posicion, 'Begin')
            $n = $fs.Read($buf, 0, $n)
            $script:posicion += $n
        }
        finally { $fs.Close() }
    }
    catch { return }
    $texto = $script:resto + [Text.Encoding]::UTF8.GetString($buf, 0, $n)
    $partes = $texto.TrimStart([char]0xFEFF) -split "`r?`n"
    $script:resto = $partes[-1]
    for ($i = 0; $i -lt $partes.Count - 1; $i++) {
        $l = $partes[$i].TrimStart([char]0xFEFF)
        $script:lineasCorrida.Add($l)
        Write-Host "    $l" -ForegroundColor DarkGray
    }
}
while (-not $proceso.HasExited) {
    Mostrar-Nuevo
    Start-Sleep -Seconds 2
}
Mostrar-Nuevo
if ($resto) { $lineasCorrida.Add($resto); Write-Host "    $resto" -ForegroundColor DarkGray }
$codigoMotor = $proceso.ExitCode
$minutos = [int]((Get-Date) - $inicio).TotalMinutes

# ---------------------------------------------------------------- Resumen
$salida = $lineasCorrida.ToArray()
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
$titular = Titular-SiNoPublico $salida
$filas = Filas-Publicadas $salida
if ($salida | Select-String -Pattern '^NO SE CORRE:' -Quiet) {
    Ojo "No se calculó: ya había otra corrida del motor en este PC. Esa publica sola."
    $codigoFinal = 0
}
elseif ($titular) {
    Ojo "El motor no publicó: este PC no es el titular en Fuentes de datos (el titular es $titular)."
    Write-Host "    Si este PC tiene que publicar, un admin lo elige en Cargar > Fuentes de datos."
    $codigoFinal = 1
}
elseif ($codigoMotor -eq 0) {
    if ($filas) { Bien "LISTO en $minutos minutos. Se publicaron $filas filas: los compradores ya ven los datos nuevos." }
    else { Bien "LISTO en $minutos minutos. El motor terminó bien." }
    $codigoFinal = 0
}
else {
    Mal "El sugerido NO se actualizó: la plataforma sigue con los datos anteriores."
    $motivo = $salida | Where-Object { $_ -match '^(ERROR|DESACTUALIZADO|\s+DESACTUALIZADO|.*Error:)' } |
              Select-Object -Last 3
    foreach ($m in $motivo) { Write-Host "      $($m.Trim())" -ForegroundColor Yellow }
    Write-Host "    Los admin reciben un aviso en la campanita de la plataforma con el motivo."
    # La tarea de las 09:30 vuelve a calcular si la última corrida del día falló, y si
    # este acceso partió antes de esa hora, la tarea lo está esperando.
    if ($inicio.TimeOfDay -lt [TimeSpan]::Parse("09:30")) {
        Write-Host "    A las 09:30 se vuelve a intentar solo (o apenas termine esto, si ya pasó esa hora)."
    }
    else {
        Write-Host "    La tarea de las 09:30 ya pasó, así que hoy no se vuelve a intentar sola."
    }
    Write-Host "    Qué hacer: si el motivo es un archivo desactualizado, vuelve a usar este acceso"
    Write-Host "    (baja las tablas de nuevo). Si es otra cosa, avísale a quien mantiene el motor."
    $codigoFinal = 1
}
Write-Host "    Registro completo: $log"
Write-Host "============================================================" -ForegroundColor Cyan
Terminar $codigoFinal
