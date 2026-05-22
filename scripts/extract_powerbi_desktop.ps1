# ============================================================
#  extract_powerbi_desktop.ps1
#  Lee la tabla del sugerido desde un Power BI Desktop ABIERTO
#  (instancia local de Analysis Services) y la imprime como JSON.
#
#  Lo invoca el backend; no esta pensado para uso manual directo.
#  Requiere el proveedor OLE DB "MSOLAP" (viene con DAX Studio /
#  las Analysis Services client libraries).
#
#  Salida (stdout): JSON { ok, error, port, rows: [ {col: val}, ... ] }
# ============================================================
param(
    [string]$Dax = "EVALUATE 'Sugerido por Sucursal'",
    [int]$Port = 0
)
$ErrorActionPreference = "Stop"

# Forzar salida UTF-8 (sin BOM) para que los acentos (Curico, etc.) lleguen bien al backend.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Find-PbiPorts {
    $procs = Get-Process -Name msmdsrv -ErrorAction SilentlyContinue
    $ports = @()
    foreach ($p in $procs) {
        try {
            $conns = Get-NetTCPConnection -OwningProcess $p.Id -State Listen -ErrorAction SilentlyContinue
            foreach ($c in $conns) {
                if ($c.LocalAddress -in @("127.0.0.1", "::1", "0.0.0.0", "::")) {
                    $ports += [int]$c.LocalPort
                }
            }
        }
        catch {}
    }
    return ($ports | Sort-Object -Unique)
}

function Get-Catalog($port) {
    $cs = "Provider=MSOLAP;Data Source=localhost:$port;"
    $conn = New-Object System.Data.OleDb.OleDbConnection($cs)
    $conn.Open()
    try {
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = "SELECT [CATALOG_NAME] FROM `$SYSTEM.DBSCHEMA_CATALOGS"
        $r = $cmd.ExecuteReader()
        $cat = $null
        if ($r.Read()) { $cat = $r.GetValue(0) }
        $r.Close()
        return $cat
    }
    finally { $conn.Close() }
}

function Invoke-Dax($port, $catalog, $dax) {
    $cs = "Provider=MSOLAP;Data Source=localhost:$port;Initial Catalog=$catalog;"
    $conn = New-Object System.Data.OleDb.OleDbConnection($cs)
    $conn.Open()
    try {
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = $dax
        $cmd.CommandTimeout = 180
        $r = $cmd.ExecuteReader()
        $cols = @()
        for ($i = 0; $i -lt $r.FieldCount; $i++) { $cols += $r.GetName($i) }
        $rows = New-Object System.Collections.ArrayList
        while ($r.Read()) {
            $obj = [ordered]@{}
            for ($i = 0; $i -lt $r.FieldCount; $i++) {
                $v = $r.GetValue($i)
                if ($v -is [System.DBNull]) { $v = $null }
                $obj[$cols[$i]] = $v
            }
            [void]$rows.Add($obj)
        }
        $r.Close()
        return $rows
    }
    finally { $conn.Close() }
}

$result = [ordered]@{ ok = $false; error = $null; port = 0; rows = @() }
try {
    $ports = if ($Port -gt 0) { @($Port) } else { Find-PbiPorts }
    if (-not $ports -or @($ports).Count -eq 0) {
        throw "No se detecto Power BI Desktop abierto. Abre el archivo del sugerido en Power BI Desktop y vuelve a intentar."
    }
    $lastErr = $null
    foreach ($p in $ports) {
        try {
            $cat = Get-Catalog $p
            if (-not $cat) { continue }
            $rows = Invoke-Dax $p $cat $Dax
            $result.ok = $true
            $result.port = $p
            $result.rows = $rows
            break
        }
        catch { $lastErr = $_.Exception.Message }
    }
    if (-not $result.ok) {
        throw ("No se pudo consultar el modelo abierto. Detalle: " + $lastErr)
    }
}
catch {
    $result.ok = $false
    $result.error = $_.Exception.Message
}

$result | ConvertTo-Json -Depth 5 -Compress
