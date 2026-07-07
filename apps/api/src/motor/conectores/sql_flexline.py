"""Conector al SQL Server de Flexline (ERP de Curifor).

Lee, en vivo, las fuentes que el Power BI hoy saca del mismo SQL:
- **Seguimiento de compras nacional**: `Tmp_SeguimientoCompraNacional` (Empresa E01).
- **Ventas Curifor**: `Tmp_ProdMensualPostVta` (Empresa E01, fecha ≥ 2018-12-31).
- **Ventas Frontera**: `Informe Gestión ...` (Empresa E07). Query largo — se toma
  verbatim del modelo (ver `VENTAS_FRONTERA_QUERY`).

Las consultas SQL están tomadas de las particiones M del modelo (`Sql.Database(
"10.50.15.2","BDFlexline",...)`). Las transformaciones que el modelo hace DESPUÉS
en Power Query / DAX (mapeo de SucursalID, tag de Origen, CantidadAjustada) se
replican aquí en Python, para entregar el mismo esquema que hoy consume el motor.

ESTADO: **no ejecutado / no probado** — requiere (1) credenciales del ERP (por env,
nunca en el repo), (2) `pip install python-tds` (o pyodbc), (3) correr DENTRO de la
red de Curifor (10.50.15.2 es IP privada de la LAN). Las funciones de transformación
pura (mapeo de sucursal, cantidad ajustada, normalización) SÍ están cubiertas por
tests offline con datos sintéticos (`tests_motor/test_conector_sql.py`).

Lo que NO cubre (ver FUENTES_REALES.md): el seguimiento importado y el de Frontera
(este último es un Excel de SharePoint, no SQL), y la etapa lead-time-desde-seguimiento.
"""
from __future__ import annotations

import os

import polars as pl

# --- Conexión (parámetros por variables de entorno; credenciales fuera del repo) ---
SQL_HOST = os.environ.get("FLEXLINE_SQL_HOST", "10.50.15.2")
SQL_DB = os.environ.get("FLEXLINE_SQL_DB", "BDFlexline")

# --- Mapeo código de local -> SucursalID (SWITCH de la columna calculada del modelo,
# tabla 'Seguimiento Compras curifor nacional'[SucursalID]). ---
SUCURSAL_ID_MAP = {
    "SUC020": "CHILLAN", "SUC030": "CHILLAN VIEJO", "SUC040": "COQUIMBO",
    "SUC050": "CURICO", "SUC070": "LINDEROS", "SUC080": "LIRA", "SUC110": "LO BLANCO",
    "SUC120": "PLACILLA", "SUC130": "RANCAGUA", "SUC140": "SAN FERNANDO",
    "SUC150": "TALCA", "SUC160": "TALCA 2", "SUC230": "MALL PLAZA NORTE",
    "SUC240": "DIEZ DE JULIO", "SUC250": "BRASIL 18", "SUC260": "CONCEPCION",
    "SUC270": "GRAN AVENIDA", "SUC280": "CD REPUESTOS", "SUC310": "RANCAGUA",
    "SUC360": "OFICINAS CENTRALES",
}
SUCURSAL_ID_DEFAULT = "DESCONOCIDO"

# tipoDocto de notas de crédito: restan (CantidadAjustada = -ABS). Resto suma.
# (Regla de la columna CantidadAjustada de 'Ventas Unificadas'.)
NC_TIPODOCTO = {
    "NC CLIENTE S/T", "NC-ELECTR REPTO", "NC SEGURO S/T", "NC LIQ FACT", "NC-ELECTR GD_FAC",
}
TIPOPRODUCTO_REPUESTOS = {"REPUESTOS", "REPUESTO"}

