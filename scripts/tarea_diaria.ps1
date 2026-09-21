# ============================================================
#  tarea_diaria.ps1 - Lo que corre la tarea programada de Windows
#
#  Calcula el sugerido con el motor y lo publica. No pregunta nada (corre sin
#  nadie delante) y deja un log por dia, para poder revisar despues si algo fallo
#  de madrugada.
#
#  Las credenciales salen del .env de la raiz. Si un crudo esta desactualizado el
#  job se niega a cargar: mejor dejar el dato de ayer que publicar uno vencido.
# ============================================================
# "Continue" a proposito. Con "Stop", el 2>&1 sobre un exe nativo envolvia cada
# linea de stderr en un ErrorRecord y PowerShell abortaba el pipeline en la
# primera: el log quedaba en 32 bytes (solo el encabezado), sin el traceback ni la
# linea RESULTADO. El motor fallo cinco dias seguidos y el log no dijo por que.
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$logDir = "$root\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = "$logDir\motor_$(Get-Date -Format 'yyyy-MM-dd').log"

"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $log -Append -Encoding utf8
try {
    Push-Location "$root\apps\api"
    # Out-File y no Tee-Object: en PowerShell 5.1 Tee-Object no acepta -Encoding y
    # escribia UTF-16 sobre un archivo que el resto del script abre en UTF-8, asi
    # que el log salia con un byte nulo entre cada letra ("C r u d o s").
    # El ForEach convierte los ErrorRecord de stderr a texto plano.
    # -u (sin buffer): escribiendo a un pipe, Python guarda la salida y la suelta
    # recien al terminar. Si matan la tarea a mitad -como paso el 29-07- el log
    # queda vacio justo cuando mas se necesita. Con -u cada linea baja al tiro.
    & "$root\apps\api\.venv\Scripts\python.exe" -u -m src.jobs.correr_motor_real --oficial 2>&1 |
        ForEach-Object { "$_" } |
        Out-File $log -Append -Encoding utf8
    $code = $LASTEXITCODE
}
catch {
    "ERROR del wrapper: $($_.Exception.Message)" | Out-File $log -Append -Encoding utf8
    $code = 1
}
finally {
    Pop-Location
}

# Si el proceso ni siquiera arranco (venv borrado, ruta mala) $code queda vacio y
# un `exit $null` sale 0: la tarea marcaria exito sin haber corrido nada.
if ($null -eq $code) { $code = 1 }

if ($code -eq 0) { "RESULTADO: OK" | Out-File $log -Append -Encoding utf8 }
else { "RESULTADO: FALLO (codigo $code)" | Out-File $log -Append -Encoding utf8 }

# Se borran los logs de mas de 30 dias para que la carpeta no crezca sin fin.
Get-ChildItem $logDir -Filter "motor_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $code
