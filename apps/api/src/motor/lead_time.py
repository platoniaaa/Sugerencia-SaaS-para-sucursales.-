"""Proveedor, lead time y abastecimiento CD (réplica del modelo DAX).

- Proveedor: razón social de la OC más reciente (por producto × sucursal).
  Si no hay reposición confirmada en la sucursal, se rellena con ProveedorLT
  (cambio jul-2026, espejo del COALESCE del DAX).
- ProveedorLT: mínimo alfabético de razón social en el seguimiento filtrado por
  motivo, con jerarquía suc → global → (sin filtro de motivo).
- Lead Time Dias: LT del par (proveedor, sucursal) si hay muestra, si no el LT
  global del proveedor, si no `P.LT_FALLBACK_DIAS` (3 desde ago-2026, antes 8).
  A todos se les suma el dia de gestion de Abastecimiento.
- LT CD a Sucursal: 1 día RM / 2 resto, con casos especiales.
- Abastece CD: importado O (clase local D + A/B en la agregada de las sucursales
  D); en la fila CD, solo si es importado. Antes era "C/D local + agregada A/B"
  sobre todas las sucursales (cambio de Abastecimiento, ago-2026).
- LT Efectivo: LT CD si se abastece del CD, si no el LT del proveedor.
"""
from __future__ import annotations

import polars as pl

from . import parametros as P


def _con_proveedor(seg: pl.DataFrame) -> pl.DataFrame:
    """Las OC que traen razón social: lo único de donde sale un proveedor."""
    return seg.filter(pl.col("RazonSocial").is_not_null())


def _solo_reposicion(df: pl.DataFrame) -> pl.DataFrame:
    """Descarta las compras nacionales que no son de reposición.

    Una OC de garantía o de un pedido puntual dice a quién se le compró esa vez,
    no a quién se le repone. El importado y Frontera no se filtran porque su
    motivo no viene informado.
    """
    return df.filter(
        (pl.col("Origen") != P.ORIGEN_CURIFOR_NACIONAL)
        | (pl.col("Motivo").str.to_lowercase() == P.MOTIVO_REPOSICION)
    )


def _min_por(df: pl.DataFrame, keys: list[str], nombre: str) -> pl.DataFrame:
    # MIN de DAX sobre texto es case-insensitive; el min() de polars ordena
    # por bytes (mayúsculas < minúsculas). Ordenar por clave en minúscula.
    return df.group_by(keys).agg(
        pl.col("RazonSocial")
        .sort_by(pl.col("RazonSocial").str.to_lowercase())
        .first()
        .alias(nombre)
    )


def proveedor_por_producto(seg: pl.DataFrame) -> pl.DataFrame:
    """A quién se le compra cada producto, sin mirar la sucursal.

    Es el escalón GLOBAL de la misma jerarquía que usa `_proveedor_lt`: primero
    con el filtro de motivo, y si ahí no hay nada, sin filtrarlo. Se comparte el
    código a propósito — si las dos reglas se separaran, la plataforma mostraría
    un proveedor y el sugerido otro para el mismo repuesto.

    Se calcula sobre TODO el seguimiento, no sobre los pares del sugerido: sirve
    para las filas que el motor no evalúa (mínimo InStock, sugerencias manuales),
    que salían sin proveedor aunque el producto tuviera decenas de OC.

    Devuelve `Producto`, `proveedor`.
    """
    con_prov = _con_proveedor(seg)
    if con_prov.is_empty():
        return pl.DataFrame(schema={"Producto": pl.Utf8, "proveedor": pl.Utf8})
    return (
        _min_por(con_prov, ["Producto"], "provFull")
        .join(_min_por(_solo_reposicion(con_prov), ["Producto"], "provRepo"),
              on="Producto", how="left")
        .with_columns(pl.coalesce("provRepo", "provFull").alias("proveedor"))
        .select(["Producto", "proveedor"])
    )


