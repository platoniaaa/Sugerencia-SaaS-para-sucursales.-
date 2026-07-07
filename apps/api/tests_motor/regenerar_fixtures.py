"""Regenera los fixtures de `tests_motor/fixtures/` desde data/paridad.

Herramienta de desarrollo (NO se corre en CI). Se ejecuta a mano cuando cambian
los datos del modelo o se quiere ampliar la cobertura:

    cd apps/api && python -m tests_motor.regenerar_fixtures

Requiere data/paridad/ poblado (extraído del Power BI, gitignored). Selecciona
110 productos master que cubren todas las ramas del motor y filtra todos los
insumos + goldens a ese grupo (expandiendo reemplazos). Como cada cálculo del
motor es por producto, el subconjunto conserva la paridad exacta.
"""
from pathlib import Path

import polars as pl

D = Path("data/paridad")
OUT = Path(__file__).parent / "fixtures"
S = {"Producto": pl.Utf8, "SucursalID": pl.Utf8}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    g_abc = pl.read_csv(D / "golden_abc.csv", schema_overrides=S)
    g_sug = pl.read_csv(D / "golden_sugerido.csv", schema_overrides=S)
    g_tr = pl.read_csv(D / "golden_traslados.csv", schema_overrides=S)
    g_lt = pl.read_csv(D / "golden_lt_ss.csv", schema_overrides=S)
    g_dem = pl.read_csv(D / "golden_demanda.csv", schema_overrides=S)
    mapeo = pl.read_csv(D / "mapeo_master.csv")
    ventas = pl.read_csv(D / "ventas_12m.csv", schema_overrides=S, try_parse_dates=True)
    importados = pl.read_csv(D / "importados.csv", schema_overrides=S)

    sel: set[str] = set()

    def añadir(serie, n):
        sel.update([p for p in serie.unique().sort().to_list() if p is not None][:n])

    n = lambda c: pl.col(c).cast(pl.Float64, strict=False)
    for clase in ["A", "B", "C", "D"]:
        añadir(g_abc.filter(pl.col("ABC") == clase).get_column("Producto"), 8)
        añadir(g_abc.filter(pl.col("ABCAgg") == clase).get_column("Producto"), 5)
    añadir(g_tr.filter((pl.col("SucursalID") == "CD REPUESTOS") & pl.col("StockCD").is_not_null()).get_column("Producto"), 12)
    añadir(g_abc.filter(pl.col("SucursalID") == "CD REPUESTOS").get_column("Producto"), 12)
    añadir(g_tr.filter(n("Traslado") > 0).get_column("Producto"), 15)
    añadir(g_tr.filter(pl.col("ComprarEnCD") == "Si").get_column("Producto"), 8)
    añadir(g_sug.filter(n("Sugerido") > 0).get_column("Producto"), 15)
    añadir(g_sug.filter(n("StockTransito") > 0).get_column("Producto"), 8)
    añadir(importados.get_column("Producto"), 10)
    añadir(ventas.filter(pl.col("Fuente") == "Frontera").get_column("Producto"), 10)
    añadir(g_lt.filter(pl.col("LTOrigen") == "Por sucursal").get_column("Producto"), 6)
    añadir(g_lt.filter(pl.col("LTOrigen") == "Fallback 8 dias").get_column("Producto"), 6)
    añadir(mapeo.group_by("Producto_Master").len().filter(pl.col("len") > 1).get_column("Producto_Master"), 10)
    sel.update(p for p in [
        "17 BK2Z19N619B", "61 BG1X9601BAORIG", "17 MK3Z2001B", "61 BG1X9E673BAORIG",
        "2723982", "2722295", "20 BXO5W30GA", "21 MOBIL10W40100ML",
    ] if p in set(g_abc.get_column("Producto").to_list()))

    masters = sorted(sel)
    raw_group = list(set(masters) | set(
        mapeo.filter(pl.col("Producto_Master").is_in(masters)).get_column("Producto").to_list()
    ))
    fp = lambda df, col="Producto": df.filter(pl.col(col).is_in(raw_group))
    fm = lambda df: df.filter(pl.col("Producto").is_in(masters))

    fp(ventas).write_csv(OUT / "ventas_12m.csv")
    fp(mapeo).write_csv(OUT / "mapeo_master.csv")
    fp(pl.read_csv(D / "dim_producto.csv", schema_overrides=S)).write_csv(OUT / "dim_producto.csv")
    fp(pl.read_csv(D / "seguimiento.csv", schema_overrides=S, try_parse_dates=True)).write_csv(OUT / "seguimiento.csv")
    fp(pl.read_csv(D / "seguimiento_transito.csv", schema_overrides=S, try_parse_dates=True)).write_csv(OUT / "seguimiento_transito.csv")
    fp(pl.read_csv(D / "stock_bodegas.csv", schema_overrides=S)).write_csv(OUT / "stock_bodegas.csv")
    fp(pl.read_csv(D / "stock_frontera.csv", schema_overrides=S)).write_csv(OUT / "stock_frontera.csv")
    fp(importados).write_csv(OUT / "importados.csv")
    pl.read_csv(D / "lt_proveedor.csv").write_csv(OUT / "lt_proveedor.csv")
    pl.read_csv(D / "lt_proveedor_sucursal.csv", schema_overrides=S).write_csv(OUT / "lt_proveedor_sucursal.csv")
    pl.read_csv(D / "dim_sucursal.csv", schema_overrides=S).write_csv(OUT / "dim_sucursal.csv")
    for nombre, g in [("golden_abc", g_abc), ("golden_demanda", g_dem), ("golden_lt_ss", g_lt),
                      ("golden_sugerido", g_sug), ("golden_traslados", g_tr)]:
        fm(g).write_csv(OUT / f"{nombre}.csv")

    print(f"OK: {len(masters)} masters, {len(raw_group)} productos raw, "
          f"{fm(g_sug).height} filas golden_sugerido -> {OUT}")


if __name__ == "__main__":
    main()
