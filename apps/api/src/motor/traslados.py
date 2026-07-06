"""Traslados desde el CD y laterales (réplica del modelo DAX).

- Stock en CD: stock del grupo de reemplazos en CD REPUESTOS (Curifor+Frontera).
- Sugerido Traslado: reparto secuencial del stock del CD entre las sucursales
  elegibles (clase local C/D + agregada A/B, sin el CD) por Prioridad CD:
  traslado = MIN(necesidad_bruta, MAX(stock_cd − necesidad de las de prioridad
  menor, 0)); solo si la fila y el stock son > 0, si no BLANK.
- Comprar en el CD: "Si" cuando al llegar el turno (prioridad acumulada,
  incluyéndose) la demanda supera el stock del CD (o no hay stock).
- Sugerido Compra Neto: INT(sugerido − COALESCE(traslado, 0)) si sugerido > 0.
- Traslado desde Otras Sucursales (lateral, informativo): para filas con
  sugerido > 0, lista las otras operativas con stock del grupo, ordenadas por
  stock DESC: "N unidades desde NOMBRE; ...".
"""
from __future__ import annotations

import polars as pl

from . import parametros as P
from .sugerido import _grupo_reemplazos, _stock_activo

_LOCAL = ["producto_master", "sucursal_final"]


def _fmt_miles(expr: pl.Expr) -> pl.Expr:
    """FORMAT(x, "#,##0") del modelo: separador de miles '.' (cultura es-CL)."""
    entero = expr.cast(pl.Int64)
    return (
        pl.when(entero >= 1000)
        .then(
            (entero // 1000).cast(pl.Utf8)
            + pl.lit(".")
            + (entero % 1000).cast(pl.Utf8).str.zfill(3)
        )
        .otherwise(entero.cast(pl.Utf8))
    )


def calcular_traslados(
    sug: pl.DataFrame,
    mapeo: pl.DataFrame,
    stock: pl.DataFrame,
    stock_frontera: pl.DataFrame,
    dim_sucursal: pl.DataFrame,
) -> pl.DataFrame:
    """sug: salida de sugerido.calcular_sugerido. Devuelve el frame con
    prioridad_cd, stock_cd, sugerido_traslado, comprar_en_cd, compra_neta y
    trasladar_desde."""
    miembros = _grupo_reemplazos(sug, mapeo)
    sa_todas = _stock_activo(miembros, stock, stock_frontera)

    r = sug.with_columns(
        pl.col("sucursal_final")
        .replace_strict(P.PRIORIDAD_CD, default=P.PRIORIDAD_CD_DEFAULT)
        .alias("prioridad_cd")
    )

    # Stock en CD por producto (grupo completo; sin fila CD -> null == BLANK).
    stock_cd = (
        sa_todas.filter(pl.col("sucursal_final") == P.CD_ID)
        .select(["producto_master", pl.col("stock_activo").alias("stock_cd")])
    )
    r = r.join(stock_cd, on="producto_master", how="left")

    # --- Reparto por prioridad: necesidad acumulada de las elegibles ---
    elegible = (
        (pl.col("sucursal_final") != P.CD_ID)
        & pl.col("clasificacion_abc").is_in(list(P.CLASES_LOCAL_RUTEADAS_CD))
        & pl.col("clasificacion_abc_agregada").is_in(list(P.CLASES_AGG_QUE_CONSOLIDA_CD))
    )
    r = r.with_columns(elegible.alias("_elegible"))
    r = r.sort(["producto_master", "prioridad_cd"]).with_columns(
        pl.when(pl.col("_elegible"))
        .then(pl.col("necesidad_bruta"))
        .otherwise(0.0)
        .cum_sum()
        .over("producto_master")
        .alias("_acumulada")
    )
    previa = pl.col("_acumulada") - pl.when(pl.col("_elegible")).then(
        pl.col("necesidad_bruta")
    ).otherwise(0.0)

    disponible = pl.max_horizontal(pl.col("stock_cd") - previa, pl.lit(0.0))
    traslado = pl.min_horizontal(pl.col("necesidad_bruta"), disponible)
    r = r.with_columns(
        pl.when(
            pl.col("_elegible")
            & (pl.col("necesidad_bruta") > 0)
            & (pl.col("stock_cd") > 0)  # null -> false, igual que ISBLANK
            & (traslado > 0)
        )
        .then(traslado.floor())
        .otherwise(None)
        .alias("sugerido_traslado"),
        pl.when(pl.col("_elegible"))
        .then(
            pl.when(
                pl.col("stock_cd").is_null()
                | (pl.col("stock_cd") <= 0)
                | (pl.col("_acumulada") > pl.col("stock_cd"))
            )
            .then(pl.lit("Si"))
            .otherwise(pl.lit("No"))
        )
        .otherwise(None)
        .alias("comprar_en_cd"),
    )

    r = r.with_columns(
        pl.when(pl.col("sugerido") > 0)
        .then((pl.col("sugerido") - pl.col("sugerido_traslado").fill_null(0)).floor())
        .otherwise(None)
        .alias("compra_neta")
    ).drop(["_elegible", "_acumulada"])

    # --- Traslado lateral entre operativas (texto informativo) ---
    nombres = dim_sucursal.select(
        pl.col("SucursalID").alias("_suc"), pl.col("Nombre").alias("_nombre")
    )
    orden_op = {s: i for i, s in enumerate(P.SUCURSALES_OPERATIVAS)}
    fuentes = (
        r.filter(pl.col("sugerido") > 0)
        .select([*_LOCAL, "sugerido"])
        .join(
            sa_todas.filter(pl.col("sucursal_final").is_in(list(P.SUCURSALES_OPERATIVAS)))
            .rename({"sucursal_final": "_suc", "stock_activo": "_st"}),
            on="producto_master",
            how="inner",
        )
        .filter((pl.col("_suc") != pl.col("sucursal_final")) & (pl.col("_st") > 0))
        .join(nombres, on="_suc", how="left")
        .with_columns(
            pl.col("_suc").replace_strict(orden_op, default=99).alias("_orden"),
            (
                _fmt_miles(pl.min_horizontal(pl.col("sugerido"), pl.col("_st")))
                + pl.lit(" unidades desde ")
                + pl.coalesce(pl.col("_nombre"), pl.col("_suc"))
            ).alias("_txt"),
        )
        .sort(["producto_master", "sucursal_final", "_st", "_orden"], descending=[False, False, True, False])
        .group_by(_LOCAL, maintain_order=True)
        .agg(pl.col("_txt").str.join("; ").alias("trasladar_desde"))
    )
    return r.join(fuentes, on=_LOCAL, how="left")
