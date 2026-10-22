"""El costo del sugerido cae al export del ERP cuando el stock no lo trae.

El costo salia de un solo lugar: el Excel de Stock por bodegas, que SOLO lista lo
que hoy tiene stock. Un producto agotado no aparece ahi y salia sin costo -y
justamente los que hay que comprar son los que no tienen stock-.

Medido sobre la corrida del 05-10-2026: 5.568 productos sin costo, y de los 76
que el sugerido mandaba a comprar, 69 tenian su costo en el export del ERP sin
que nadie lo mirara. Iban a la orden de compra con la columna en blanco, con
costos de hasta $1,19 millones.

El del stock sigue mandando cuando existe: es el que se mueve con cada recepcion.
El del ERP es el respaldo.
"""
import polars as pl

from src.motor import pipeline


def _fuentes(costo_stock: list[tuple[str, str]], costo_erp: list[tuple[str, float]] | None):
    """Las dos fuentes de costo, en el formato que arma `fuentes_reales`."""
    fuentes = {
        "costo": pl.DataFrame(costo_stock, schema=["Producto", "Costo"], orient="row"),
    }
    if costo_erp is not None:
        fuentes["costo_erp"] = pl.DataFrame(
            costo_erp, schema=["Producto", "Costo"], orient="row"
        )
    return fuentes


def _costos(fuentes, productos):
    """Lo que el pipeline resuelve como costo_unitario para esos productos."""
    base = pl.DataFrame({"producto_master": productos})
    return dict(
        pipeline.costos_unitarios(base, fuentes)
        .select(["producto_master", "costo_unitario"])
        .rows()
    )


def test_el_costo_del_stock_sigue_mandando():
    """Es el que se mueve con cada recepcion; el del ERP es la foto semanal."""
    fuentes = _fuentes(
        costo_stock=[("13 AAA", "1000")],
        costo_erp=[("13 AAA", 999.0)],
    )
    assert _costos(fuentes, ["13 AAA"])["13 AAA"] == 1000.0


def test_sin_stock_toma_el_costo_del_erp():
    """El caso de la queja: producto agotado, sin fila en el Excel de stock."""
    fuentes = _fuentes(
        costo_stock=[("13 OTRO", "5000")],
        costo_erp=[("13 BF5X4635AMERIT", 45330.507852)],
    )
    assert _costos(fuentes, ["13 BF5X4635AMERIT"])["13 BF5X4635AMERIT"] == 45330.507852


def test_sin_costo_en_ninguna_parte_queda_vacio():
    """No se inventa un cero: un costo 0 ensucia el valorizado y parece dato."""
    fuentes = _fuentes(costo_stock=[("13 OTRO", "5000")], costo_erp=[("13 OTRO", 5000.0)])
    assert _costos(fuentes, ["13 SIN DATO"])["13 SIN DATO"] is None


def test_un_costo_en_cero_o_negativo_no_sirve_como_respaldo():
    """El ERP trae ceros en los codigos que nunca se compraron. Un 0 no es un
    costo: dejar la celda vacia dice la verdad, un 0 miente."""
    fuentes = _fuentes(
        costo_stock=[("13 OTRO", "5000")],
        costo_erp=[("13 CERO", 0.0), ("13 NEG", -10.0)],
    )
    resueltos = _costos(fuentes, ["13 CERO", "13 NEG"])
    assert resueltos["13 CERO"] is None
    assert resueltos["13 NEG"] is None


def test_sin_el_export_del_erp_se_comporta_como_antes():
    """La fuente es opcional: si el archivo no esta, no se cae la corrida."""
    fuentes = _fuentes(costo_stock=[("13 AAA", "1000")], costo_erp=None)
    resueltos = _costos(fuentes, ["13 AAA", "13 SIN STOCK"])
    assert resueltos["13 AAA"] == 1000.0
    assert resueltos["13 SIN STOCK"] is None


def test_entre_varias_filas_del_stock_manda_la_mas_cara():
    """Se conserva el criterio del modelo: MAX(Costo) por producto."""
    fuentes = _fuentes(
        costo_stock=[("13 AAA", "1000"), ("13 AAA", "1200"), ("13 AAA", "900")],
        costo_erp=[("13 AAA", 50.0)],
    )
    assert _costos(fuentes, ["13 AAA"])["13 AAA"] == 1200.0
