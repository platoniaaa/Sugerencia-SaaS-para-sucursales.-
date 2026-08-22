# ============================================================
#  tarea_vigentes_ford.ps1 - Corrida SEMANAL de vigentes de FORD
#
#  Consulta en el portal de FORD los codigos que Curifor tiene (stock + pautas),
#  arma el Excel con el vigente y la cadena de reemplazo de cada uno, y lo deja en
#  la carpeta de crudos. Al dia siguiente el motor diario lo toma solo.
#
#  Corre los LUNES: asi el martes la plataforma ya muestra los reemplazos frescos.
#
#  Si la sesion de Ford vencio, la corrida se queda esperando el MFA -eso es
#  deliberado, el segundo factor no se automatiza-. Por eso hay un tope de tiempo:
#  pasado ese tope se corta y se deja una incidencia en la plataforma, en vez de
#  quedarse con una ventana de Chrome abierta toda la semana sin que nadie sepa.
# ============================================================
$ErrorActionPreference = "Continue"

$wings = "C:\Users\icalderon\OneDrive - Curifor S.A\Documentos\Desarrollos\Automatizaciones\5. Extraccion precios ford"
$crudos = "C:\Users\icalderon\OneDrive - Curifor S.A\Documentos\Desarrollos\Bases de datos\Vigentes Ford"
$python = "C:\Users\icalderon\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$root = Split-Path $PSScriptRoot -Parent
$logDir = "$root\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = "$logDir\vigentes_ford_$(Get-Date -Format 'yyyy-MM-dd').log"

# La corrida completa medida el 22-08-2026: 5.020 codigos en 25 minutos. El tope
# es holgado a proposito -la lista crece, y una semana lenta no es una falla- pero
# muy por debajo de "toda la noche": si pasa de aca, es que pidio MFA.
$topeMinutos = 90

function Log($msg) {
    "[$(Get-Date -Format 'HH:mm:ss')] $msg" | Out-File $log -Append -Encoding utf8
}

"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $log -Append -Encoding utf8
Log "Corrida semanal de vigentes FORD"

# --- 1) Armar la lista de entrada (stock + pautas, traducida y filtrada) ---------
Log "Armando la lista de consulta..."
Push-Location $wings
& $python -u "armar_lista_consulta.py" 2>&1 | ForEach-Object { "$_" } | Out-File $log -Append -Encoding utf8
$codigoLista = $LASTEXITCODE
Pop-Location
if ($codigoLista -ne 0) {
    Log "FALLO armando la lista (codigo $codigoLista). No se consulta nada."
    & "$root\apps\api\.venv\Scripts\python.exe" -c @"
import sys; sys.path.insert(0, r'$root\apps\api')
from src.jobs.correr_motor_real import avisar_falla
avisar_falla('No se pudo armar la lista de vigentes FORD',
             'El paso previo a consultar el portal fallo. Ver logs/vigentes_ford_*.log')
"@ 2>&1 | Out-File $log -Append -Encoding utf8
    "RESULTADO: FALLO (armando la lista)" | Out-File $log -Append -Encoding utf8
    exit 1
}

# --- 2) Consultar el portal, con tope de tiempo ----------------------------------
Log "Consultando el portal de FORD (tope $topeMinutos min)..."
# El codigo de salida del Python viaja como una linea marcada dentro de la salida
# del job. `$job.State` NO sirve para esto: dice si el JOB termino, no si el
# proceso de adentro fallo. Con `State` este wrapper marco "RESULTADO: OK" una
# corrida que habia muerto pidiendo MFA (22-08-2026), copio el archivo viejo a
# crudos y no dejo ninguna incidencia. Es la misma trampa que documenta
# `tarea_diaria.ps1`.
$job = Start-Job -ScriptBlock {
    param($wings, $python)
    Set-Location $wings
    & $python -u "correr_vigentes_curifor.py" 2>&1
    "__CODIGO_SALIDA__=$LASTEXITCODE"
} -ArgumentList $wings, $python

