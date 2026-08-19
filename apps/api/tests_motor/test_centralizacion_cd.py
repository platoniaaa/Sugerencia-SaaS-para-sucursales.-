"""Que filas deja de comprar la sucursal para que se las mande el CD.

Hasta ago-2026 la regla era "clase local C o D + clase agregada A/B", con la
agregada contando TODAS las sucursales. El problema: la agregada la levanta la
sucursal que ya vende bien. Un repuesto que se mueve en Linderos sale A a nivel
nacional y arrastraba a centralizacion a todas las demas, aunque entre ellas casi
no se vendiera.

Desde ago-2026 (Abastecimiento): solo clase local D, y la agregada se cuenta SOLO
sobre las sucursales donde el producto es D. Lo que decide si vale la pena
centralizar es cuanto suman las que lo piden poco, no la que ya lo vende sola.
"""
from datetime import date

import polars as pl

from src.motor import clasificacion_abc, parametros as P

FIN = date(2026, 7, 1)


def _ventas(filas):
    """filas: (producto, sucursal, mes_offset) -> una venta ese mes."""
    return pl.DataFrame(
        [
            {"Producto": p, "SUCURSAL": s, "TipoVenta": "NORMAL",
             "Fecha": date(2026, 7 - m, 1) if m < 7 else date(2025, 19 - m, 1),
             "CantidadAjustada": 1.0, "Fuente": "Curifor"}
            for p, s, m in filas
        ],
        schema={"Producto": pl.Utf8, "SUCURSAL": pl.Utf8, "TipoVenta": pl.Utf8,
                "Fecha": pl.Date, "CantidadAjustada": pl.Float64, "Fuente": pl.Utf8},
    )


VACIO_MAPEO = pl.DataFrame(schema={"Producto": pl.Utf8, "Producto_Master": pl.Utf8})
VACIO_DIM = pl.DataFrame(schema={"Producto": pl.Utf8, "Categoria": pl.Utf8})


def _abc(filas):
    return clasificacion_abc.calcular_abc(_ventas(filas), VACIO_MAPEO, VACIO_DIM, FIN)


def _clase(df, producto, sucursal, col="clasificacion_abc"):
    f = df.filter((pl.col("producto_master") == producto)
                  & (pl.col("sucursal_final") == sucursal))
    return f.select(col).item() if f.height else None


def test_la_agregada_d_ignora_a_la_sucursal_que_vende_bien():
    """El nucleo del cambio.

    UNO vende todos los meses en LINDEROS (clase A ahi) y una sola vez en CURICO
    (clase D). La agregada normal da A porque suma las dos. La agregada de las
    sucursales D mira solo esa unica venta de CURICO: da D.
    """
    filas = [("UNO", "LINDEROS", m) for m in range(6)] + [("UNO", "CURICO", 0)]
    abc = _abc(filas)
    assert _clase(abc, "UNO", "LINDEROS") == "A"
    assert _clase(abc, "UNO", "CURICO") == "D"
    assert _clase(abc, "UNO", "CURICO", "clasificacion_abc_agregada") == "A"
    assert _clase(abc, "UNO", "CURICO", "clasificacion_abc_agregada_d") == "D"


def test_si_las_sucursales_d_suman_entre_ellas_si_da_ab():
    """El caso que SI hay que centralizar: nadie lo vende mucho, pero entre varias
    sucursales chicas se mueve todos los meses."""
    # Cada sucursal vende en meses DISTINTOS: 2 meses cada una, 6 entre las tres.
    # Asi ninguna llega a A por su cuenta pero juntas cubren la ventana completa.
    filas = ([("TRES", "CURICO", 0), ("TRES", "CURICO", 1)]
             + [("TRES", "TALCA", 2), ("TRES", "TALCA", 3)]
             + [("TRES", "CHILLAN", 4), ("TRES", "CHILLAN", 5)])
    abc = _abc(filas)
    for s in ("CURICO", "TALCA", "CHILLAN"):
        assert _clase(abc, "TRES", s) == "D", f"{s} deberia ser D local"
    # Las tres juntas cubren los 6 meses -> A en la agregada de las D.
    assert _clase(abc, "TRES", "CURICO", "clasificacion_abc_agregada_d") == "A"


def test_la_clase_c_ya_no_entra_a_centralizacion():
    """Antes la regla incluia C; ahora una sucursal con rotacion C compra directo."""
    assert "C" not in P.CENTRALIZACION_CLASES_LOCALES
    assert P.CENTRALIZACION_CLASES_LOCALES == ("D",)


def test_la_agregada_normal_sigue_disponible():
    """No se borra: la plataforma la muestra como 'ABC Agregada' y sirve para leer
    el producto a nivel nacional, aunque ya no decida la centralizacion."""
    filas = [("UNO", "LINDEROS", m) for m in range(6)] + [("UNO", "CURICO", 0)]
    abc = _abc(filas)
    assert "clasificacion_abc_agregada" in abc.columns
    assert "clasificacion_abc_agregada_d" in abc.columns


def test_un_producto_sin_ninguna_sucursal_d_no_queda_nulo():
    """Si el producto es A en todas partes, la agregada de las D no tiene filas que
    contar. Tiene que dar D (cero meses), no null: null romperia el is_in."""
    filas = [("CUATRO", "LINDEROS", m) for m in range(6)]
    abc = _abc(filas)
    v = _clase(abc, "CUATRO", "LINDEROS", "clasificacion_abc_agregada_d")
    assert v == "D", f"esperaba D, salio {v!r}"
