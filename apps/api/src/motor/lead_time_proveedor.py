"""Cálculo del lead time por proveedor desde el seguimiento (réplica del modelo).

Reemplaza las tablas DERIVADAS 'Lead Time Proveedor' y 'Lead Time Proveedor
Sucursal' del Power BI, que el motor hoy consume como insumo. Con esto el motor
calcula el lead time él mismo desde el seguimiento crudo (fechas OC y P/E),
eliminando la última dependencia de una tabla que produce el modelo.

Lógica por grupo (proveedor, o proveedor+sucursal):
- OCs válidas: Fecha OC y Fecha P/E no nulas, P/E >= OC, filtro de motivo
  (origen != Nacional o motivo=reposicion) y tope de 30 días para no-importados.
- LT en días = INT(Fecha P/E - Fecha OC).
- Percentil de corte = 0.7 si en el grupo predominan las OCs nacionales de
  reposición (<30d) sobre las no-nacionales, si no 0.8.
- Lead Time Dias = promedio de los LT que caen en/bajo ese percentil (INC).
- N Muestras (tabla sucursal) = cuántos LT entran en ese promedio.

Todas las comparaciones de texto en minúscula (DAX es case-insensitive).
"""
from __future__ import annotations

import polars as pl

from . import parametros as P


def _preparar(seg: pl.DataFrame) -> pl.DataFrame:
    """Agrega LT en días y los flags de las OCs (válidas, nacionales, otras)."""
    origen = pl.col("Origen")
    motivo = pl.col("Motivo").str.to_lowercase()
    lt = (pl.col("FechaPE") - pl.col("FechaOC")).dt.total_days()
    fechas_ok = pl.col("FechaOC").is_not_null() & pl.col("FechaPE").is_not_null() & (pl.col("FechaPE") >= pl.col("FechaOC"))
    return seg.with_columns(
        lt.alias("lt_dias"),
        fechas_ok.alias("_fok"),
    ).with_columns(
        # OC válida para el promedio: fechas ok + filtro motivo + tope 30 (salvo importado).
        (
            pl.col("_fok")
            & ((origen != P.ORIGEN_NACIONAL) | (motivo == P.MOTIVO_REPOSICION))
            & ((origen == P.ORIGEN_IMPORTADO) | (pl.col("lt_dias") < P.LT_TOPE_DIAS))
        ).alias("_valida"),
        # nNac: nacional + reposicion + LT<30 (para elegir el percentil).
        (
            pl.col("_fok")
            & (origen == P.ORIGEN_NACIONAL)
            & (motivo == P.MOTIVO_REPOSICION)
            & (pl.col("lt_dias") < P.LT_TOPE_DIAS)
        ).alias("_nac"),
        # nOtros: fechas ok + no nacional (sin tope de 30).
        (pl.col("_fok") & (origen != P.ORIGEN_NACIONAL)).alias("_otros"),
    )


def _percentil_corte(base: pl.DataFrame, keys: list[str], pctiles: pl.DataFrame) -> pl.DataFrame:
    """Percentil INC (interpolación lineal) del LT por grupo, al pctil de cada grupo.
    Se separa por valor de pctil porque quantile toma un escalar."""
    b = base.join(pctiles, on=keys, how="inner", nulls_equal=True)
    partes = []
    for q in (P.LT_PCTIL_NAC, P.LT_PCTIL_OTROS):
        sub = b.filter(pl.col("pctil") == q)
        if sub.height:
            partes.append(
                sub.group_by(keys).agg(pl.col("lt_dias").quantile(q, interpolation="linear").alias("pcorte"))
            )
    return pl.concat(partes) if partes else pl.DataFrame(schema={**{k: pl.Utf8 for k in keys}, "pcorte": pl.Float64})


def _calcular(seg: pl.DataFrame, keys: list[str], con_muestras: bool) -> pl.DataFrame:
    """Tabla de lead time agrupada por `keys` (proveedor, o proveedor+sucursal)."""
    df = _preparar(seg)

    # nNac / nOtros por grupo -> percentil de corte.
    counts = df.group_by(keys).agg(
        pl.col("_nac").sum().alias("n_nac"),
        pl.col("_otros").sum().alias("n_otros"),
    ).with_columns(
        pl.when(pl.col("n_nac") > pl.col("n_otros")).then(P.LT_PCTIL_NAC).otherwise(P.LT_PCTIL_OTROS).alias("pctil")
    )

    base = df.filter(pl.col("_valida")).select([*keys, "lt_dias"])
    # el grupo existe solo si tiene >=1 OC válida.
    grupos_validos = base.select(keys).unique()
    pctiles = counts.join(grupos_validos, on=keys, how="semi", nulls_equal=True).select([*keys, "pctil"])

    pcorte = _percentil_corte(base, keys, pctiles)

    bajo_corte = base.join(pcorte, on=keys, how="inner", nulls_equal=True).filter(pl.col("lt_dias") <= pl.col("pcorte"))
    agg = [pl.col("lt_dias").mean().alias("Lead Time Dias")]
    if con_muestras:
        agg.append(pl.len().alias("N Muestras"))
    return bajo_corte.group_by(keys).agg(agg)


def calcular_lead_time_proveedor(seguimiento_lt: pl.DataFrame) -> pl.DataFrame:
    """Tabla 'Lead Time Proveedor': Razon Social Proveedor -> Lead Time Dias."""
    r = _calcular(seguimiento_lt, ["RazonSocial"], con_muestras=False)
    return r.rename({"RazonSocial": "Razon Social Proveedor"})


def calcular_lead_time_proveedor_sucursal(seguimiento_lt: pl.DataFrame) -> pl.DataFrame:
    """Tabla 'Lead Time Proveedor Sucursal': + SucursalID, N Muestras.
    Excluye sucursal DESCONOCIDO y proveedor nulo."""
    seg = seguimiento_lt.filter(
        (pl.col("SucursalID") != P.SUCURSAL_DESCONOCIDA) & pl.col("RazonSocial").is_not_null()
    )
    r = _calcular(seg, ["RazonSocial", "SucursalID"], con_muestras=True)
    return r.rename({"RazonSocial": "Razon Social Proveedor"})