$termino = Wait-Job $job -Timeout ($topeMinutos * 60)
if ($null -eq $termino) {
    Stop-Job $job
    Receive-Job $job 2>&1 | ForEach-Object { "$_" } | Out-File $log -Append -Encoding utf8
    Remove-Job $job -Force
    Log "CORTADA por tope de tiempo. Lo mas probable es que la sesion de Ford"
    Log "vencio y quedo pidiendo MFA. Hay que abrir la app y entrar una vez."
    & "$root\apps\api\.venv\Scripts\python.exe" -c @"
import sys; sys.path.insert(0, r'$root\apps\api')
from src.jobs.correr_motor_real import avisar_falla
avisar_falla('La corrida semanal de vigentes FORD no termino',
             'Paso el tope de tiempo. Lo mas probable es que la sesion del portal '
             'de Ford vencio y quedo pidiendo el MFA, que lo tiene que ingresar una '
             'persona. Abrir la app de extraccion, iniciar sesion, y volver a correr. '
             'Mientras tanto la plataforma sigue mostrando los reemplazos de la '
             'semana pasada.')
"@ 2>&1 | Out-File $log -Append -Encoding utf8
    "RESULTADO: FALLO (tope de tiempo / MFA)" | Out-File $log -Append -Encoding utf8
    exit 1
}

$salidaJob = Receive-Job $job 2>&1 | ForEach-Object { "$_" }
Remove-Job $job -Force
$salidaJob | Out-File $log -Append -Encoding utf8

$marca = $salidaJob | Where-Object { $_ -like "__CODIGO_SALIDA__=*" } | Select-Object -Last 1
if ($marca) { $codigoCorrida = [int]($marca -replace '.*=', '') }
else {
    # Sin la marca, el job murio antes de llegar al final. No se asume exito.
    $codigoCorrida = 1
    Log "La corrida no dejo codigo de salida: se toma como fallida."
}

if ($codigoCorrida -ne 0) {
    Log "FALLO la consulta al portal (codigo $codigoCorrida)."
    Log "Si el log de arriba dice 'MFA', la sesion de Ford vencio: hay que abrir la"
    Log "app de extraccion, entrar una vez, y volver a correr esta tarea."
    Log "NO se copia nada a crudos: el motor sigue con el archivo de la semana pasada."
    & "$root\apps\api\.venv\Scripts\python.exe" -c @"
import sys; sys.path.insert(0, r'$root\apps\api')
from src.jobs.correr_motor_real import avisar_falla
avisar_falla('La corrida semanal de vigentes FORD fallo',
             'La consulta al portal no termino bien. La causa mas comun es que la '
             'sesion de Ford vencio y quedo pidiendo el MFA, que lo tiene que '
             'ingresar una persona: abrir la app de extraccion, iniciar sesion, y '
             'volver a correr la tarea. Los reemplazos siguen mostrando los de la '
             'semana pasada, no hay dato erroneo en pantalla.')
"@ 2>&1 | Out-File $log -Append -Encoding utf8
    "RESULTADO: FALLO (codigo $codigoCorrida)" | Out-File $log -Append -Encoding utf8
    exit $codigoCorrida
}

# --- 3) Dejar el resultado donde el motor lo ve ----------------------------------
# Solo si la corrida termino bien: copiar tras una falla dejaria el archivo de la
# corrida anterior con fecha nueva, y el log diria "actualizado" sin serlo.
#
# El motor busca "*vigentes*ford*" y toma el mas reciente. El nombre NO puede
# llevar "precio", o desplaza a la lista de 39.622 que alimenta el SKU del portal.
$salida = Get-ChildItem "$wings\salidas" -Filter "Vigentes ford curifor_*_resultado.xlsx" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($null -eq $salida) {
    Log "No se encontro el Excel de salida. El motor va a seguir con el de la semana pasada."
    "RESULTADO: FALLO (sin archivo de salida)" | Out-File $log -Append -Encoding utf8
    exit 1
}
if (-not (Test-Path $crudos)) { New-Item -ItemType Directory -Path $crudos | Out-Null }
Copy-Item $salida.FullName -Destination $crudos -Force
Log "Copiado a crudos: $($salida.Name)"

# Se dejan solo las 4 ultimas semanas: el motor toma el mas reciente, pero una
# carpeta con un ano de archivos hace lento el barrido y confunde al mirarla.
Get-ChildItem $crudos -Filter "Vigentes ford curifor_*_resultado.xlsx" |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 4 |
    Remove-Item -Force -ErrorAction SilentlyContinue

if ($codigoCorrida -eq 0) {
    Log "El motor lo toma en su proxima corrida (manana 10:00)."
    "RESULTADO: OK" | Out-File $log -Append -Encoding utf8
} else {
    "RESULTADO: FALLO (codigo $codigoCorrida)" | Out-File $log -Append -Encoding utf8
}

Get-ChildItem $logDir -Filter "vigentes_ford_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $codigoCorrida
