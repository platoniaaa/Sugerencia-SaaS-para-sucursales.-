"""Stock de seguridad (réplica del modelo DAX).

SS = ROUND(Z * sigma * sqrt((LT_efectivo + CO) / 22), 0)
- Z por clase (agregada si es CD, local si no); reducido para importado-desde-CD.
- CO = 3 si se abastece del CD, 5 si no.
- sigma = desviación estándar mensual (winsorizada).
Redondeo comercial (half away from zero) como DAX, no bancario.
"""
from __future__ import annotations

import polars as pl

from . import parametros as P

_LOCAL = ["producto_master", "sucursal_final"]


def _round_com(expr: pl.Expr) -> pl.Expr:
    """ROUND a entero half-away-from-zero (SS es >= 0)."""
    return (expr + 0.5).floor()


def calcular_safety_stock(lead_time: pl.DataFrame, demanda: pl.DataFrame) -> pl.DataFrame:
    r = lead_time.join(demanda.select([*_LOCAL, "desv_std_mensual"]), on=_LOCAL, how="left")

    es_cd = pl.col("sucursal_final") == P.CD_ID
    clase_z = pl.when(es_cd).then(pl.col("clasificacion_abc_agregada")).otherwise(pl.col("clasificacion_abc"))
    co = pl.when(pl.col("abastece_cd") == "Si").then(P.CICLO_ORDEN_DIAS_CD).otherwise(P.CICLO_ORDEN_DIAS)
    proteccion = (pl.col("lt_efectivo") + co) / P.DIAS_HABILES_MES
    es_imp_cd = (pl.col("abastece_cd") == "Si") & pl.col("es_importado")

    z = (
        pl.when(es_imp_cd & (clase_z == "A")).then(P.Z_IMPORTADO_CD["A"])
        .when(es_imp_cd & (clase_z == "B")).then(P.Z_IMPORTADO_CD["B"])
        .when(clase_z == "A").then(P.Z_POR_CLASE["A"])
        .when(clase_z == "B").then(P.Z_POR_CLASE["B"])
        .when(clase_z == "C").then(P.Z_POR_CLASE["C"])
        .otherwise(0.0)
    )
    sigma = pl.col("desv_std_mensual")
    ss = _round_com(z * sigma * proteccion.sqrt())

    return r.with_columns(
        pl.when(sigma.is_not_null()).then(ss).otherwise(None).cast(pl.Int64).alias("stock_seguridad")
    )
