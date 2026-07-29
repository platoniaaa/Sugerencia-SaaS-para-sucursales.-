"""Lectura y cruce de las listas de precios de proveedor.

El cruce es lo unico delicado: el codigo interno de Curifor trae un prefijo
numerico ("25 DG9Z8100A") y las listas usan el del fabricante en su propio
formato ("DG9Z/8100/A/"). Sin normalizar, el cruce da CERO.
"""
import polars as pl
import pytest
from openpyxl import Workbook

from src.motor.lectores_excel import (
    clave_precio,
    leer_precios_ford,
    leer_precios_gildemeister,
)


def _xlsx(ruta, cabeceras, filas):
    wb = Workbook()
    ws = wb.active
    ws.title = "Precios"
    ws.append(cabeceras)
    for f in filas:
        ws.append(f)
    wb.save(ruta)


@pytest.mark.parametrize("entrada,esperado", [
    ("25 DG9Z8100A", "DG9Z8100A"),      # codigo Curifor: se le saca el prefijo
    ("DG9Z/8100/A/", "DG9Z8100A"),      # FORD: se le sacan las barras
    ("83 51703-4A000", "517034A000"),   # Curifor con guion
    ("517034A000", "517034A000"),       # Gildemeister
    ("  ab3z/1a380/b/  ", "AB3Z1A380B"),
    (None, None),
    ("   ", None),
    ("///", None),
])
def test_clave_precio_normaliza_los_dos_lados(entrada, esperado):
    assert clave_precio(entrada) == esperado


def test_el_codigo_curifor_y_el_de_ford_caen_en_la_misma_clave():
    assert clave_precio("25 DG9Z8100A") == clave_precio("DG9Z/8100/A/")


def test_leer_precios_ford(tmp_path):
    ruta = tmp_path / "ford.xlsx"
    _xlsx(ruta,
          ["PartNumber", "Price_dealer", "Estado", "Precio_Publico",
           "Precio_Publico_ConImpuestos", "Reposicion", "Urgente_VOR",
           "Promociones", "Urgente_Recargo15", "Precio_Flota"],
          [["DG9Z/8100/A/", 1000, "Encontrado", 1500, 1785, 1000, 1000, 1000, 1150, 1200]])
    df = leer_precios_ford(ruta)
    fila = df.to_dicts()[0]
    assert fila["clave_precio"] == "DG9Z8100A"
    assert fila["precio_dealer_ford"] == 1000
    assert fila["precio_publico_ford"] == 1500
    assert fila["precio_flota_ford"] == 1200


def test_leer_precios_gildemeister(tmp_path):
    ruta = tmp_path / "gilde.xlsx"
    _xlsx(ruta, ["Marca", "Codigo", "Nombre", "Precio_Sugerido", "Precio_Dealer",
                 "Precio_Final_Dealer", "Stock"],
          [["HYUNDAI", "517034A000", "PERNO", 214, 118, 118, "Agotado"]])
    df = leer_precios_gildemeister(ruta)
    fila = df.to_dicts()[0]
    assert fila["clave_precio"] == "517034A000"
    assert fila["precio_sugerido_gilde"] == 214
    assert fila["precio_dealer_gilde"] == 118


def test_dos_codigos_que_normalizan_igual_se_quedan_con_el_mayor(tmp_path):
    """No puede fallar el join por claves duplicadas; con el mayor no se
    subestima el margen y el resultado es estable entre corridas."""
    ruta = tmp_path / "ford.xlsx"
    _xlsx(ruta, ["PartNumber", "Price_dealer", "Precio_Publico"],
          [["AB3Z/1A380/B/", 100, 500], ["AB3Z1A380B", 200, 900]])
    df = leer_precios_ford(ruta)
    assert df.height == 1
    assert df.to_dicts()[0]["precio_publico_ford"] == 900


def test_lista_sin_la_columna_de_codigo_avisa_claro(tmp_path):
    ruta = tmp_path / "ford.xlsx"
    _xlsx(ruta, ["Otra", "Precio_Publico"], [["x", 1]])
    with pytest.raises(ValueError, match="PartNumber"):
        leer_precios_ford(ruta)


def test_lista_sin_ninguna_columna_de_precio_avisa_claro(tmp_path):
    ruta = tmp_path / "ford.xlsx"
    _xlsx(ruta, ["PartNumber", "Comentario"], [["A/1/", "x"]])
    with pytest.raises(ValueError, match="columna de precio"):
        leer_precios_ford(ruta)


def test_columnas_de_precio_ausentes_no_rompen(tmp_path):
    """La lista puede venir con menos columnas; se cargan las que haya."""
    ruta = tmp_path / "ford.xlsx"
    _xlsx(ruta, ["PartNumber", "Precio_Publico"], [["DG9Z/8100/A/", 1500]])
    df = leer_precios_ford(ruta)
    assert df.columns == ["clave_precio", "precio_publico_ford"]
