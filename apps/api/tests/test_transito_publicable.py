"""El transito que se publica a la plataforma es el MISMO que usa el sugerido.

Si aca se reimplementara el filtro de "OC vigente", la plataforma mostraria un
numero y el sugerido otro, y no habria forma de saber cual creer. Por eso el job
llama a `_stock_transito` y lo unico que agrega es la fecha de la OC mas antigua.
"""
from datetime import date

import polars as pl

from src.motor.sugerido import _stock_transito


def _seguimiento() -> pl.DataFrame:
    """Cuatro OC: una vigente, una vencida por ventana, una de otra sucursal y
    una cerrada."""
    return pl.DataFrame({
        "Producto": ["A", "A", "B", "C"],
        "SucursalID": ["LINDEROS", "LINDEROS", "CURICO", "LINDEROS"],
        "Cantidad": [3.0, 2.0, 4.0, 9.0],
        "EstadoOC": ["Pendiente", "Pendiente", "Pendiente", "Cerrada"],
        "EstadoDoc": ["", "", "", ""],
        "Origen": ["Curifor Nacional"] * 4,
        "Motivo": ["reposicion"] * 4,
        "FechaOC": [
            date(2026, 7, 1),   # 35 dias: fuera de la ventana nacional
            date(2026, 7, 20),  # 16 dias: vigente
            date(2026, 7, 5),   # otra sucursal
            date(2026, 7, 1),   # cerrada
        ],
    }).with_columns(pl.lit(None, dtype=pl.Date).alias("FechaDoc"))


HOY = date(2026, 8, 5)


def test_con_fecha_no_cambia_lo_que_ya_calculaba_el_sugerido():
    """La bandera es aditiva: si tocara el numero, la plataforma y el sugerido
    dejarian de coincidir sin que nadie lo note."""
    sin = _stock_transito(_seguimiento(), HOY)
    con = _stock_transito(_seguimiento(), HOY, con_fecha=True)

    assert sin.columns == ["producto_master", "sucursal_final", "stock_transito"]
    assert con.columns == [*sin.columns, "pedido_desde"]
    assert sorted(sin.rows()) == sorted([r[:3] for r in con.rows()])


def test_solo_cuenta_las_oc_vigentes():
    """La OC de hace 35 dias no viene en camino: quedo colgada."""
    filas = {(p, s): c for p, s, c in _stock_transito(_seguimiento(), HOY).rows()}
    assert filas == {("A", "LINDEROS"): 2.0}


def test_la_fecha_es_la_de_la_oc_mas_antigua_VIGENTE():
    """"Vienen 5" no dice lo mismo que "vienen 5 pedidas hace meses". La fecha
    sale de las filas que sobrevivieron el filtro, no de todas."""
    con = _stock_transito(_seguimiento(), HOY, con_fecha=True)
    fecha = {(p, s): f for p, s, _c, f in con.rows()}
    assert fecha[("A", "LINDEROS")] == date(2026, 7, 20)


def test_una_oc_de_frontera_usa_la_fecha_del_documento():
    """En Frontera la OC no trae FechaOC: la vigencia y la fecha salen de FechaDoc."""
    seg = pl.DataFrame({
        "Producto": ["F"],
        "SucursalID": ["LINDEROS"],
        "Cantidad": [5.0],
        "EstadoOC": [""],
        "EstadoDoc": ["Pendiente"],
        "Origen": ["Frontera Nacional"],
        "Motivo": ["reposicion"],
        "FechaDoc": [date(2026, 7, 25)],
    }).with_columns(pl.lit(None, dtype=pl.Date).alias("FechaOC"))

    con = _stock_transito(seg, HOY, con_fecha=True)
    assert con.rows() == [("F", "LINDEROS", 5.0, date(2026, 7, 25))]