# --- Consultas SQL (verbatim del modelo) -----------------------------------------
# Seguimiento nacional: se selecciona solo lo que el motor necesita (el modelo trae
# ~50 columnas). Incluye Fecha Documento P/E para la futura etapa de lead time.
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
# (tabla histórica aparte) y filtra tipoproducto IN REPUESTOS: eso se hace en Python.
VENTAS_CURIFOR_QUERY = (
    "select * From Tmp_ProdMensualPostVta "
    "Where Empresa = 'E01' and fecha >= '31-12-2018'"
)

# Ventas Frontera (E07): query largo con CASE de SUCURSAL y clasificaciones. Debe
# copiarse COMPLETO desde la partición M del modelo 'Informe Gestión Producción REP
# ST GAR D&P' (Sql.Database("10.50.15.2","BDFlexline",[Query=...])). Al ejecutarlo,
# el propio SQL ya devuelve [SUCURSAL], [Tipo-Venta], [Documento], [producto],
# [cantidad], [tipoproducto]. Placeholder hasta pegar el texto exacto.
VENTAS_FRONTERA_QUERY = None  # TODO: pegar el query E07 del modelo (ver FUENTES_REALES.md)


# --- Transformaciones puras (testeables sin base de datos) ------------------------
def mapear_sucursal_id(codigo: str | None) -> str:
    """Código de local (SUC0XX) -> SucursalID, como el SWITCH del modelo."""
    return SUCURSAL_ID_MAP.get(codigo, SUCURSAL_ID_DEFAULT)


def cantidad_ajustada_expr() -> pl.Expr:
    """CantidadAjustada: -ABS(Cantidad) si tipoDocto es NC, si no ABS(Cantidad)."""
    return (
        pl.when(pl.col("tipoDocto").is_in(list(NC_TIPODOCTO)))
        .then(-pl.col("Cantidad").abs())
        .otherwise(pl.col("Cantidad").abs())
    )


def normalizar_seguimiento(raw: pl.DataFrame, para_transito: bool = False) -> pl.DataFrame:
    """DataFrame crudo del SQL nacional -> esquema del motor.

    para_transito=False -> columnas de `seguimiento` (lead time):
        Producto, SucursalID, RazonSocial, FechaOC, NOC, Origen, Motivo
    para_transito=True  -> además Cantidad, EstadoOC, EstadoDoc, FechaDoc
    """
    df = raw.with_columns(
        pl.col("Sucursal").replace_strict(SUCURSAL_ID_MAP, default=SUCURSAL_ID_DEFAULT).alias("SucursalID"),
        pl.lit("Curifor Nacional").alias("Origen"),
    )
    cols = ["Producto", "SucursalID", "RazonSocial", "FechaOC", "NOC", "Origen", "Motivo"]
    if para_transito:
        cols += ["Cantidad", "EstadoOC", "EstadoDoc", "FechaDoc"]
    return df.select(cols)


def normalizar_ventas_curifor(raw: pl.DataFrame) -> pl.DataFrame:
    """DataFrame crudo de Tmp_ProdMensualPostVta -> esquema `ventas` del motor:
    Producto, SUCURSAL, TipoVenta, Fecha, CantidadAjustada, Fuente. Filtra a repuestos."""
    df = raw.filter(pl.col("tipoproducto").is_in(list(TIPOPRODUCTO_REPUESTOS)))
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


def leer_seguimiento(conn, para_transito: bool = False) -> pl.DataFrame:
    """Lee el seguimiento nacional del SQL y lo normaliza al esquema del motor.
    OJO: solo nacional; importado y Frontera-Excel son fuentes aparte (unir después)."""
    raw = _query_a_polars(conn, SEGUIMIENTO_NACIONAL_QUERY)
    return normalizar_seguimiento(raw, para_transito=para_transito)


def leer_ventas_curifor(conn) -> pl.DataFrame:
    """Lee ventas Curifor del SQL y las normaliza. Falta anexar el histórico
    'Produccion Post Venta Historico (2)' (tabla aparte del modelo)."""
    raw = _query_a_polars(conn, VENTAS_CURIFOR_QUERY)
    return normalizar_ventas_curifor(raw)
