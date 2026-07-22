"""Clasificación ABC por frecuencia de venta (réplica del modelo DAX).

Cuenta en cuántos meses distintos hubo venta (CantidadAjustada > 0) en ventanas
de 3/6/12 meses, a nivel local (producto_master × sucursal_final) y agregado
(producto_master), y aplica el SWITCH de parametros.clasificar_abc.

Es paridad con la partición 'Sugerido por Sucursal': VentasLimpias + SUCURSAL_FINAL
+ Producto_Master + conteo de meses. La ventana temporal se deriva de la fecha de
corte (primer día del mes en curso).
"""
from __future__ import annotations

from datetime import date

import polars as pl

from . import parametros as P


def _inicio_ventana(fin_mes_cerrado: date, meses_atras: int) -> str:
    """Devuelve 'YYYYMM' del primer mes de la ventana. Igual que el DAX:
    UltimoMesCerrado = mes anterior a fin_mes_cerrado; Ini = UltimoMes - (n-1)."""
    total = (fin_mes_cerrado.year * 12 + (fin_mes_cerrado.month - 1)) - 1  # UltimoMesCerrado
    ini = total - (meses_atras - 1)
    return f"{ini // 12:04d}{ini % 12 + 1:02d}"


def preparar_ventas(
    ventas: pl.DataFrame,
    mapeo: pl.DataFrame,
    dim_producto: pl.DataFrame,
) -> pl.DataFrame:
    """Aplica Producto_Master, SUCURSAL_FINAL y VentasLimpias (exclusiones).
    Devuelve las filas limpias con columnas producto_master, sucursal_final, mes,
    cantidad_ajustada."""
    mapeo_u = mapeo.unique(subset=["Producto"], keep="first")
    v = ventas.join(mapeo_u, on="Producto", how="left").with_columns(
        pl.coalesce(pl.col("Producto_Master"), pl.col("Producto")).alias("producto_master")
    )

    # SUCURSAL_FINAL: 1) LINDEROS+VTA MOVIL, 2) RANCAGUA 2, 3) especiales -> CD.
    s0 = (
        pl.when((pl.col("SUCURSAL") == P.SUCURSAL_LINDEROS) & (pl.col("TipoVenta") == P.TIPO_VENTA_MOVIL))
        .then(pl.lit(P.SUCURSAL_LINDEROS_MOVIL))
        .when(pl.col("SUCURSAL") == "RANCAGUA 2")
        .then(pl.lit("RANCAGUA"))
        .otherwise(pl.col("SUCURSAL"))
    )
    v = v.with_columns(s0.alias("_s0")).with_columns(
        pl.when(pl.col("_s0").is_in(list(P.ESPECIALES_CD)))
        .then(pl.lit(P.CD_ID))
        .otherwise(pl.col("_s0"))
        .alias("sucursal_final")
    )

    cat_excl = (
        dim_producto.filter(pl.col("Categoria").is_in(list(P.CATEGORIAS_EXCLUIDAS)))
        .get_column("Producto")
        .to_list()
    )

    v = v.filter(
        pl.col("Producto").is_not_null()
        & pl.col("sucursal_final").is_not_null()
        & ~pl.col("sucursal_final").is_in(list(P.SUCURSALES_EXCLUIDAS))
        & ~pl.col("producto_master").is_in(list(P.PRODUCTOS_EXCLUIDOS))
        & ~pl.col("Producto").is_in(cat_excl)
    )

    return v.with_columns(pl.col("Fecha").dt.strftime("%Y%m").alias("mes"))


def _contar_meses(vpos: pl.DataFrame, ini: str, keys: list[str], nombre: str) -> pl.DataFrame:
    """Meses distintos con venta (>=1 fila positiva) desde 'ini', por keys."""
    return (
        vpos.filter(pl.col("mes") >= ini)
        .select([*keys, "mes"])
        .unique()
        .group_by(keys)
        .agg(pl.len().alias(nombre))
    )


