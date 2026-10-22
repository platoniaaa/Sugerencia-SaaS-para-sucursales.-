# ============================================================
#  tarea_si_no_corrio_hoy.ps1 - La corrida de las 09:30, sin repetir
#
#  Lo corre tarea_al_iniciar_sesion.ps1 (la tarea "Sugerido Curifor - Motor al iniciar
#  sesion" del PC del dueño). instalar_pc_jefa.ps1 YA NO registra esta tarea ni la de
#  las 09:30: en el PC de la jefa el motor solo corre cuando se aprieta "Actualizar
#  ahora" (agente_actualizacion.ps1). Lanza tarea_diaria.ps1 SOLO si:
#    - hoy no hubo una corrida que saliera bien: la ultima linea RESULTADO del log
#      del dia (logs\motor_<fecha>.log) no es OK. El acceso del Escritorio
#      "Actualizar plataforma" y el boton "Actualizar ahora" de la web (el agente)
#      dejan esa linea: si ella ya actualizo temprano, a las 09:30 no se calcula dos
#      veces lo mismo. Si esa corrida fallo (por ejemplo, la plataforma respondio
#      502 al cargar), se vuelve a intentar: antes una falla de las 08:40 dejaba el
#      dia sin reintento y la tarea quedaba marcada como correcta;
#    - no hay otra corrida en curso (candado del motor con su proceso vivo; uno
#      viejo de un proceso muerto no frena, el motor lo pisa al arrancar).
#
#  Si a las 09:30 el acceso "Actualizar plataforma" esta bajando las tablas, espera
#  a que termine (hasta 60 minutos) y vuelve a mirar: si el acceso publico, no hace
#  nada; si el programa del ERP fallo y el acceso no calculo, calcula con lo que
#  haya. Lanzar el motor en ese momento leeria archivos a medio bajar, y despues el
#  acceso ya no podria publicar los nuevos ("NO SE CORRE: ya hay una corrida").
#
#  Tambien espera (hasta 15 minutos) si el agente esta atendiendo un "Actualizar
#  motor": mientras hace git merge y reinstala las librerias, un motor importaria
#  codigo a medio cambiar.
#
#  En el PC del dueño la tarea de las 09:30 corre tarea_diaria.ps1 directo: ahi no
#  hay acceso "Actualizar plataforma" que pueda haber corrido antes.
# ============================================================
param(
    # Cada cuanto se vuelve a mirar si el acceso termino, y hasta cuando. Solo las
    # pruebas los cambian.
    [int]$EsperaSeg = 30,
    [int]$EsperaMaxMin = 60
)
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$log = "$root\logs\motor_$(Get-Date -Format 'yyyy-MM-dd').log"

. "$PSScriptRoot\salida_motor.ps1"

# Una actualizacion del motor tarda 1 a 3 minutos; la plataforma la da por caida a los
# 15. Si sigue despues de eso, quedo pegada: se calcula igual.
$ESPERA_MOTOR_MAX_MIN = 15

$partio = Get-Date
$limite = $partio.AddMinutes($EsperaMaxMin)
$limiteMotor = $partio.AddMinutes([Math]::Min($EsperaMaxMin, $ESPERA_MOTOR_MAX_MIN))
while ((Get-Date) -lt $limite -and ((Actualizacion-EnCurso $root) -or
        ((Get-Date) -lt $limiteMotor -and (ActualizacionMotor-EnCurso $root)))) {
    Start-Sleep -Seconds $EsperaSeg
}

if (Test-Path $log) {
    $ultimo = Select-String -Path $log -Pattern '^RESULTADO' | Select-Object -Last 1
    if ($ultimo -and $ultimo.Line -notmatch 'FALLO') { exit 0 }
}
if (Corrida-EnCurso $root) { exit 0 }
if (Actualizacion-EnCurso $root) { exit 0 }  # paso la hora y el acceso sigue: que publique el

& "$PSScriptRoot\tarea_diaria.ps1"
exit $LASTEXITCODE
