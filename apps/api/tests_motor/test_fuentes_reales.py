"""Test del lector de stock (fuentes_reales.leer_stock).

Usa un xlsx sintético en Hoja1 que ejercita el mapeo Bodega -> SucursalID
(incluyendo case-insensitivity, alias que colapsan, bodega desconocida y nula).
No depende de los Excel reales de 48 MB.
"""
import polars as pl
import pytest

openpyxl = pytest.importorskip("openpyxl")

from src.motor import fuentes_reales as FR


def _xlsx(path, filas):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    ws.append(["Producto", "Descripcion", "Unidad", "Stock", "Bodega", "Costo"])
    for f in filas:
        ws.append(f)
    wb.save(path)


def test_leer_stock_mapea_sucursal(tmp_path):
    ruta = tmp_path / "stock.xlsx"
    # Producto, Descripcion, Unidad, Stock, Bodega, Costo
    _xlsx(ruta, [
        ["P1", "d", "UNIDAD", 10, "BODEGA ML", 500],          # -> CD REPUESTOS
        ["P2", "d", "UNIDAD", 5, "BODEGA DYP TALCA 2", 600],  # -> TALCA (2)
        ["P3", "d", "UNIDAD", 3, "la florida", 700],          # case-insensitive -> LA FLORIDA
        ["P4", "d", "UNIDAD", 7, "RANCAGUA 3", 800],          # alias -> RANCAGUA
        ["P5", "d", "UNIDAD", 1, "BODEGA RARA", 900],         # desconocida -> DESCONOCIDO
        ["P6", "d", "UNIDAD", 2, None, 100],                  # nula -> DESCONOCIDO
    ])
    df = FR.leer_stock(ruta)
    assert df.columns == ["Producto", "SucursalID", "Stock", "Costo"]
    m = {r["Producto"]: r["SucursalID"] for r in df.to_dicts()}
    assert m["P1"] == "CD REPUESTOS"
    assert m["P2"] == "TALCA (2)"
    assert m["P3"] == "LA FLORIDA"
    assert m["P4"] == "RANCAGUA"
    assert m["P5"] == "DESCONOCIDO"
    assert m["P6"] == "DESCONOCIDO"
    # Stock queda entero; Costo texto (el modelo lo pasa por VALUE()).
    assert df.schema["Stock"] == pl.Int64
    assert df.filter(pl.col("Producto") == "P1").select("Stock").item() == 10


def test_leer_stock_ignora_filas_sin_producto(tmp_path):
    ruta = tmp_path / "stock.xlsx"
    _xlsx(ruta, [
        ["P1", "d", "UNIDAD", 10, "LINDEROS", 500],
        [None, "d", "UNIDAD", 99, "LINDEROS", 500],  # sin producto -> se ignora
    ])
    df = FR.leer_stock(ruta)
    assert df.height == 1
    assert df.select("Producto").item() == "P1"
