"""Conector al SQL Server de Flexline (ERP de Curifor).

Lee, en vivo, las fuentes que el Power BI hoy saca del mismo SQL:
- **Seguimiento de compras nacional**: `Tmp_SeguimientoCompraNacional` (Empresa E01).
- **Ventas Curifor**: `Tmp_ProdMensualPostVta` (Empresa E01, fecha ≥ 2018-12-31).
- **Ventas Frontera**: `Informe Gestión ...` (Empresa E07). Query largo tomado
  verbatim de la partición M del modelo (ver `VENTAS_FRONTERA_QUERY`).

Las consultas SQL están tomadas de las particiones M del modelo (`Sql.Database(
"10.50.15.2","BDFlexline",...)`). Las transformaciones que el modelo hace DESPUÉS
en Power Query / DAX (mapeo de SucursalID, tag de Origen, CantidadAjustada, filtros)
se replican aquí en Python, para entregar el mismo esquema que hoy consume el motor.

Fuentes que NO son SQL y se **inyectan** como DataFrames (SharePoint Excel):
- Histórico de ventas Curifor (`Produccion Post Venta Historico`, biblioteca
  `RespaldosBBDD`). Se anexa a las ventas Curifor con `leer_ventas(historico=...)`
  para que la historia quede completa (necesario para derivar la columna Empresa
  Solo Curifor / Frontera / Ambas — que mira TODA la historia, no solo 12m).
- Seguimiento importado y seguimiento Frontera (Excel). Se unen al nacional con
  `unir_seguimiento(...)` (réplica de la tabla calculada 'Seguimiento Compras Unificado').

ESTADO: **no ejecutado / no probado en vivo** — requiere (1) credenciales del ERP
(por env, nunca en el repo), (2) `pip install python-tds` (o pyodbc), (3) correr
DENTRO de la red de Curifor (10.50.15.2 es IP privada de la LAN). Las funciones de
transformación pura (mapeo de sucursal, cantidad ajustada, filtros, unión) SÍ están
cubiertas por tests offline con datos sintéticos (`tests_motor/test_conector_sql.py`).

Brecha conocida (documentada, no mecánica): la SUCURSAL de las ventas Curifor la
resuelve el modelo con `Local` → `Dim_Locales (2)[DESCRIPCION]` (SUC0XX → nombre,
43 locales). Acá se pasa la columna SUCURSAL cruda tal cual; cerrar esto requiere el
snapshot de Dim_Locales(2) (tabla chica y estable). No afecta la columna Empresa.
"""
from __future__ import annotations

import os

import polars as pl

# --- Conexión (parámetros por variables de entorno; credenciales fuera del repo) ---
SQL_HOST = os.environ.get("FLEXLINE_SQL_HOST", "10.50.15.2")
SQL_DB = os.environ.get("FLEXLINE_SQL_DB", "BDFlexline")

# --- Mapeo código de local -> SucursalID del SEGUIMIENTO NACIONAL (SWITCH de la
# columna calculada 'Seguimiento Compras curifor nacional'[SucursalID]). Incluye el
# fix del 08-jul-2026: SUC160 -> "TALCA (2)" y SUC240 -> "DIEZ DE JULIO (2)" (antes
# "TALCA 2"/"DIEZ DE JULIO"), para que el cruce (Producto, SucursalID) ventas↔compras
# matchee la ortografía canónica del sugerido y no se pierdan los proveedores. ---
SUCURSAL_ID_MAP = {
    "SUC020": "CHILLAN", "SUC030": "CHILLAN VIEJO", "SUC040": "COQUIMBO",
    "SUC050": "CURICO", "SUC070": "LINDEROS", "SUC080": "LIRA", "SUC110": "LO BLANCO",
    "SUC120": "PLACILLA", "SUC130": "RANCAGUA", "SUC140": "SAN FERNANDO",
    "SUC150": "TALCA", "SUC160": "TALCA (2)", "SUC230": "MALL PLAZA NORTE",
    "SUC240": "DIEZ DE JULIO (2)", "SUC250": "BRASIL 18", "SUC260": "CONCEPCION",
    "SUC270": "GRAN AVENIDA", "SUC280": "CD REPUESTOS", "SUC310": "RANCAGUA",
    "SUC360": "OFICINAS CENTRALES",
}
SUCURSAL_ID_DEFAULT = "DESCONOCIDO"