def calcular_abc(
    ventas: pl.DataFrame,
    mapeo: pl.DataFrame,
    dim_producto: pl.DataFrame,
    fin_mes_cerrado: date,
) -> pl.DataFrame:
    """Devuelve un DataFrame con producto_master, sucursal_final, m3/m6/m12,
    clasificacion_abc (local) y clasificacion_abc_agregada."""
    v = preparar_ventas(ventas, mapeo, dim_producto)
    vpos = v.filter(pl.col("CantidadAjustada") > 0)

    ini3 = _inicio_ventana(fin_mes_cerrado, P.VENTANA_M3)
    ini6 = _inicio_ventana(fin_mes_cerrado, P.VENTANA_M6)
    ini12 = _inicio_ventana(fin_mes_cerrado, P.VENTANA_M12)

    local = ["producto_master", "sucursal_final"]
    agg = ["producto_master"]

    # Los combos salen de los ULTIMOS 12 MESES, no de todo lo que se haya cargado
    # (DAX: CombosVenta = DISTINCT(SELECTCOLUMNS(Ventas12m, ...))). Sacarlos de `v`
    # entero agregaba una fila por cada combo que vendio antes de la ventana y nada
    # dentro: 6.769 filas fantasma, todas clase D con m3=m6=m12=0.
    combos = v.filter(pl.col("mes") >= ini12).select(local).unique()

    def _m(keys, ini, nom):
        return _contar_meses(vpos, ini, keys, nom)

    abc = (
        combos.join(_m(local, ini3, "m3"), on=local, how="left")
        .join(_m(local, ini6, "m6"), on=local, how="left")
        .join(_m(local, ini12, "m12"), on=local, how="left")
        .fill_null(0)
    )
    agg_df = (
        combos.select(agg).unique()
        .join(_m(agg, ini3, "m3a"), on=agg, how="left")
        .join(_m(agg, ini6, "m6a"), on=agg, how="left")
        .join(_m(agg, ini12, "m12a"), on=agg, how="left")
        .fill_null(0)
    )

    abc = abc.join(agg_df, on=agg, how="left")

    def switch_expr(m3, m6, m12):
        return (
            pl.when(pl.col(m6) >= 5).then(pl.lit("A"))
            .when(pl.col(m6) == 4).then(pl.lit("B"))
            .when((pl.col(m6) == 3) & (pl.col(m3) >= 2)).then(pl.lit("C"))
            .when((pl.col(m12) > 6) & (pl.col(m6) == 3) & (pl.col(m3) < 2)).then(pl.lit("C"))
            .otherwise(pl.lit("D"))
        )

    base = abc.with_columns(
        switch_expr("m3", "m6", "m12").alias("clasificacion_abc"),
        switch_expr("m3a", "m6a", "m12a").alias("clasificacion_abc_agregada"),
    )

    # Filas sintéticas del CD (routing de centralización): productos con cola
    # C/D local y agregada A/B que no tienen fila propia en el CD. Nacen con
    # m3/m6/m12 = 0 y clase local "D" (igual que FilasCDExtra en el DAX).
    cola = base.filter(
        pl.col("clasificacion_abc").is_in(["C", "D"])
        & pl.col("clasificacion_abc_agregada").is_in(["A", "B"])
    ).select("producto_master").unique()
    existentes = base.filter(pl.col("sucursal_final") == P.CD_ID).select("producto_master").unique()
    extra = cola.join(existentes, on="producto_master", how="anti")
    if extra.height:
        info_agg = base.select(
            ["producto_master", "m3a", "m6a", "m12a", "clasificacion_abc_agregada"]
        ).unique(subset=["producto_master"])
        filas = (
            extra.join(info_agg, on="producto_master", how="left")
            .with_columns(
                pl.lit(P.CD_ID).alias("sucursal_final"),
                pl.lit(0).alias("m3"),
                pl.lit(0).alias("m6"),
                pl.lit(0).alias("m12"),
                pl.lit("D").alias("clasificacion_abc"),
            )
            .select(base.columns)
        )
        base = pl.concat([base, filas], how="vertical_relaxed")
    return base
