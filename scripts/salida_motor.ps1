# ============================================================
#  salida_motor.ps1 - Que dijo una corrida oficial del motor
#
#  Lo cargan los scripts que corren el motor sin nadie mirando:
#  agente_actualizacion.ps1 (los botones "Actualizar ahora" y "Actualizar motor"),
#  tarea_vigentes_ford.ps1, tarea_si_no_corrio_hoy.ps1 y actualizar_plataforma.ps1.
#  Tambien sabe si hay otra cosa trabajando en este PC (los candados del motor, del
#  acceso "Actualizar plataforma" y del agente).
#    . "$PSScriptRoot\salida_motor.ps1"
#
#  Que el motor salga con 0 no quiere decir que publico. En un PC que no es el
#  titular de Fuentes de datos no calcula ni publica: imprime "NO SE PUBLICA: este
#  PC no es el titular (<alias>)" y sale con 0 a proposito, porque no es una falla.
#  Sin mirar esa linea, el agente le decia "OK" a la web sin haber publicado nada.
#
#  Las pruebas estan en apps/api/tests_motor/test_scripts_salida_motor.py.
# ============================================================

# El alias del PC titular si el motor no publico porque este PC no es el titular.
# $null si no.
function Titular-SiNoPublico($salida) {
    $linea = $salida | Select-String -Pattern 'NO SE PUBLICA: este PC no es el titular \((.*)\)' |
             Select-Object -First 1
    if ($linea) { return $linea.Matches[0].Groups[1].Value }
    return $null
}

# Las filas de la carga oficial ("CARGA OFICIAL: 17102 filas."). $null si el motor
# no imprimio esa linea. Se pregunta antes de indizar: `.Matches.Groups[1]` sobre un
# resultado nulo, con $ErrorActionPreference = "Stop", lanzaba "No se puede indizar
# en una matriz nula" y ese texto llegaba a la tarjeta de la web.
function Filas-Publicadas($salida) {
    $linea = $salida | Select-String -Pattern 'CARGA OFICIAL:\s*([\d\.]+)\s*filas' |
             Select-Object -First 1
    if ($linea) { return $linea.Matches[0].Groups[1].Value }
    return $null
}

# Los archivos por los que el motor freno sin publicar, vencidos o faltantes: el bloque
# que imprime debajo del "ERROR: ..." ("Archivos vencidos:", o "Problemas:" con Fuentes
# de datos activa), una linea "  - <archivo>: ..." por archivo. Lista vacia si el motor
# no freno por eso. Se usa para decirle a quien aprieta el boton que bajar y que hacer,
# en vez de dejar solo "ERROR: No se carga a produccion con archivos desactualizados.".
function Archivos-Frenados($salida) {
    $items = New-Object System.Collections.Generic.List[string]
    $dentro = $false
    foreach ($linea in @($salida | ForEach-Object { "$_" -split "`r?`n" })) {
        if (-not $dentro) {
            if ($linea -match '^(Archivos vencidos|Problemas):\s*$') { $dentro = $true }
            continue
        }
        # Lo ultimo que imprime el motor en el bloque es "Actualizalos ..." o "Revisalos ...".
        if ($linea -match '^(Actualizalos|Revisalos)\b') { break }
        # Las lineas de stdout (Python las vacia recien al salir) pueden caer en medio de
        # las de stderr: se saltan en vez de cortar la lista.
        if ($linea -match '^\s+-\s+(\S.*?)\s*$') { $items.Add($matches[1]) }
    }
    return $items.ToArray()
}