# Seguimiento IMPORTADO: SWITCH propio del modelo ('Seguimiento Compras curifor
# importado'). OJO: NO tiene el fix del 08-jul (SUC160 "TALCA 2", SUC240 "DIEZ DE
# JULIO", SUC310 "RANCAGUA 2"). En la práctica es inocuo: el importado trae [Sucursal]
# en blanco -> siempre DESCONOCIDO (solo aporta al fallback global de proveedor).
SUCURSAL_ID_MAP_IMPORTADO = {
    "SUC020": "CHILLAN", "SUC030": "CHILLAN VIEJO", "SUC040": "COQUIMBO",
    "SUC050": "CURICO", "SUC070": "LINDEROS", "SUC080": "LIRA", "SUC110": "LO BLANCO",
    "SUC120": "PLACILLA", "SUC130": "RANCAGUA", "SUC140": "SAN FERNANDO",
    "SUC150": "TALCA", "SUC160": "TALCA 2", "SUC230": "MALL PLAZA NORTE",
    "SUC240": "DIEZ DE JULIO", "SUC250": "BRASIL 18", "SUC260": "CONCEPCION",
    "SUC270": "GRAN AVENIDA", "SUC280": "CD REPUESTOS", "SUC310": "RANCAGUA 2",
    "SUC360": "OFICINAS CENTRALES",
}

# Seguimiento FRONTERA: SucursalID = SWITCH sobre [Nombre Local] (ya viene canónico,
# con el "(2)"). El resto -> DESCONOCIDO. ('Seguimiento de Compras frontera nacional').
SUCURSAL_ID_MAP_FRONTERA = {
    "BRASIL 18": "BRASIL 18", "CD REPUESTOS": "CD REPUESTOS", "CHILLAN VIEJO": "CHILLAN VIEJO",
    "CURICO": "CURICO", "DIEZ DE JULIO (2)": "DIEZ DE JULIO (2)", "LINDEROS": "LINDEROS",
    "PLACILLA": "PLACILLA", "RANCAGUA": "RANCAGUA",
}

# Tag de Origen de cada seguimiento (columna Origen de 'Seguimiento Compras Unificado').
ORIGEN_NACIONAL = "Curifor Nacional"
ORIGEN_IMPORTADO = "Curifor Importado"
ORIGEN_FRONTERA = "Frontera Nacional"

# tipoDocto de notas de crédito: restan (CantidadAjustada = -ABS). Resto suma.
# (Regla de la columna CantidadAjustada de 'Ventas Unificadas'.) OJO: la NC de FRONTERA
# es "NOTA CREDITO ST", que NO está en esta lista -> en Frontera las NC SUMAN. Es el
# comportamiento real del modelo (la columna se calcula igual para ambas fuentes).
NC_TIPODOCTO = {
    "NC CLIENTE S/T", "NC-ELECTR REPTO", "NC SEGURO S/T", "NC LIQ FACT", "NC-ELECTR GD_FAC",
}
TIPOPRODUCTO_REPUESTOS = {"REPUESTOS", "REPUESTO"}

# Frontera (E07) — filtros que 'Ventas Unificadas' aplica DESPUÉS del SQL:
#  - Documento IN este set (subconjunto de los del WHERE SQL: excluye
#    'FACTURA REPUESTOS (E)' y 'CARGO GARANTIA').
#  - Docto-Emitido = "Emitido".
#  - tipoproducto = "REPUESTO" (este filtro es un paso M posterior al SELECT, NO va
#    en el SQL: el SELECT E07 trae todos los tipoproducto).
FRONTERA_VENTAS_DOCTOS = {
    "CARGO INTERNO", "FACTURA ST", "NOTA CREDITO ST", "REFACTURACION C/RS", "REFACTURACION ST",
}
# SUCURSAL de Frontera: el SELECT ya devuelve "NN NOMBRE"; 'Ventas Unificadas' des-prefija
# SOLO estas 5 (SWITCH), el resto queda igual ("08 TALCA", "99 Ver Sucursal", ...) y no
# matchea el sugerido -> se descarta aguas abajo. Réplica exacta de ese SWITCH.
FRONTERA_VENTAS_SUCURSAL_MAP = {
    "02 LINDEROS": "LINDEROS", "03 PLACILLA": "PLACILLA", "05 RANCAGUA": "RANCAGUA",
    "07 CURICO": "CURICO", "10 CHILLAN VIEJO": "CHILLAN VIEJO",
}

