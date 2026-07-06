"""Demanda mensual y desviación estándar (réplica del modelo DAX).

Para cada (producto_master, sucursal_final) arma la serie mensual de la venta
(suma de CantidadAjustada por mes, con 0 en meses sin actividad), la winsoriza
con mediana + MAD, y toma el promedio (demanda) y la desviación muestral.

Ventana: clase A/B → 6 meses; clase C/D → 12 meses (igual que DemLocal del DAX).
El CD con clase agregada A/B es un caso especial: consolida su venta + la de las
sucursales clase-C/D-local del producto sobre 12 meses, y winsoriza igual
(cambio 2026-07: antes era promedio simple sin winsorizar).
"""
from __future__ import annotations

from datetime import date

import polars as pl

from . import parametros as P
from .clasificacion_abc import _inicio_ventana, preparar_ventas


def _meses_ventana(ini_yyyymm: str, n: int) -> list[str]:
    y, m = int(ini_yyyymm[:4]), int(ini_yyyymm[4:])
    base = y * 12 + (m - 1)
    return [f"{(base + i) // 12:04d}{(base + i) % 12 + 1:02d}" for i in range(n)]


def _serie_completa(totales: pl.DataFrame, grupos: pl.DataFrame, meses: list[str], keys: list[str]) -> pl.DataFrame:
    """Cross join grupos × meses de la ventana, trae el total mensual (0 si falta)."""
    malla = grupos.join(pl.DataFrame({"mes": meses}), how="cross")
    return malla.join(totales, on=[*keys, "mes"], how="left").with_columns(
        pl.col("total").fill_null(0.0)
    )


def _winsorizar(serie: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    """Winsoriza la serie por grupo (mediana + 1.4826*MAD) y devuelve demanda
    (promedio) y desv std muestral de la serie winsorizada."""
    s = serie.with_columns(pl.col("total").median().over(keys).alias("_med"))
    s = s.with_columns((pl.col("total") - pl.col("_med")).abs().alias("_ad"))
    s = s.with_columns(pl.col("_ad").median().over(keys).alias("_mad"))
    s = s.with_columns((pl.col("_med") + P.WINSOR_K * P.WINSOR_ESCALA_MAD * pl.col("_mad")).alias("_tope"))
    s = s.with_columns(
        pl.when(pl.col("_mad") == 0)
        .then(pl.col("total"))
        .otherwise(pl.min_horizontal(pl.col("total"), pl.col("_tope")))
        .alias("_tw")
    )
    return s.group_by(keys).agg(
        pl.col("_tw").mean().alias("demanda_mensual"),
        pl.col("_tw").std(ddof=1).alias("desv_std_mensual"),
    )


def calcular_demanda(
    ventas: pl.DataFrame,
    mapeo: pl.DataFrame,
    dim_producto: pl.DataFrame,
    abc: pl.DataFrame,
    fin_mes_cerrado: date,
) -> pl.DataFrame:
    """abc: salida de clasificacion_abc.calcular_abc (con producto_master,
    sucursal_final, clasificacion_abc, clasificacion_abc_agregada)."""
    v = preparar_ventas(ventas, mapeo, dim_producto).with_columns(
        pl.col("Fecha").dt.strftime("%Y%m").alias("mes")
    )
    local = ["producto_master", "sucursal_final"]
    totales = v.group_by([*local, "mes"]).agg(pl.col("CantidadAjustada").sum().alias("total"))

    meses6 = _meses_ventana(_inicio_ventana(fin_mes_cerrado, P.VENTANA_M6), 6)
    meses12 = _meses_ventana(_inicio_ventana(fin_mes_cerrado, P.VENTANA_M12), 12)

    # --- DemLocal: por clase LOCAL, ventana 6m (A/B) o 12m (C/D) ---
    grupos = abc.select([*local, "clasificacion_abc", "clasificacion_abc_agregada"])
    g_ab = grupos.filter(pl.col("clasificacion_abc").is_in(["A", "B"])).select(local)
    g_cd = grupos.filter(pl.col("clasificacion_abc").is_in(["C", "D"])).select(local)

    dem_ab = _winsorizar(_serie_completa(totales, g_ab, meses6, local), local)
    dem_cd = _winsorizar(_serie_completa(totales, g_cd, meses12, local), local)
    dem_local = pl.concat([dem_ab, dem_cd])

    base = grupos.join(dem_local, on=local, how="left")

    # --- CD con clase agregada A/B: serie 12m consolidada + winsorizada ---
    cd_ab = grupos.filter(
        (pl.col("sucursal_final") == P.CD_ID) & pl.col("clasificacion_abc_agregada").is_in(["A", "B"])
    ).select("producto_master").unique()

    if cd_ab.height:
        # sucursales que el CD consolida: clase local C/D (por producto).
        sucsD = grupos.filter(
            (pl.col("sucursal_final") != P.CD_ID) & pl.col("clasificacion_abc").is_in(["C", "D"])
        ).select(["producto_master", "sucursal_final"])
        consolidar = pl.concat([
            cd_ab.with_columns(pl.lit(P.CD_ID).alias("sucursal_final")),
            sucsD.join(cd_ab, on="producto_master", how="inner"),
        ]).unique()

        vcd = v.join(consolidar, on=local, how="inner")
        totales_cd = vcd.group_by(["producto_master", "mes"]).agg(
            pl.col("CantidadAjustada").sum().alias("total")
        )
        serie_cd = _serie_completa(totales_cd, cd_ab, meses12, ["producto_master"])
        dem_cd_ab = _winsorizar(serie_cd, ["producto_master"]).with_columns(
            pl.lit(P.CD_ID).alias("sucursal_final")
        )

        # override sobre la base para esas filas del CD.
        base = base.join(
            dem_cd_ab.rename({"demanda_mensual": "_dem_cd", "desv_std_mensual": "_desv_cd"}),
            on=local, how="left",
        ).with_columns(
            pl.coalesce(pl.col("_dem_cd"), pl.col("demanda_mensual")).alias("demanda_mensual"),
            pl.coalesce(pl.col("_desv_cd"), pl.col("desv_std_mensual")).alias("desv_std_mensual"),
        ).drop(["_dem_cd", "_desv_cd"])

    return base.with_columns(
        (pl.col("demanda_mensual") / P.DIAS_HABILES_MES).alias("demanda_diaria")
    )
