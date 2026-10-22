# ============================================================
#  robot_erp.ps1 - Como se encuentra y se corre el programa que baja las tablas del ERP
#
#  El programa (un robot sobre Flexline, carpeta "automatizacion" con panel.bat y
#  flexline_flows.py) no es parte de este repositorio: lo instalo un kit aparte en
#  el PC. Lo carga actualizar_plataforma.ps1 (instalar_pc_jefa.ps1 ya no lo usa):
#    . "$PSScriptRoot\robot_erp.ps1"
#
#  Sin ventana del panel: se llama al subcomando que usan los botones del panel,
#    python flexline_flows.py descargar --tablas <lista>
#  que entra a cada empresa, baja las tablas, deja una copia en
#  Documentos\Desarrollos\Bases de datos (stock y Seguimientos de compras) y sale
#  con 0 solo si bajaron todas. En el PC del dueño, del 01 al 16-10-2026, bajar
#  estas cinco tardo entre 6,5 y 9,5 minutos cuando salio bien (logs del robot).
#  Mientras corre maneja el mouse y el teclado de verdad.
# ============================================================

# Lo que lee el motor: stock Curifor y Frontera, y los tres seguimientos. El Vale
# Consumo (para el BI) no se baja aca.
$TABLAS_ROBOT = "stock_frontera,seguimiento_frontera,seguimiento_importado,seguimiento_nacional,stock_curifor"

# Si la carpeta es la del programa del ERP. Hace falta flexline_flows.py: panel.bat
# solo abre la ventana, que a su vez usa ese archivo.
function Es-CarpetaRobot($dir) {
    return [bool]($dir -and (Test-Path (Join-Path $dir "flexline_flows.py")))
}

# Las carpetas donde suele quedar el programa, que existan y lo tengan. La primera era
# adonde lo copiaba el instalador (ya no lo hace). Si se agrega una, va también en
# Carpetas-KitRobot de instalar_pc_jefa.ps1, que la usa para encontrar el Python del kit.
function Carpetas-RobotProbables {
    $escritorio = [Environment]::GetFolderPath("Desktop")
    $documentos = [Environment]::GetFolderPath("MyDocuments")
    $od = $env:OneDriveCommercial
    $candidatas = @(
        "$env:USERPROFILE\automatizacion",
        "$escritorio\INSTALAR_EN_PC_JEFA\automatizacion",
        "$escritorio\automatizacion",
        "$documentos\automatizacion",
        "$env:USERPROFILE\Desktop\INSTALAR_EN_PC_JEFA\automatizacion",
        "$env:USERPROFILE\Documents\automatizacion"
    )
    if ($od) {
        $candidatas += @(
            "$od\Documentos\Desarrollos\Automatizaciones\3. Actualizacion\automatizacion",
            "$od\Escritorio\INSTALAR_EN_PC_JEFA\automatizacion",
            "$od\Documentos\automatizacion"
        )
    }
    $vistas = @{}
    foreach ($c in $candidatas) {
        if ((Es-CarpetaRobot $c) -and -not $vistas.ContainsKey($c.ToLower())) {
            $vistas[$c.ToLower()] = $true
            $c
        }
    }
}

# El Python con que corre el programa, en el mismo orden que su panel.bat e
# instalar.bat: el portable de la carpeta (el kit lo trae para no instalar nada),
# despues el del PATH y las rutas tipicas. Se queda con el primero que de verdad
# tenga las librerias del programa (pywinauto); el "python" del PATH puede ser el
# atajo de la Microsoft Store, que no corre nada. $null si ninguno sirve.
function Buscar-PythonRobot($dir) {
    $candidatos = @("$dir\python\python.exe")
    $g = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($g) { $candidatos += $g.Source }
    foreach ($v in @("314", "313", "312")) {
        $candidatos += "$env:LOCALAPPDATA\Programs\Python\Python$v\python.exe"
        $candidatos += "$env:ProgramFiles\Python$v\python.exe"
    }
    $candidatos += "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe"
    foreach ($py in $candidatos) {
        if (-not (Test-Path $py)) { continue }
        Push-Location $dir
        $eap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $py -c "import pywinauto" 2>&1 | Out-Null
            $ok = ($LASTEXITCODE -eq 0)
        }
        catch { $ok = $false }
        finally {
            $ErrorActionPreference = $eap
            Pop-Location
        }
        if ($ok) { return $py }
    }
    return $null
}