# Columnas crudas de ventas que usa el motor (comunes al SQL Curifor y al histórico).
_COLS_CRUDO_VENTAS_CURIFOR = ["Producto", "SUCURSAL", "Tipo-Venta", "Fecha", "Cantidad", "tipoDocto", "tipoproducto"]

# --- Consultas SQL (verbatim del modelo) -----------------------------------------
# Seguimiento nacional: se selecciona solo lo que el motor necesita (el modelo trae
# ~50 columnas). Incluye Fecha Documento P/E para la etapa de lead time.
SEGUIMIENTO_NACIONAL_QUERY = """
SELECT [Producto],
       [Sucursal],
       [Razón Social Proveedor]   AS RazonSocial,
       [Motivo Compra]            AS Motivo,
       [Fecha Orden de Compra]    AS FechaOC,
       [N° Orden de Compra]       AS NOC,
       [Cantidad]                 AS Cantidad,
       [Estado Orden de Compra]   AS EstadoOC,
       [Estado Documento Base]    AS EstadoDoc,
       [Fecha Documento Base]     AS FechaDoc,
       [Fecha Documento P/E]      AS FechaPE
FROM Tmp_SeguimientoCompraNacional
""".strip()

# Ventas Curifor (E01). El modelo además anexa 'Produccion Post Venta Historico (2)'
# (Excel de SharePoint, no SQL) y filtra tipoproducto IN REPUESTOS: eso se hace en
# Python (`normalizar_ventas_curifor` / `leer_ventas`).
VENTAS_CURIFOR_QUERY = (
    "select * From Tmp_ProdMensualPostVta "
    "Where Empresa = 'E01' and fecha >= '31-12-2018'"
)

