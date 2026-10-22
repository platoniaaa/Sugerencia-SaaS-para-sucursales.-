# ============================================================
#  tarea_al_iniciar_sesion.ps1 - Recupera la corrida diaria que se perdio
#
#  El PC se reinicia solo a la 01:00 (politica de la empresa) y la tarea de las
#  09:30 necesita una sesion iniciada: si nadie entra antes, Windows no la lanza
#  y tampoco la recupera despues (evento 332, "user not logged-on"). Esta tarea
#  corre al iniciar sesion y lanza la corrida del dia SOLO si:
#    - ya pasaron las 09:30 (antes, la corre la tarea diaria a su hora);
#    - hoy no hubo una corrida que saliera bien (la ultima linea RESULTADO del log
#      del dia no es OK: si fallo, se vuelve a intentar);
#    - no hay otra corrida en curso (candado del motor con su proceso vivo).
#  Asi no corre dos veces ni antes que el programa del ERP.
#
#  Las dos ultimas condiciones las mira tarea_si_no_corrio_hoy.ps1, que ademas
#  espera si el acceso "Actualizar plataforma" esta bajando las tablas (solo
#  existe si alguien lo creo a mano: el instalador del PC de la jefa ya no lo deja). Antes este script miraba solo
#  si existia el candado: uno viejo, de una corrida cortada por un apagon, dejaba
#  el dia sin recuperar.
# ============================================================
param(
    # La hora que se compara con las 09:30. Solo las pruebas la cambian.
    [datetime]$Ahora = (Get-Date)
)
$ErrorActionPreference = "Continue"

if ($Ahora.TimeOfDay -lt [TimeSpan]::Parse("09:30")) { exit 0 }

& "$PSScriptRoot\tarea_si_no_corrio_hoy.ps1"
exit $LASTEXITCODE
