"""Pipeline end-to-end del motor: encadena las 5 etapas y produce el CSV con el
contrato EXACTO de la plataforma (mismas cabeceras que la extracción DAX de la
sync: columnas físicas de 'Sugerido por Sucursal' + medidas en snake_case, ver
`powerbi_dax_query` y `excel_loader.HEADER_ALIASES` en el repo de la plataforma).

Uso típico (con los CSV de paridad como fuentes):

    from datetime import date
    from src.motor import pipeline
    f = pipeline.cargar_fuentes("data/paridad")
    df = pipeline.ejecutar(f, fin_mes_cerrado=date(2026, 7, 1), hoy=date(2026, 7, 6))
    pipeline.exportar_csv(df, "sugerido_motor.csv")

Columnas del catálogo/costo (Descripcion, FILTRO1_Final, Unidad de Medida,
Costo Unitario, total_valor_sugerido_clp): se llenan si están las fuentes
`dim_producto_catalogo.csv` (Dim Producto) y `stock_costo.csv` (Stock Bodegas
[Costo]); si faltan, esas columnas salen vacías. Costo Unitario = MAX(VALUE(Costo))
del grupo de reemplazos; Valor CLP = Sugerido × Costo.

Nota: `Tiene Stock CD` el modelo lo saca de 'Stock Unificado'; aquí se APROXIMA
con Stock Bodegas + Frontera en CD > 0 (coincide 100% en la corroboración).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from . import parametros as P
from .clasificacion_abc import calcular_abc
from .demanda import calcular_demanda
from .lead_time import calcular_lead_time
from .lead_time_proveedor import calcular_lead_time_proveedor, calcular_lead_time_proveedor_sucursal
from .safety_stock import calcular_safety_stock
from .sugerido import _grupo_reemplazos, _stock_activo, calcular_sugerido
from .traslados import calcular_traslados

_LOCAL = ["producto_master", "sucursal_final"]

# (nombre en Dim Sucursal ausente) -> nombre que muestra el modelo.
_NOMBRE_FALLBACK = {
    "TALCA (2)": "Talca (2)",
    "DIEZ DE JULIO (2)": "Diez de Julio (2)",
    "LINDEROS VTA MOVIL": "LINDEROS VTA MOVIL",
}

_S = {"Producto": pl.Utf8, "SucursalID": pl.Utf8}


def cargar_fuentes(directorio: str | Path) -> dict[str, pl.DataFrame]:
    """Lee las fuentes desde un directorio con el layout de data/paridad."""
    d = Path(directorio)

    def _csv(nombre: str, **kw) -> pl.DataFrame:
        return pl.read_csv(d / nombre, schema_overrides=_S, **kw)

    fuentes = {
        "ventas": _csv("ventas_12m.csv", try_parse_dates=True),
        "mapeo": pl.read_csv(d / "mapeo_master.csv"),
        "dim_producto": _csv("dim_producto.csv"),
        "dim_sucursal": _csv("dim_sucursal.csv"),
        "seguimiento": _csv("seguimiento.csv", try_parse_dates=True),
        "seguimiento_transito": _csv("seguimiento_transito.csv", try_parse_dates=True),
        "lt_proveedor": pl.read_csv(d / "lt_proveedor.csv"),
        "lt_proveedor_sucursal": pl.read_csv(d / "lt_proveedor_sucursal.csv"),
        "importados": _csv("importados.csv"),
        "stock": _csv("stock_bodegas.csv"),
        "stock_frontera": _csv("stock_frontera.csv"),
    }
    # Catálogo (Descripcion/Marca/Unidad) y costo son opcionales: si no están,
    # esas columnas del contrato salen vacías (como antes de conectarlos).
    cat = d / "dim_producto_catalogo.csv"
    if cat.exists():
        fuentes["catalogo"] = _csv("dim_producto_catalogo.csv")
    costo = d / "stock_costo.csv"
    if costo.exists():
        # Costo llega como texto (trae placeholders " -"); se castea con VALUE al usarlo.
        fuentes["costo"] = pl.read_csv(costo, infer_schema_length=0)
    # Seguimiento con Fecha P/E: si está, el motor CALCULA las tablas de lead time
    # (en vez de leer lt_proveedor*.csv que derivan del modelo).
    seg_lt = d / "seguimiento_lt.csv"
    if seg_lt.exists():
        fuentes["seguimiento_lt"] = _csv("seguimiento_lt.csv", try_parse_dates=True)
    return fuentes


def _empresa(ventas_limpias: pl.DataFrame) -> pl.DataFrame:
    """Solo Curifor / Solo Frontera / Ambas por (producto, sucursal), según la
    Fuente de las ventas limpias 12m (mismo EXCEPT del modelo)."""
    combos = (
        ventas_limpias.select([*_LOCAL, "Fuente"])
        .unique()
        .group_by(_LOCAL)
        .agg(
            (pl.col("Fuente") == "Frontera").any().alias("_front"),
            (pl.col("Fuente") == "Curifor").any().alias("_curi"),
        )
    )
    return combos.with_columns(
        pl.when(pl.col("_front") & ~pl.col("_curi")).then(pl.lit("Solo Frontera"))
        .when(pl.col("_front")).then(pl.lit("Ambas"))
        .otherwise(pl.lit("Solo Curifor"))
        .alias("empresa")
    ).select([*_LOCAL, "empresa"])


def _pivot_stock_bodegas(sa_todas: pl.DataFrame, productos: pl.DataFrame) -> pl.DataFrame:
    """Columnas 'Stock LINDEROS'...'Stock TALCA (2)' (grupo de reemplazos)."""
    r = productos
    for suc in P.SUCURSALES_STOCK_COLUMNAS:
        col = (
            sa_todas.filter(pl.col("sucursal_final") == suc)
            .select(["producto_master", pl.col("stock_activo").cast(pl.Int64).alias(f"Stock {suc}")])
        )
        r = r.join(col, on="producto_master", how="left")
    return r


def ejecutar(
    fuentes: dict[str, pl.DataFrame],
    fin_mes_cerrado: date,
    hoy: date,
) -> pl.DataFrame:
    """Corre las 5 etapas y devuelve el frame final con el contrato de la plataforma."""
    ventas = fuentes["ventas"]
    mapeo = fuentes["mapeo"]
    dim_p = fuentes["dim_producto"]
    dim_s = fuentes["dim_sucursal"]
    importados = fuentes["importados"].get_column("Producto").to_list()

    # Etapas 1-5 (cada una con paridad 100% demostrada contra el modelo).
    abc = calcular_abc(ventas, mapeo, dim_p, fin_mes_cerrado)
    dem = calcular_demanda(ventas, mapeo, dim_p, abc, fin_mes_cerrado)
    # Tablas de lead time: calculadas desde el seguimiento (fresco) si está, si no
    # se leen las que derivan del modelo (lt_proveedor*.csv).
    if "seguimiento_lt" in fuentes:
        lt_prov = calcular_lead_time_proveedor(fuentes["seguimiento_lt"])
        lt_prov_suc = calcular_lead_time_proveedor_sucursal(fuentes["seguimiento_lt"])
    else:
        lt_prov, lt_prov_suc = fuentes["lt_proveedor"], fuentes["lt_proveedor_sucursal"]
    lt = calcular_lead_time(abc, fuentes["seguimiento"], lt_prov, lt_prov_suc, dim_s, importados)
    ss = calcular_safety_stock(lt, dem)
    sug = calcular_sugerido(ss, dem, fuentes["stock"], fuentes["stock_frontera"],
                            fuentes["seguimiento_transito"], mapeo, hoy)
    r = calcular_traslados(sug, mapeo, fuentes["stock"], fuentes["stock_frontera"], dim_s)

    # --- Enriquecimientos del contrato ---
    r = r.join(abc.select([*_LOCAL, "m3", "m6", "m12"]), on=_LOCAL, how="left")
    r = r.join(dem.select([*_LOCAL, "demanda_mensual", "desv_std_mensual", "demanda_diaria"]),
               on=_LOCAL, how="left")

    # Nombre Sucursal: Dim Sucursal -> fallbacks del modelo -> el ID.
    nombres = dim_s.select(pl.col("SucursalID"), pl.col("Nombre").alias("_nombre"))
    r = r.join(nombres, left_on="sucursal_final", right_on="SucursalID", how="left")
    r = r.with_columns(
        pl.coalesce(
            pl.col("_nombre"),
            pl.col("sucursal_final").replace_strict(_NOMBRE_FALLBACK, default=None),
            pl.col("sucursal_final"),
        ).alias("nombre_sucursal")
    ).drop("_nombre")

    # Empresa (Fuente de las ventas 12m). Sin ventas (filas sintéticas) -> Solo Curifor.
    from .clasificacion_abc import preparar_ventas

    vl = preparar_ventas(ventas, mapeo, dim_p)
    r = r.join(_empresa(vl), on=_LOCAL, how="left").with_columns(
        pl.col("empresa").fill_null("Solo Curifor")
    )

    # Reemplazos: los otros productos del grupo (excluye el master).
    reempl = (
        mapeo.filter(pl.col("Producto") != pl.col("Producto_Master"))
        .group_by("Producto_Master")
        .agg(pl.col("Producto").str.join(", ").alias("reemplazos"))
        .rename({"Producto_Master": "producto_master"})
    )
    r = r.join(reempl, on="producto_master", how="left")

    # Sucursales Origen CD: en la fila CD con agregada A/B, las sucursales C/D
    # locales cuya demanda consolida (orden no garantizado por el modelo).
    origen_cd = (
        r.filter(
            (pl.col("sucursal_final") != P.CD_ID)
            & pl.col("clasificacion_abc").is_in(["C", "D"])
            & pl.col("clasificacion_abc_agregada").is_in(["A", "B"])
        )
        .group_by("producto_master")
        .agg(pl.col("sucursal_final").str.join(", ").alias("sucursales_origen_cd"))
    )
    r = r.join(origen_cd, on="producto_master", how="left").with_columns(
        pl.when(
            (pl.col("sucursal_final") == P.CD_ID)
            & pl.col("clasificacion_abc_agregada").is_in(["A", "B"])
        )
        .then(pl.col("sucursales_origen_cd"))
        .otherwise(None)
        .alias("sucursales_origen_cd")
    )

    # Stock por bodega (11 columnas fijas, grupo de reemplazos).
    miembros = _grupo_reemplazos(r, mapeo)
    sa_todas = _stock_activo(miembros, fuentes["stock"], fuentes["stock_frontera"])
    r = r.join(
        _pivot_stock_bodegas(sa_todas, r.select("producto_master").unique()),
        on="producto_master", how="left",
    )

    # Tiene Stock CD (aprox; el modelo usa 'Stock Unificado', ver docstring).
    con_stock_cd = (
        pl.concat([
            fuentes["stock"].select(["Producto", "SucursalID", "Stock"]),
            fuentes["stock_frontera"].select(["Producto", "SucursalID", "Stock"]),
        ])
        .filter((pl.col("SucursalID") == P.CD_ID) & (pl.col("Stock") > 0))
        .get_column("Producto").unique().to_list()
    )
    r = r.with_columns(
        pl.col("producto_master").is_in(con_stock_cd).alias("tiene_stock_cd"),
        pl.when(pl.col("es_importado")).then(pl.lit("Importado")).otherwise(pl.lit("Nacional")).alias("tipo_origen"),
    )

    # --- Catálogo: Descripcion, Marca (FILTRO1_Final), Unidad (LOOKUPVALUE por master) ---
    if "catalogo" in fuentes:
        cat = fuentes["catalogo"].unique(subset=["Producto"], keep="first").rename({
            "Descripcion": "descripcion_cat", "FILTRO1_Final": "filtro1_cat", "UnidadMedida": "unidad_cat",
        })
        r = r.join(cat, left_on="producto_master", right_on="Producto", how="left")
    else:
        r = r.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("descripcion_cat"),
            pl.lit(None, dtype=pl.Utf8).alias("filtro1_cat"),
            pl.lit(None, dtype=pl.Utf8).alias("unidad_cat"),
        )

    # --- Costo Unitario: MAX(VALUE(Costo)) del grupo en Stock Bodegas (como el modelo) ---
    if "costo" in fuentes:
        costo = (
            fuentes["costo"].with_columns(pl.col("Costo").cast(pl.Float64, strict=False))
            .filter(pl.col("Costo").is_not_null())
            .group_by("Producto").agg(pl.col("Costo").max().alias("costo_unitario"))
        )
        r = r.join(costo, left_on="producto_master", right_on="Producto", how="left")
    else:
        r = r.with_columns(pl.lit(None, dtype=pl.Float64).alias("costo_unitario"))

    # Valor Sugerido CLP = Sugerido * Costo (solo si sugerido>0 y hay costo).
    r = r.with_columns(
        pl.when((pl.col("sugerido") > 0) & pl.col("costo_unitario").is_not_null())
        .then(pl.col("sugerido") * pl.col("costo_unitario"))
        .otherwise(None)
        .alias("valor_clp")
    )
    return r


# Contrato de salida: cabecera del CSV -> expresión sobre el frame de ejecutar().
# Nombres idénticos a los que produce la extracción DAX de la plataforma.
_CONTRATO: list[tuple[str, str]] = [
    ("Producto", "producto_master"),
    ("Descripcion", "descripcion_cat"),
    ("SucursalID", "sucursal_final"),
    ("Nombre Sucursal", "nombre_sucursal"),
    ("Meses con Venta 3m", "m3"),
    ("Meses con Venta 6m", "m6"),
    ("Meses con Venta 12m", "m12"),
    ("Clasificacion ABC", "clasificacion_abc"),
    ("Clasificacion ABC Agregada", "clasificacion_abc_agregada"),
    ("Proveedor", "proveedor"),
    ("Lead Time Dias", "lead_time_dias"),
    ("LT Origen", "lt_origen"),
    ("LT CD a Sucursal Dias", "lt_cd_a_sucursal_dias"),
    ("LT Efectivo", "lt_efectivo"),
    ("Abastece CD", "abastece_cd"),
    ("Prioridad CD", "prioridad_cd"),
    ("Demanda Mensual", "demanda_mensual"),
    ("Desv Std Mensual", "desv_std_mensual"),
    ("Demanda Diaria", "demanda_diaria"),
    ("Stock de Seguridad", "stock_seguridad"),
    ("Costo Unitario", "costo_unitario"),
    ("Es Importado", "es_importado"),
    ("Tiene Stock CD", "tiene_stock_cd"),
    ("FILTRO1_Final", "filtro1_cat"),
    ("Unidad de Medida", "unidad_cat"),
    ("Sucursales Origen CD", "sucursales_origen_cd"),
    ("Reemplazos", "reemplazos"),
    ("Empresa", "empresa"),
    ("Pedir", "pedir"),
    ("Tipo Origen", "tipo_origen"),
    ("Punto de Pedido", "punto_pedido"),
    # Medidas (alias snake_case idénticos a powerbi_dax_query de la plataforma).
    ("total_sugerido_suc", "sugerido"),
    ("total_valor_sugerido_clp", "valor_clp"),
    ("sugerido_suc", "sugerido"),
    ("stock_activo_suc", "stock_activo"),
    ("stock_en_transito_suc", "stock_transito"),
    ("stock_en_cd", "stock_cd"),
    ("sugerido_traslado", "sugerido_traslado"),
    ("sugerido_compra_neto", "compra_neta"),
    ("comprar_en_el_cd", "comprar_en_cd"),
    ("pedir_flag", "pedir"),
    ("trasladar_desde", "trasladar_desde"),
]


def contrato(df: pl.DataFrame) -> pl.DataFrame:
    """Proyecta el frame del motor al contrato de la plataforma (+ stocks por bodega)."""
    cols = []
    for cabecera, campo in _CONTRATO:
        if campo == "_null":
            cols.append(pl.lit(None, dtype=pl.Utf8).alias(cabecera))
        else:
            cols.append(pl.col(campo).alias(cabecera))
    cols += [pl.col(f"Stock {s}") for s in P.SUCURSALES_STOCK_COLUMNAS]
    return df.select(cols)


def exportar_csv(df: pl.DataFrame, ruta: str | Path) -> Path:
    """Escribe el CSV final (UTF-8, booleanos como True/False igual que la sync)."""
    out = contrato(df).with_columns(
        pl.when(pl.col("Es Importado")).then(pl.lit("True")).otherwise(pl.lit("False")).alias("Es Importado"),
        pl.when(pl.col("Tiene Stock CD")).then(pl.lit("True")).otherwise(pl.lit("False")).alias("Tiene Stock CD"),
    )
    ruta = Path(ruta)
    out.write_csv(ruta)
    return ruta