# Ventas Frontera (E07): SELECT verbatim de la partición M del modelo
# 'Informe Gestión Producción REP ST GAR D&P' (Sql.Database("10.50.15.2","BDFlexline",
# [Query=...])). Se conservan los DECLARE de T-SQL (@Empresa='E07', rango de fecha
# desde 2020, @FechaFin=getdate()) tal como en el modelo. El SELECT ya devuelve
# [SUCURSAL] con prefijo "NN NOMBRE", [Documento], [Docto-Emitido], [producto],
# [cantidad], [tipoproducto], etc. Los filtros/mapeos posteriores (tipoproducto=REPUESTO,
# Docto-Emitido, Documento IN, des-prefijo de SUCURSAL) los hace `normalizar_ventas_frontera`.
VENTAS_FRONTERA_QUERY = """
Declare @Empresa Varchar(20) = 'E07'
Declare @FechaIni Datetime = '01/01/2020'
Declare @FechaFin Datetime = getdate()

SELECT
    E0.periodolibro   [Periodo],
    E0.tipodocto      [Documento],
    E0.numero,
    E0.fecha,
    E0.analisise21    [Tipo-Venta],
    E0.analisise13    [Marca],
    E0.analisise14    [Modelo],
    E0.idctacte       [Rut Cliente],
    E0.centrocosto,
    D0.producto,
    LEFT(P.glosa, 20) [Descripcion Producto],
    D0.linea          [Items],
    D0.cantidad,
    D0.neto,
    D0.total,
    E0.local,
    P.tipoproducto,
    d0.analisis9      [Tipo Cargo],

    CASE
        WHEN E0.analisise14 LIKE '            %' THEN 'MESON'
        WHEN E0.analisise14 LIKE '%NKR%' THEN 'SERIE N'
        WHEN E0.analisise14 LIKE '%NPR%' THEN 'SERIE N'
        WHEN E0.analisise14 LIKE '%NQR%' THEN 'SERIE N'
        WHEN E0.analisise14 LIKE '%FRR%' THEN 'SERIE F'
        WHEN E0.analisise14 LIKE '%FTR%' THEN 'SERIE F'
        WHEN E0.analisise14 LIKE '%FVR%' THEN 'SERIE F'
        WHEN E0.analisise14 LIKE '%DMAX%' THEN 'LIVIANOS'
        WHEN E0.analisise14 LIKE '%COLORADO%' THEN 'LIVIANOS'
        ELSE 'OTROS'
    END AS [SERIE UNIDAD],

    CASE
        WHEN p.tipoproducto = 'REPUESTO' AND D0.producto IN ('2723982','2722295','2722260','2723053','2722278','2722289') THEN 'LUBRICANTE'
        WHEN p.tipoproducto = 'REPUESTO' THEN 'REPUESTOS'
        WHEN p.tipoproducto = 'MO_TERC' THEN 'SERV. 3ro'
        WHEN p.tipoproducto = 'INTERNO' AND D0.producto LIKE 'AJUSTE ST' THEN 'MECANICA'
        WHEN p.tipoproducto = 'MO_ST' AND D0.producto LIKE 'MO_%' THEN 'MECANICA'
        WHEN p.tipoproducto = 'MO_ST' AND D0.producto LIKE 'INS%' THEN 'INSUMOS'
        ELSE 'OTROS PROD'
    END AS [TIPO PRODUCTO],

    CASE
        WHEN E0.local IN ( 'CASA MATRIZ', 'SUC010' ) THEN '01 LA FLORIDA'
        WHEN E0.local IN ( 'LO BLANCO', 'SUC110' ) THEN '01 LO BLANCO'
        WHEN E0.local IN ( 'LINDEROS', 'SUC070' ) THEN '02 LINDEROS'
        WHEN E0.local IN ( 'PLACILLA', 'SUC120' ) THEN '03 PLACILLA'
        WHEN E0.local IN ( 'COQUIMBO', 'SUC040' ) THEN '04 COQUIMBO'
        WHEN E0.local IN ( 'RANCAGUA', 'SUC130' ) THEN '05 RANCAGUA'
        WHEN E0.local IN ( 'RANCAGUA2', 'SUC190' ) THEN '06 RANCAGUA2'
        WHEN E0.local IN ( 'CURICO', 'SUC050' ) THEN '07 CURICO'
        WHEN E0.local IN ( 'TALCA', 'SUC150' ) THEN '08 TALCA'
        WHEN E0.local IN ( 'CHILLAN', 'SUC020' ) THEN '09 CHILLAN'
        WHEN E0.local IN ( 'CHILLAN VIEJO', 'SUC030' ) THEN '10 CHILLAN VIEJO'
        WHEN E0.local IN ( 'SAN FERNANDO', 'SUC140' ) THEN '11 SAN FERNANDO'
        WHEN E0.local IN ( 'DIEZ DE JULIO', 'SUC060' ) THEN '12 DIEZ DE JULIO'
        ELSE '99 Ver Sucursal'
    END AS [SUCURSAL],

    CASE
        WHEN E0.tipodocto IN ( 'NOTA CREDITO ST' ) THEN ( ( D0.costo ) * -1 )
        WHEN E0.tipodocto IN ( 'FACTURA REPUESTOS (E)', 'FACTURA ST',
                                'NOTA CREDITO ST', 'REFACTURACION ST',
                                'CARGO INTERNO', 'CARGO GARANTIA',
                                'REFACTURACION C/RS' ) THEN ( ( D0.costo ) * +1 )
    END AS 'Costo Neto',

    CASE
        WHEN E0.tipodocto IN ( 'NOTA CREDITO ST' ) THEN ( ( D0.total ) * -1 )
        WHEN E0.tipodocto IN ( 'FACTURA REPUESTOS (E)', 'FACTURA ST',
                                'NOTA CREDITO ST', 'REFACTURACION ST',
                                'CARGO INTERNO', 'CARGO GARANTIA',
                                'REFACTURACION C/RS' ) THEN ( ( D0.total ) * +1 )
    END AS 'Total Neta',

    CASE
        WHEN E0.tipodocto IN ( 'FACTURA ST', 'FACTURA REPUESTOS (E)', 'NOTA CREDITO ST', 'REFACTURACION ST', 'REFACTURACION C/RS' )
             AND E0.emitido = 'N' THEN 'Emision Pendiente'
        ELSE 'Emitido'
    END AS [Docto-Emitido],

    E0.VENDEDOR

FROM documento E0
JOIN documentod D0 ON E0.empresa = D0.empresa AND E0.tipodocto = D0.tipodocto AND E0.correlativo = D0.correlativo
JOIN producto P ON D0.empresa = P.empresa AND D0.producto = P.producto

WHERE E0.empresa = @Empresa
  AND E0.tipodocto IN ( 'FACTURA REPUESTOS (E)', 'FACTURA ST',
                        'CARGO INTERNO', 'CARGO GARANTIA',
                        'NOTA CREDITO ST', 'REFACTURACION ST',
                        'REFACTURACION C/RS' )
  AND E0.Fecha BETWEEN @FechaIni AND @FechaFin
  AND E0.vigencia <> 'A'
""".strip()