def _proveedor_lt(abc: pl.DataFrame, seg: pl.DataFrame) -> pl.DataFrame:
    """MIN(razón social) con jerarquía suc/global, filtrado y sin filtrar motivo."""
    con_prov = _con_proveedor(seg)
    filtrado = _solo_reposicion(con_prov)

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
    valido = _solo_reposicion(_con_proveedor(seg)).filter(
        pl.col("FechaOC").is_not_null()
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
    r = abc.select([*local, "clasificacion_abc", "clasificacion_abc_agregada",
                    "clasificacion_abc_agregada_d"])
    r = r.join(_proveedor_lt(abc, seguimiento), on=local, how="left")
    r = r.join(_proveedor_oc_reciente(abc, seguimiento), on=local, how="left")

    # El proveedor mostrado rellena los blancos (par sin reposición confirmada en
    # la sucursal) con el proveedor deducido global. Espejo del cambio jul-2026 del
    # DAX: "Proveedor" = COALESCE([Proveedor], [ProveedorLT]). Válido porque el
    # código es 1:1 con el proveedor (si cambia el proveedor, cambia el código).
    r = r.with_columns(pl.coalesce("proveedor", "proveedor_lt").alias("proveedor"))

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
    # Se suma la gestion de Abastecimiento: el LT medido va de la fecha de la OC a
    # la recepcion, asi que el tramo previo -revisar el sugerido, decidir, emitir la
    # orden- no estaba en ninguna parte y el modelo asumia que la OC sale el mismo
    # dia que aparece la necesidad. Va tambien sobre el fallback: cuando no hay
    # historial el proveedor se desconoce, pero la gestion ocurre igual.
    gestion = float(P.LT_GESTION_ABASTECIMIENTO_DIAS)
    r = r.with_columns(
        pl.when(lt.is_null() | pl.col("proveedor_lt").is_null())
        .then(pl.lit(float(P.LT_FALLBACK_DIAS) + gestion))
        .otherwise(lt + gestion)
        .alias("lead_time_dias"),
        pl.when(pl.col("lt_spec").is_not_null())
        .then(pl.lit("Por sucursal"))
        .when(pl.col("lt_global").is_not_null() & pl.col("proveedor_lt").is_not_null())
        .then(pl.lit("Global proveedor"))
        # El texto lleva el numero del parametro: tenerlo escrito a mano hacia que
        # dijera "Fallback 8 dias" al lado de una columna que mostraba otra cifra.
        .otherwise(pl.lit(f"Fallback {int(P.LT_FALLBACK_DIAS)} dias"))
        .alias("lt_origen"),
    )

    # LT CD a sucursal (por región + especiales).
    reg = dim_sucursal.select(["SucursalID", "Region"])
    r = r.join(reg, left_on="sucursal_final", right_on="SucursalID", how="left")
    r = r.with_columns(
        # Casos especiales fijos; el resto por region (RM vs resto) es calibrable.
        pl.when(pl.col("sucursal_final") == "TALCA (2)").then(P.LT_CD_RESTO)
        .when(pl.col("sucursal_final") == "DIEZ DE JULIO (2)").then(P.LT_CD_RM)
        .when(pl.col("sucursal_final") == "LINDEROS VTA MOVIL").then(P.LT_CD_RM)
        .when(pl.col("Region") == "RM").then(P.LT_CD_RM)
        .when(pl.col("Region").is_not_null()).then(P.LT_CD_RESTO)
        .otherwise(P.LT_CD_RESTO)
        .alias("lt_cd_a_sucursal_dias")
    )

    # Abastece CD.
    es_imp = pl.col("producto_master").is_in(importados)
    r = r.with_columns(es_imp.alias("es_importado"))
    # Centralizacion: el CD abastece a la sucursal en vez de que ella compre.
    #
    # Antes: clase local C o D + agregada A/B (sobre TODAS las sucursales). El
    # problema es que la agregada normal la levanta la sucursal que ya vende bien:
    # un repuesto que se mueve en Linderos sale A a nivel nacional y arrastraba a
    # centralizacion a todas las demas, aunque entre ellas casi no se vendiera.
    #
    # Desde ago-2026 (Abastecimiento): solo clase local D, y la agregada se cuenta
    # SOLO sobre las sucursales donde el producto es D. Asi lo que decide si vale
    # la pena centralizar es cuanto suman las que lo piden poco, no la que ya lo
    # vende sola. La C sale de la regla: una sucursal con rotacion C compra directo.
    #
    # OJO: `clasificacion_abc.calcular_abc` crea las filas sinteticas del CD con
    # ESTA misma condicion. Si cambia una hay que cambiar la otra, o el CD queda
    # con filas que nadie abastece.
    r = r.with_columns(
        pl.when(pl.col("sucursal_final") == P.CD_ID)
        .then(pl.when(pl.col("es_importado")).then(pl.lit("Si")).otherwise(pl.lit("No")))
        .otherwise(
            pl.when(
                pl.col("es_importado")
                | (
                    pl.col("clasificacion_abc").is_in(list(P.CENTRALIZACION_CLASES_LOCALES))
                    & pl.col(
                        "clasificacion_abc_agregada_d" if P.CENTRALIZACION_AGREGADA_SOLO_D
                        else "clasificacion_abc_agregada"
                    ).is_in(["A", "B"])
                )
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