# Si el proceso que dejo un candado ("<PID> <fecha>") sigue vivo y es el mismo. Windows
# recicla los PID, asi que el numero puede ser ahora de otro proceso con el mismo nombre:
# el agente lanza un PowerShell cada minuto, y la tarea de las 09:30 corre en otro. Un
# candado viejo del acceso (la ventana se cerro con la X, o se apago el PC) con el PID
# de cualquiera de ellos dejaba el dia sin calcular. Por eso, ademas del nombre:
#   - quien pregunta no es quien dejo el candado (si lo fuera, no estaria preguntando);
#   - el proceso partio antes de la fecha anotada (unos segundos de margen: la fecha va
#     sin fracciones). Si partio despues, es otro que heredo el numero.
# Si la fecha no se puede leer, o Windows no deja ver cuando partio el proceso, se
# confia en el nombre, como antes.
function Proceso-DelCandado([int]$id, [string]$desde, [string]$nombre) {
    if ($id -eq $PID) { return $false }
    $proceso = Get-Process -Id $id -ErrorAction SilentlyContinue
    if (-not $proceso -or $proceso.ProcessName -notlike $nombre) { return $false }
    $fecha = [datetime]::MinValue
    if (-not [datetime]::TryParseExact($desde, "yyyy-MM-dd HH:mm:ss",
            [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$fecha)) {
        return $true
    }
    $inicio = $null
    try { $inicio = $proceso.StartTime } catch { }
    if ($inicio -and $inicio -gt $fecha.AddSeconds(5)) { return $false }
    return $true
}

# Si hay una corrida del motor en curso en este PC: la fecha de inicio que anoto
# el motor en su candado (apps/api/data/motor.lock, "<PID> <fecha>"). $null si no
# hay candado, o si el proceso que lo dejo ya no existe: el motor pisa ese candado
# viejo al arrancar (`tomar_candado`), asi que no frena nada y tampoco tiene que
# frenar a quien pregunta. Se mira que el proceso sea Python porque Windows recicla
# los PID: un candado viejo con el numero de otro programa no es una corrida.
function Corrida-EnCurso($root) {
    $candado = Join-Path $root "apps\api\data\motor.lock"
    if (-not (Test-Path $candado)) { return $null }
    $texto = "$(Get-Content $candado -Raw -ErrorAction SilentlyContinue)".Trim()
    if ($texto -notmatch '^(\d+)\s*(.*)$') { return $null }
    $id = [int]$matches[1]
    $desde = $matches[2].Trim()
    if (-not (Proceso-DelCandado $id $desde "python*")) { return $null }
    if (-not $desde) { $desde = "hora desconocida" }
    return $desde
}

# Si el acceso "Actualizar plataforma" (actualizar_plataforma.ps1) esta corriendo en
# este PC: la fecha en que empezo. $null si no. Mientras baja las tablas del ERP no
# hay que lanzar el motor (leeria archivos a medio bajar y despues el acceso ya no
# podria publicar los nuevos: "NO SE CORRE") ni cambiar el codigo. Mismo formato
# de candado que el del motor, con el PID de esa ventana de PowerShell.
function Actualizacion-EnCurso($root) {
    $candado = Join-Path $root ".actualizar_plataforma.lock"
    if (-not (Test-Path $candado)) { return $null }
    $texto = "$(Get-Content $candado -Raw -ErrorAction SilentlyContinue)".Trim()
    if ($texto -notmatch '^(\d+)\s*(.*)$') { return $null }
    $id = [int]$matches[1]
    $desde = $matches[2].Trim()
    if (-not (Proceso-DelCandado $id $desde "powershell*")) { return $null }
    if (-not $desde) { $desde = "hora desconocida" }
    return $desde
}

# Si el agente esta atendiendo un "Actualizar motor" en este PC: la fecha en que lo
# tomo. $null si no. Mientras hace git merge y reinstala las librerias no hay que
# lanzar el motor: importaria una mezcla de codigo viejo y nuevo, o un polars a medio
# reinstalar, y caeria antes de dejar incidencia; o al reves, pip fallaria por
# archivos en uso. El agente anota en su candado (.agente.lock) "<PID> <fecha> <tipo>".
function ActualizacionMotor-EnCurso($root) {
    $candado = Join-Path $root ".agente.lock"
    if (-not (Test-Path $candado)) { return $null }
    $texto = "$(Get-Content $candado -Raw -ErrorAction SilentlyContinue)".Trim()
    if ($texto -notmatch '^(\d+)\s+(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+actualizar_motor$') { return $null }
    $id = [int]$matches[1]
    $desde = $matches[2]
    if (-not (Proceso-DelCandado $id $desde "powershell*")) { return $null }
    return $desde
}