# --- Transformaciones puras (testeables sin base de datos) ------------------------
def mapear_sucursal_id(codigo: str | None) -> str:
    """Código de local (SUC0XX) -> SucursalID del seguimiento nacional (SWITCH del modelo)."""
    return SUCURSAL_ID_MAP.get(codigo, SUCURSAL_ID_DEFAULT)


def cantidad_ajustada_expr() -> pl.Expr:
    """CantidadAjustada: -ABS(Cantidad) si tipoDocto es NC, si no ABS(Cantidad)."""
    return (
        pl.when(pl.col("tipoDocto").is_in(list(NC_TIPODOCTO)))
        .then(-pl.col("Cantidad").abs())
        .otherwise(pl.col("Cantidad").abs())
    )


def normalizar_seguimiento(
    raw: pl.DataFrame,
    para_transito: bool = False,
    *,
    para_lead_time: bool = False,
    origen: str = ORIGEN_NACIONAL,
    sucursal_map: dict[str, str] = SUCURSAL_ID_MAP,
    sucursal_col: str = "Sucursal",
) -> pl.DataFrame:
    """DataFrame crudo de un seguimiento -> esquema del motor.

    Sirve para los tres orígenes (nacional/importado/frontera) variando `origen`,
    `sucursal_map` y `sucursal_col`; las columnas que un origen no traiga (p.ej.
    Frontera no tiene Motivo ni N° OC) se completan con nulo para que la UNION cuadre.

    Modo (excluyentes):
      base (default)      -> `seguimiento`: Producto, SucursalID, RazonSocial, FechaOC, NOC, Origen, Motivo
      para_transito=True  -> además Cantidad, EstadoOC, EstadoDoc, FechaDoc
      para_lead_time=True -> `seguimiento_lt` (insumo de lead_time_proveedor):
          RazonSocial, SucursalID, FechaOC, FechaPE, Origen, Motivo
    """
    if sucursal_col in raw.columns:
        suc = pl.col(sucursal_col).replace_strict(sucursal_map, default=SUCURSAL_ID_DEFAULT)
    else:  # el origen no trae columna de sucursal -> todo DESCONOCIDO
        suc = pl.lit(SUCURSAL_ID_DEFAULT)
    df = raw.with_columns(suc.alias("SucursalID"), pl.lit(origen).alias("Origen"))
    if para_lead_time:
        cols = ["RazonSocial", "SucursalID", "FechaOC", "FechaPE", "Origen", "Motivo"]
    else:
        cols = ["Producto", "SucursalID", "RazonSocial", "FechaOC", "NOC", "Origen", "Motivo"]
        if para_transito:
            cols += ["Cantidad", "EstadoOC", "EstadoDoc", "FechaDoc"]
    faltan = [c for c in cols if c not in df.columns]
    if faltan:
        df = df.with_columns([pl.lit(None).alias(c) for c in faltan])
    return df.select(cols)


def normalizar_seguimiento_importado(
    raw: pl.DataFrame, para_transito: bool = False, *, para_lead_time: bool = False
) -> pl.DataFrame:
    """Seguimiento importado (Excel) -> esquema del motor. Origen 'Curifor Importado',
    SucursalID por el SWITCH del importado (su [Sucursal] suele venir en blanco -> DESCONOCIDO).
    Para lead time el llamador aporta FechaPE desde 'Fecha Documento Recepción'."""
    return normalizar_seguimiento(
        raw, para_transito, para_lead_time=para_lead_time, origen=ORIGEN_IMPORTADO,
        sucursal_map=SUCURSAL_ID_MAP_IMPORTADO, sucursal_col="Sucursal",
    )


def normalizar_seguimiento_frontera(
    raw: pl.DataFrame, para_transito: bool = False, *, para_lead_time: bool = False
) -> pl.DataFrame:
    """Seguimiento Frontera (Excel) -> esquema del motor. Origen 'Frontera Nacional',
    SucursalID por el SWITCH sobre [Nombre Local] (columna esperada `NombreLocal`).
    En el modelo el Frontera no trae Motivo ni N° OC -> quedan nulos; FechaOC la aporta
    el llamador desde 'Fecha Documento Base' y FechaPE desde 'Fecha Recepción'."""
    return normalizar_seguimiento(
        raw, para_transito, para_lead_time=para_lead_time, origen=ORIGEN_FRONTERA,
        sucursal_map=SUCURSAL_ID_MAP_FRONTERA, sucursal_col="NombreLocal",
    )


