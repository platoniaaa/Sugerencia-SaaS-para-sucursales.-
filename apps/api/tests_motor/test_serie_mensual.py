"""Las 12 columnas de venta mensual y los promedios a 3, 6 y 12 meses.

Salen de la MISMA serie que la demanda -mismo grano, misma CantidadAjustada, misma
ventana- pero sin winsorizar, para que el comprador pueda sumar las doce columnas
y comprobar el promedio que tiene al lado.

Lo que estos tests cuidan es lo que no se ve al mirar una fila: que la ventana no
se corra un mes, que los meses sin venta cuenten como cero en el promedio, y que
la venta del código dado de baja llegue a la fila del vigente.
"""
from datetime import date

import polars as pl

from src.motor.demanda import calcular_serie_mensual, ultimo_mes_cerrado

# Ventana de esta fecha: 202507 (venta_mes_12) .. 202606 (venta_mes_01).
FIN = date(2026, 7, 1)
SIN_MAPEO = pl.DataFrame(schema={"Producto": pl.Utf8, "Producto_Master": pl.Utf8})


def _ventas(filas: list[tuple[str, date, float]]) -> pl.DataFrame:
    return pl.DataFrame({
        "Producto": [p for p, _, _ in filas],
        "SUCURSAL": ["TALCA"] * len(filas),
        "TipoVenta": ["VTA MESON"] * len(filas),
        "Fecha": [f for _, f, _ in filas],
        "CantidadAjustada": [c for _, _, c in filas],
        "Fuente": ["Curifor"] * len(filas),
    })


def _dim(*productos: str) -> pl.DataFrame:
    return pl.DataFrame({"Producto": list(productos),
                         "Categoria": ["MECANICA"] * len(productos)})


def _fila(df: pl.DataFrame, producto: str) -> dict:
    return df.filter(pl.col("producto_master") == producto).to_dicts()[0]


def test_el_mes_01_es_el_ultimo_mes_cerrado_y_el_mes_en_curso_no_entra():
    """El mes en curso está a medias: mostrarlo haría ver una caída que no existe.

    `_inicio_ventana` ya define la ventana terminando en el mes ANTERIOR a
    `fin_mes_cerrado`; esto lo fija para que un cambio ahí no corra las columnas
    en silencio.
    """
    v = _ventas([
        ("A", date(2026, 7, 15), 9),   # 202607: mes en curso, fuera
        ("A", date(2026, 6, 10), 4),   # 202606: el ultimo cerrado
        ("A", date(2025, 7, 3), 2),    # 202507: el mas antiguo de la ventana
        ("A", date(2025, 6, 30), 50),  # 202506: justo antes, fuera
    ])

    r = _fila(calcular_serie_mensual(v, SIN_MAPEO, _dim("A"), FIN), "A")

    assert ultimo_mes_cerrado(FIN) == "202606"
    assert r["venta_mes_01"] == 4
    assert r["venta_mes_12"] == 2
    assert sum(r[f"venta_mes_{i:02d}"] for i in range(1, 13)) == 6, "entró venta de fuera de la ventana"


def test_los_meses_sin_venta_cuentan_como_cero_en_el_promedio():
    """Es el error clásico: promediar solo los meses con movimiento.

    Un repuesto que vendió 12 unidades en dos meses y nada en los otros diez tiene
    promedio 1, no 6. Con 6 el sugerido pediría seis veces lo que corresponde.
    """
    v = _ventas([
        ("A", date(2026, 6, 10), 6),
        ("A", date(2026, 5, 10), 6),
    ])

    r = _fila(calcular_serie_mensual(v, SIN_MAPEO, _dim("A"), FIN), "A")

    assert r["prom_vta_12m"] == 1.0
    assert r["prom_vta_6m"] == 2.0
    assert r["prom_vta_3m"] == 4.0


def test_cada_promedio_mira_solo_su_ventana():
    """Si los tres promedios miraran los mismos meses, sobrarían dos columnas."""
    v = _ventas([
        ("A", date(2026, 6, 10), 3),
        ("A", date(2026, 5, 10), 3),
        ("A", date(2026, 4, 10), 3),
        ("A", date(2025, 12, 10), 30),  # fuera de 3m y de 6m, dentro de 12m
    ])

    r = _fila(calcular_serie_mensual(v, SIN_MAPEO, _dim("A"), FIN), "A")

    assert r["prom_vta_3m"] == 3.0
    assert r["prom_vta_6m"] == 1.5
    assert r["prom_vta_12m"] == 39 / 12


def test_la_venta_del_codigo_de_baja_llega_a_la_fila_del_vigente():
    """El grano es el grupo de reemplazos, igual que el stock y la demanda.

    Sin esto, un repuesto FORD que se vendía con el código viejo y hoy va con el
    vigente mostraría meses en cero justo donde el grupo sí vendió, y la columna
    contradiría a la demanda de su propia fila.
    """
    mapeo = pl.DataFrame({"Producto": ["VIEJO"], "Producto_Master": ["NUEVO"]})
    v = _ventas([
        ("VIEJO", date(2026, 5, 10), 7),
        ("NUEVO", date(2026, 6, 10), 3),
    ])

    df = calcular_serie_mensual(v, mapeo, _dim("VIEJO", "NUEVO"), FIN)

    assert df["producto_master"].to_list() == ["NUEVO"], "el código viejo quedó como fila aparte"
    r = _fila(df, "NUEVO")
    assert r["venta_mes_01"] == 3
    assert r["venta_mes_02"] == 7
