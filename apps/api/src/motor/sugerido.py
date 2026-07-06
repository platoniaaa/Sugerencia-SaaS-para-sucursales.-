"""Sugerido de compra por sucursal (réplica del modelo DAX).

Sugerido Suc = MAX(0, ROUND(DD*(CO+LT_ef) + SS - SA - ST, 0)) si la clase que
compra (agregada para el CD, local para sucursales) es A/B; si no, 0.
- Necesidad Bruta = lo mismo SIN el flag de clase (la usan los traslados).
- Punto de Pedido = ROUND(DD*LT_ef + SS, 0) — sin CO: define cuándo, no cuánto.
- SA (stock activo) suma el stock del grupo de reemplazos (master + hijos) en
  Stock Bodegas + Stock bodegas frontera.
- ST (tránsito) suma OCs pendientes vigentes SOLO del producto master (la
  relación bidireccional del modelo anula la expansión de reemplazos): Curifor
  Nacional con motivo reposicion <=30 días, Curifor Importado <=180, Frontera
  Nacional por documento base <=30.

Todas las comparaciones de texto van en minúscula: DAX es case-insensitive.
"""
from __future__ import annotations

from datetime import date

import polars as pl

from . import parametros as P

_LOCAL = ["producto_master", "sucursal_final"]


def _round_com(expr: pl.Expr) -> pl.Expr:
    """ROUND de DAX (half away from zero) a entero; aquí siempre seguido de un
    piso en 0, así que basta la rama positiva."""
    return (expr + 0.5).floor()


def _grupo_reemplazos(productos: pl.DataFrame, mapeo: pl.DataFrame) -> pl.DataFrame:
    """(producto_master, miembro): el master y todos los productos cuyo master
    es él, según Mapeo Producto Master."""
    hijos = mapeo.select(
        pl.col("Producto_Master").alias("producto_master"),
        pl.col("Producto").alias("miembro"),
    )
    propios = productos.select(pl.col("producto_master")).unique().with_columns(
        pl.col("producto_master").alias("miembro")
    )
    return pl.concat([propios, hijos.join(propios.select("producto_master"), on="producto_master", how="semi")]).unique()


def _stock_activo(miembros: pl.DataFrame, stock: pl.DataFrame, stock_frontera: pl.DataFrame) -> pl.DataFrame:
    """Suma de stock del grupo por sucursal (Curifor + Frontera)."""
    todo = pl.concat([
        stock.select(["Producto", "SucursalID", "Stock"]),
        stock_frontera.select(["Producto", "SucursalID", "Stock"]),
    ])
    return (
        miembros.join(todo, left_on="miembro", right_on="Producto", how="inner")
        .group_by(["producto_master", "SucursalID"])
        .agg(pl.col("Stock").sum().alias("stock_activo"))
        .rename({"SucursalID": "sucursal_final"})
    )


def _stock_transito(seg: pl.DataFrame, hoy: date) -> pl.DataFrame:
    """Tránsito vigente por (producto, sucursal) desde el seguimiento.

    SIN expandir el grupo de reemplazos: aunque la medida DAX intenta expandir
    con TREATAS, la relación bidireccional Sugerido⇄Dim Producto→Seguimiento
    deja el seguimiento pre-filtrado al master y la intersección anula la
    expansión. El comportamiento real del modelo (y del Excel de la
    plataforma) es tránsito solo del producto master."""
    estado_oc = pl.col("EstadoOC").str.to_lowercase()
    estado_doc = pl.col("EstadoDoc").str.to_lowercase()
    origen = pl.col("Origen").str.to_lowercase()
    motivo = pl.col("Motivo").str.to_lowercase()
    dias_oc = (pl.lit(hoy) - pl.col("FechaOC")).dt.total_days()
    dias_doc = (pl.lit(hoy) - pl.col("FechaDoc")).dt.total_days()

    curifor = (
        (estado_oc == "pendiente")
        & pl.col("FechaOC").is_not_null()
        & (
            ((origen == "curifor nacional") & (motivo == P.MOTIVO_REPOSICION) & (dias_oc <= 30))
            | ((origen == "curifor importado") & (dias_oc <= 180))
        )
    )
    frontera = (
        (origen == "frontera nacional")
        & (estado_doc == "pendiente")
        & pl.col("FechaDoc").is_not_null()
        & (dias_doc <= 30)
    )

    vigente = seg.filter(curifor | frontera)  # orígenes disjuntos: unión == suma de ambas ramas
    return (
        vigente.group_by(["Producto", "SucursalID"])
        .agg(pl.col("Cantidad").sum().alias("stock_transito"))
        .rename({"Producto": "producto_master", "SucursalID": "sucursal_final"})
    )


def calcular_sugerido(
    safety: pl.DataFrame,
    demanda: pl.DataFrame,
    stock: pl.DataFrame,
    stock_frontera: pl.DataFrame,
    seg_transito: pl.DataFrame,
    mapeo: pl.DataFrame,
    hoy: date,
) -> pl.DataFrame:
    """safety: salida de safety_stock.calcular_safety_stock (trae clases,
    abastece_cd, lt_efectivo, stock_seguridad). Devuelve el frame con
    stock_activo, stock_transito, sugerido, necesidad_bruta, punto_pedido, pedir."""
    r = safety.join(demanda.select([*_LOCAL, "demanda_diaria"]), on=_LOCAL, how="left")

    miembros = _grupo_reemplazos(r, mapeo)
    r = (
        r.join(_stock_activo(miembros, stock, stock_frontera), on=_LOCAL, how="left")
        .join(_stock_transito(seg_transito, hoy), on=_LOCAL, how="left")
        .with_columns(
            pl.col("stock_activo").fill_null(0),
            pl.col("stock_transito").fill_null(0),
        )
    )

    dd = pl.col("demanda_diaria")
    lt = pl.col("lt_efectivo")
    ss = pl.col("stock_seguridad").fill_null(0)
    co = (
        pl.when(pl.col("abastece_cd") == "Si")
        .then(P.CICLO_ORDEN_DIAS_CD)
        .otherwise(P.CICLO_ORDEN_DIAS)
    )
    es_cd = pl.col("sucursal_final") == P.CD_ID
    compra = (
        pl.when(es_cd)
        .then(pl.col("clasificacion_abc_agregada").is_in(["A", "B"]))
        .otherwise(pl.col("clasificacion_abc").is_in(["A", "B"]))
    )

    bruto = dd * (co + lt) + ss - pl.col("stock_activo") - pl.col("stock_transito")
    reposicion = pl.max_horizontal(_round_com(bruto), pl.lit(0.0))

    return r.with_columns(
        pl.when(compra & dd.is_not_null()).then(reposicion).otherwise(0.0).alias("sugerido"),
        pl.when(dd.is_not_null()).then(reposicion).otherwise(0.0).alias("necesidad_bruta"),
        pl.when(dd.is_not_null()).then(_round_com(dd * lt + ss)).otherwise(None).alias("punto_pedido"),
    ).with_columns(
        pl.when(pl.col("sugerido") > 0).then(pl.lit("Si")).otherwise(pl.lit("No")).alias("pedir")
    )
