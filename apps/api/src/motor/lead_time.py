"""Proveedor, lead time y abastecimiento CD (réplica del modelo DAX).

- Proveedor: razón social de la OC más reciente (por producto × sucursal).
- ProveedorLT: mínimo alfabético de razón social en el seguimiento filtrado por
  motivo, con jerarquía suc → global → (sin filtro de motivo).
- Lead Time Dias: LT del par (proveedor, sucursal) si hay muestra, si no el LT
  global del proveedor, si no fallback 8.
- LT CD a Sucursal: 1 día RM / 2 resto, con casos especiales.
- Abastece CD: importado O (clase local C/D + agregada A/B); en la fila CD, solo
  si es importado.
- LT Efectivo: LT CD si se abastece del CD, si no el LT del proveedor.
"""
from __future__ import annotations

import polars as pl

from . import parametros as P


def _proveedor_lt(abc: pl.DataFrame, seg: pl.DataFrame) -> pl.DataFrame:
    """MIN(razón social) con jerarquía suc/global, filtrado y sin filtrar motivo."""
    con_prov = seg.filter(pl.col("RazonSocial").is_not_null())
    filtrado = con_prov.filter(
        (pl.col("Origen") != P.ORIGEN_CURIFOR_NACIONAL) | (pl.col("Motivo").str.to_lowercase() == P.MOTIVO_REPOSICION)
    )

    def _min_por(df, keys, nombre):
        # MIN de DAX sobre texto es case-insensitive; el min() de polars ordena
        # por bytes (mayúsculas < minúsculas). Ordenar por clave en minúscula.
        return df.group_by(keys).agg(
            pl.col("RazonSocial")
            .sort_by(pl.col("RazonSocial").str.to_lowercase())
            .first()
            .alias(nombre)
        )

    combos = abc.select(["producto_master", "sucursal_final"])
    r = (
        combos.join(
            _min_por(filtrado, ["Producto", "SucursalID"], "provSuc"),
            left_on=["producto_master", "sucursal_final"], right_on=["Producto", "SucursalID"], how="left",
        )
        .join(_min_por(filtrado, ["Producto"], "provGlobal"),
              left_on="producto_master", right_on="Producto", how="left")
        .join(_min_por(con_prov, ["Producto", "SucursalID"], "provSucFull"),
              left_on=["producto_master", "sucursal_final"], right_on=["Producto", "SucursalID"], how="left")
        .join(_min_por(con_prov, ["Producto"], "provGlobalFull"),
              left_on="producto_master", right_on="Producto", how="left")
    )
    return r.with_columns(
        pl.coalesce("provSuc", "provGlobal", "provSucFull", "provGlobalFull").alias("proveedor_lt")
    ).select(["producto_master", "sucursal_final", "proveedor_lt"])


def _proveedor_oc_reciente(abc: pl.DataFrame, seg: pl.DataFrame) -> pl.DataFrame:
    """Razón social de la OC más reciente (Fecha OC desc, N OC desc) por par."""
    valido = seg.filter(
        ((pl.col("Origen") != P.ORIGEN_CURIFOR_NACIONAL) | (pl.col("Motivo").str.to_lowercase() == P.MOTIVO_REPOSICION))
        & pl.col("RazonSocial").is_not_null()
        & pl.col("FechaOC").is_not_null()
    ).with_columns(pl.col("NOC").fill_null(-1))
    # OC más reciente por par: ordenar dentro del grupo (Fecha OC desc, N OC desc).
    reciente = valido.group_by(["Producto", "SucursalID"]).agg(
        pl.col("RazonSocial").sort_by(["FechaOC", "NOC"], descending=[True, True]).first().alias("RazonSocial")
    )
    return abc.select(["producto_master", "sucursal_final"]).join(
        reciente, left_on=["producto_master", "sucursal_final"],
        right_on=["Producto", "SucursalID"], how="left",
    ).rename({"RazonSocial": "proveedor"})


def calcular_lead_time(
    abc: pl.DataFrame,
    seguimiento: pl.DataFrame,
    lt_prov: pl.DataFrame,
    lt_prov_suc: pl.DataFrame,
    dim_sucursal: pl.DataFrame,
    importados: list[str],
) -> pl.DataFrame:
    local = ["producto_master", "sucursal_final"]
    r = abc.select([*local, "clasificacion_abc", "clasificacion_abc_agregada"])
    r = r.join(_proveedor_lt(abc, seguimiento), on=local, how="left")
    r = r.join(_proveedor_oc_reciente(abc, seguimiento), on=local, how="left")

    # LT por (proveedor, sucursal) con muestra, y global por proveedor.
    lts = lt_prov_suc.filter(pl.col("N Muestras") >= 1).group_by(
        ["Razon Social Proveedor", "SucursalID"]
    ).agg(pl.col("Lead Time Dias").max().alias("lt_spec"))
    ltg = lt_prov.group_by("Razon Social Proveedor").agg(pl.col("Lead Time Dias").max().alias("lt_global"))

    r = r.join(
        lts, left_on=["proveedor_lt", "sucursal_final"],
        right_on=["Razon Social Proveedor", "SucursalID"], how="left",
    ).join(ltg, left_on="proveedor_lt", right_on="Razon Social Proveedor", how="left")

    lt = pl.coalesce("lt_spec", "lt_global")
    r = r.with_columns(
        pl.when(lt.is_null() | pl.col("proveedor_lt").is_null())
        .then(pl.lit(float(P.LT_FALLBACK_DIAS)))
        .otherwise(lt)
        .alias("lead_time_dias"),
        pl.when(pl.col("lt_spec").is_not_null())
        .then(pl.lit("Por sucursal"))
        .when(pl.col("lt_global").is_not_null() & pl.col("proveedor_lt").is_not_null())
        .then(pl.lit("Global proveedor"))
        .otherwise(pl.lit("Fallback 8 dias"))
        .alias("lt_origen"),
    )

    # LT CD a sucursal (por región + especiales).
    reg = dim_sucursal.select(["SucursalID", "Region"])
    r = r.join(reg, left_on="sucursal_final", right_on="SucursalID", how="left")
    r = r.with_columns(
        pl.when(pl.col("sucursal_final") == "TALCA (2)").then(2)
        .when(pl.col("sucursal_final") == "DIEZ DE JULIO (2)").then(1)
        .when(pl.col("sucursal_final") == "LINDEROS VTA MOVIL").then(1)
        .when(pl.col("Region") == "RM").then(1)
        .when(pl.col("Region").is_not_null()).then(2)
        .otherwise(2)
        .alias("lt_cd_a_sucursal_dias")
    )

    # Abastece CD.
    es_imp = pl.col("producto_master").is_in(importados)
    r = r.with_columns(es_imp.alias("es_importado"))
    r = r.with_columns(
        pl.when(pl.col("sucursal_final") == P.CD_ID)
        .then(pl.when(pl.col("es_importado")).then(pl.lit("Si")).otherwise(pl.lit("No")))
        .otherwise(
            pl.when(
                pl.col("es_importado")
                | (pl.col("clasificacion_abc").is_in(["C", "D"]) & pl.col("clasificacion_abc_agregada").is_in(["A", "B"]))
            ).then(pl.lit("Si")).otherwise(pl.lit("No"))
        )
        .alias("abastece_cd")
    )

    # LT Efectivo.
    r = r.with_columns(
        pl.when(pl.col("abastece_cd") == "Si")
        .then(pl.col("lt_cd_a_sucursal_dias").cast(pl.Float64))
        .otherwise(pl.col("lead_time_dias"))
        .alias("lt_efectivo")
    )
    return r