def unir_seguimiento(
    nacional: pl.DataFrame,
    importado: pl.DataFrame | None = None,
    frontera: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """UNION de los tres seguimientos ya normalizados (réplica de 'Seguimiento Compras
    Unificado'). El nacional es obligatorio (SQL); importado/frontera son opcionales
    (Excel de SharePoint) y ya deben venir por `normalizar_seguimiento_*`."""
    frames = [f for f in (nacional, importado, frontera) if f is not None]
    if not frames:
        raise ValueError("unir_seguimiento requiere al menos el seguimiento nacional")
    return pl.concat(frames, how="vertical_relaxed")


def normalizar_ventas_curifor(
    raw: pl.DataFrame, historico: pl.DataFrame | None = None
) -> pl.DataFrame:
    """DataFrame crudo de Tmp_ProdMensualPostVta -> esquema `ventas` del motor:
    Producto, SUCURSAL, TipoVenta, Fecha, CantidadAjustada, Fuente. Filtra a repuestos.

    Si se pasa `historico` (Excel 'Produccion Post Venta Historico', ya con las mismas
    columnas crudas), se anexa ANTES de calcular — igual que el `Table.Combine` del
    modelo — para que la historia quede completa (cierra la columna Empresa)."""
    base = raw
    if historico is not None:
        base = pl.concat(
            [raw.select(_COLS_CRUDO_VENTAS_CURIFOR), historico.select(_COLS_CRUDO_VENTAS_CURIFOR)],
            how="vertical_relaxed",
        )
    df = base.filter(pl.col("tipoproducto").is_in(list(TIPOPRODUCTO_REPUESTOS)))
    return df.with_columns(
        cantidad_ajustada_expr().alias("CantidadAjustada"),
        pl.lit("Curifor").alias("Fuente"),
    ).select([
        "Producto",
        pl.col("SUCURSAL"),
        pl.col("Tipo-Venta").alias("TipoVenta"),
        "Fecha",
        "CantidadAjustada",
        "Fuente",
    ])


def normalizar_ventas_frontera(raw: pl.DataFrame) -> pl.DataFrame:
    """DataFrame crudo del SELECT E07 -> esquema `ventas` del motor (Fuente 'Frontera').

    Replica los pasos que el modelo hace DESPUÉS del SQL (paso M `tipoproducto=REPUESTO`
    + filtros y mapeos de 'Ventas Unificadas'):
      1. tipoproducto = "REPUESTO"  (filtro M posterior al SELECT).
      2. Docto-Emitido = "Emitido"  y  Documento IN FRONTERA_VENTAS_DOCTOS.
      3. SUCURSAL: des-prefija las 5 del SWITCH; el resto pasa igual.
      4. CantidadAjustada con tipoDocto = Documento (la NC de Frontera SUMA, ver NC_TIPODOCTO).
    """
    df = raw.filter(
        (pl.col("tipoproducto") == "REPUESTO")
        & (pl.col("Docto-Emitido") == "Emitido")
        & (pl.col("Documento").is_in(list(FRONTERA_VENTAS_DOCTOS)))
    )
    df = df.with_columns(
        pl.col("Documento").alias("tipoDocto"),
        pl.col("cantidad").alias("Cantidad"),
        pl.col("SUCURSAL").replace(FRONTERA_VENTAS_SUCURSAL_MAP).alias("SUCURSAL"),
    )
    return df.with_columns(
        cantidad_ajustada_expr().alias("CantidadAjustada"),
        pl.lit("Frontera").alias("Fuente"),
    ).select([
        pl.col("producto").alias("Producto"),
        pl.col("SUCURSAL"),
        pl.col("Tipo-Venta").alias("TipoVenta"),
        pl.col("fecha").alias("Fecha"),
        "CantidadAjustada",
        "Fuente",
    ])


def unir_ventas(*frames: pl.DataFrame | None) -> pl.DataFrame:
    """UNION de ventas Curifor + Frontera (mismo esquema), réplica de 'Ventas Unificadas'."""
    fs = [f for f in frames if f is not None]
    if not fs:
        raise ValueError("unir_ventas requiere al menos un DataFrame de ventas")
    return pl.concat(fs, how="vertical_relaxed")


# --- Conexión y lectura (requiere credenciales + red + driver) --------------------
def conectar(user: str | None = None, password: str | None = None):
    """Abre una conexión al SQL de Flexline con python-tds. Credenciales por env
    (FLEXLINE_SQL_USER / FLEXLINE_SQL_PASSWORD) si no se pasan. No hardcodear."""
    user = user or os.environ.get("FLEXLINE_SQL_USER")
    password = password or os.environ.get("FLEXLINE_SQL_PASSWORD")
    if not user or not password:
        raise RuntimeError(
            "Faltan credenciales del SQL de Flexline. Definir FLEXLINE_SQL_USER y "
            "FLEXLINE_SQL_PASSWORD en el entorno (nunca en el repo)."
        )
    try:
        import pytds  # noqa: PLC0415  (import perezoso: el módulo se importa sin driver)
    except ImportError as e:
        raise RuntimeError("Falta el driver: pip install python-tds") from e
    return pytds.connect(server=SQL_HOST, database=SQL_DB, user=user, password=password)


def _query_a_polars(conn, query: str) -> pl.DataFrame:
    cur = conn.cursor()
    cur.execute(query)
    cols = [c[0] for c in cur.description]
    filas = cur.fetchall()
    return pl.DataFrame(filas, schema=cols, orient="row")


def leer_seguimiento(
    conn,
    para_transito: bool = False,
    *,
    importado: pl.DataFrame | None = None,
    frontera: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Lee el seguimiento nacional del SQL y lo normaliza al esquema del motor. Si se
    pasan `importado`/`frontera` (Excel de SharePoint, crudos), los normaliza y los une
    (réplica de 'Seguimiento Compras Unificado')."""
    nacional = normalizar_seguimiento(
        _query_a_polars(conn, SEGUIMIENTO_NACIONAL_QUERY), para_transito=para_transito
    )
    if importado is None and frontera is None:
        return nacional
    imp = normalizar_seguimiento_importado(importado, para_transito) if importado is not None else None
    fro = normalizar_seguimiento_frontera(frontera, para_transito) if frontera is not None else None
    return unir_seguimiento(nacional, imp, fro)


def leer_seguimiento_lt(
    conn,
    *,
    importado: pl.DataFrame | None = None,
    frontera: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Insumo `seguimiento_lt` de `lead_time_proveedor` (RazonSocial, SucursalID,
    FechaOC, FechaPE, Origen, Motivo). El nacional sale del SQL (trae Fecha P/E);
    importado/frontera (Excel) se unen si se pasan, con su FechaPE ya mapeada."""
    nacional = normalizar_seguimiento(
        _query_a_polars(conn, SEGUIMIENTO_NACIONAL_QUERY), para_lead_time=True
    )
    if importado is None and frontera is None:
        return nacional
    imp = normalizar_seguimiento_importado(importado, para_lead_time=True) if importado is not None else None
    fro = normalizar_seguimiento_frontera(frontera, para_lead_time=True) if frontera is not None else None
    return unir_seguimiento(nacional, imp, fro)


def leer_ventas_curifor(conn, historico: pl.DataFrame | None = None) -> pl.DataFrame:
    """Lee ventas Curifor del SQL y las normaliza. `historico` = Excel de SharePoint
    'Produccion Post Venta Historico' (crudo) para anexar y cerrar la columna Empresa."""
    raw = _query_a_polars(conn, VENTAS_CURIFOR_QUERY)
    return normalizar_ventas_curifor(raw, historico=historico)


def leer_ventas_frontera(conn) -> pl.DataFrame:
    """Lee ventas Frontera (E07) del SQL y las normaliza al esquema `ventas`."""
    raw = _query_a_polars(conn, VENTAS_FRONTERA_QUERY)
    return normalizar_ventas_frontera(raw)


def leer_ventas(conn, historico: pl.DataFrame | None = None) -> pl.DataFrame:
    """Ventas del motor completas = Curifor (E01 + histórico) UNION Frontera (E07).
    Réplica de 'Ventas Unificadas'. `historico` es el Excel de SharePoint (opcional)."""
    curifor = leer_ventas_curifor(conn, historico=historico)
    frontera = leer_ventas_frontera(conn)
    return unir_ventas(curifor, frontera)
