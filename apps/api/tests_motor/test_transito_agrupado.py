"""El transito de un grupo de reemplazos se cuenta junto, igual que el stock.

Las ordenes de compra viejas quedaron emitidas con el codigo viejo. Mientras el
master del grupo fue ese mismo codigo no se notaba, pero al pasar el master al
codigo vigente de FORD (ago-2026) el transito quedaba huerfano: 42 unidades de
25 MB3Z19N619C en camino dejaban de contarse y el modelo pedia 21 donde antes
pedia 5 — comprar de nuevo algo que ya venia en camino.
"""
from datetime import date, timedelta

import polars as pl

from src.motor.sugerido import _grupo_reemplazos, _stock_transito

HOY = date(2026, 8, 18)


def _seg(filas):
    """Seguimiento con OC vigentes (pendientes, dentro de la ventana nacional)."""
    return pl.DataFrame(
        [
            {"Producto": p, "SucursalID": s, "Cantidad": float(c),
             "EstadoOC": "Pendiente", "EstadoDoc": "",
             "Origen": "Curifor Nacional", "Motivo": "reposicion",
             "FechaOC": HOY - timedelta(days=5), "FechaDoc": None}
            for p, s, c in filas
        ],
        schema={"Producto": pl.Utf8, "SucursalID": pl.Utf8, "Cantidad": pl.Float64,
                "EstadoOC": pl.Utf8, "EstadoDoc": pl.Utf8, "Origen": pl.Utf8,
                "Motivo": pl.Utf8, "FechaOC": pl.Date, "FechaDoc": pl.Date},
    )


def _miembros(master, *hijos):
    productos = pl.DataFrame({"producto_master": [master]})
    mapeo = pl.DataFrame({
        "Producto": [master, *hijos],
        "Producto_Master": [master] * (1 + len(hijos)),
    })
    return _grupo_reemplazos(productos, mapeo)


def _dict(df):
    return {(r["producto_master"], r["sucursal_final"]): r["stock_transito"]
            for r in df.to_dicts()}


def test_el_transito_del_codigo_viejo_cuenta_para_el_grupo():
    """El caso que motivo el cambio."""
    seg = _seg([("25 VIEJO", "RANCAGUA", 13)])
    out = _stock_transito(seg, HOY, miembros=_miembros("19 VIGENTE", "25 VIEJO"))
    assert _dict(out) == {("19 VIGENTE", "RANCAGUA"): 13.0}


def test_suma_el_de_todos_los_miembros():
    seg = _seg([("25 VIEJO", "RANCAGUA", 13), ("19 VIGENTE", "RANCAGUA", 4),
                ("25 VIEJO2", "RANCAGUA", 5)])
    out = _stock_transito(seg, HOY, miembros=_miembros("19 VIGENTE", "25 VIEJO", "25 VIEJO2"))
    assert _dict(out) == {("19 VIGENTE", "RANCAGUA"): 22.0}


def test_no_mezcla_sucursales():
    """Cada sucursal recibe lo suyo: el transito es por (grupo, sucursal)."""
    seg = _seg([("25 VIEJO", "RANCAGUA", 13), ("25 VIEJO", "CURICO", 4)])
    out = _stock_transito(seg, HOY, miembros=_miembros("19 VIGENTE", "25 VIEJO"))
    assert _dict(out) == {("19 VIGENTE", "RANCAGUA"): 13.0,
                          ("19 VIGENTE", "CURICO"): 4.0}


def test_el_transito_de_un_producto_ajeno_no_entra():
    seg = _seg([("25 VIEJO", "RANCAGUA", 13), ("99 AJENO", "RANCAGUA", 99)])
    out = _stock_transito(seg, HOY, miembros=_miembros("19 VIGENTE", "25 VIEJO"))
    assert _dict(out) == {("19 VIGENTE", "RANCAGUA"): 13.0}


def test_sin_miembros_se_comporta_como_antes():
    """El job que publica el transito a la plataforma llama sin agrupar."""
    seg = _seg([("25 VIEJO", "RANCAGUA", 13)])
    out = _stock_transito(seg, HOY)
    assert _dict(out) == {("25 VIEJO", "RANCAGUA"): 13.0}


def test_las_oc_cerradas_siguen_sin_contarse():
    """Agrupar no puede colar ordenes que ya no estan vigentes."""
    seg = _seg([("25 VIEJO", "RANCAGUA", 13)]).with_columns(
        pl.lit("Cerrada").alias("EstadoOC")
    )
    out = _stock_transito(seg, HOY, miembros=_miembros("19 VIGENTE", "25 VIEJO"))
    assert out.height == 0
