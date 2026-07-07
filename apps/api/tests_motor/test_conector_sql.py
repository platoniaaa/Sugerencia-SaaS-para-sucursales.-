"""Tests offline del conector SQL: transformaciones puras con datos sintéticos.
No tocan la base de datos (esa parte requiere credenciales + red de Curifor)."""
from datetime import date

import polars as pl

from src.motor.conectores import sql_flexline as F


def test_mapear_sucursal_id():
    assert F.mapear_sucursal_id("SUC070") == "LINDEROS"
    assert F.mapear_sucursal_id("SUC280") == "CD REPUESTOS"
    assert F.mapear_sucursal_id("SUC310") == "RANCAGUA"
    assert F.mapear_sucursal_id("XXXX") == "DESCONOCIDO"
    assert F.mapear_sucursal_id(None) == "DESCONOCIDO"


def test_cantidad_ajustada():
    df = pl.DataFrame({
        "tipoDocto": ["FACTURA", "NC CLIENTE S/T", "NC-ELECTR REPTO", "GUIA"],
        "Cantidad": [5, 3, -2, -4],
    }).with_columns(F.cantidad_ajustada_expr().alias("ca"))
    # NC restan (valor absoluto negativo); el resto suma en valor absoluto.
    assert df.get_column("ca").to_list() == [5, -3, -2, 4]


def test_normalizar_seguimiento():
    raw = pl.DataFrame({
        "Producto": ["P1", "P2"],
        "Sucursal": ["SUC070", "SUC280"],
        "RazonSocial": ["Prov A", "Prov B"],
        "FechaOC": [date(2026, 1, 1), date(2026, 2, 1)],
        "NOC": [100, 200],
        "Motivo": ["reposicion", "REPOSICION"],
        "Cantidad": [10, 20],
        "EstadoOC": ["Pendiente", "Cerrado"],
        "EstadoDoc": ["Pendiente", "Cerrado"],
        "FechaDoc": [date(2026, 1, 1), date(2026, 2, 1)],
        "FechaPE": [None, date(2026, 2, 5)],
    })
    out = F.normalizar_seguimiento(raw)
    assert out.columns == ["Producto", "SucursalID", "RazonSocial", "FechaOC", "NOC", "Origen", "Motivo"]
    assert out.get_column("SucursalID").to_list() == ["LINDEROS", "CD REPUESTOS"]
    assert out.get_column("Origen").unique().to_list() == ["Curifor Nacional"]
    # para tránsito: agrega las columnas de estado/cantidad
    tr = F.normalizar_seguimiento(raw, para_transito=True)
    assert {"Cantidad", "EstadoOC", "EstadoDoc", "FechaDoc"}.issubset(set(tr.columns))


def test_normalizar_ventas_curifor():
    raw = pl.DataFrame({
        "Producto": ["P1", "P2", "P3"],
        "SUCURSAL": ["LINDEROS", "TALCA", "CURICO"],
        "Tipo-Venta": ["VTA MESON", "VTA MOVIL", "VTA MESON"],
        "Fecha": [date(2026, 1, 1)] * 3,
        "Cantidad": [5, 3, 2],
        "tipoDocto": ["FACTURA", "NC CLIENTE S/T", "FACTURA"],
        "tipoproducto": ["REPUESTOS", "REPUESTO", "MO_ST"],  # el 3ro se filtra
    })
    out = F.normalizar_ventas_curifor(raw)
    assert out.columns == ["Producto", "SUCURSAL", "TipoVenta", "Fecha", "CantidadAjustada", "Fuente"]
    assert out.height == 2  # MO_ST descartado
    assert out.get_column("CantidadAjustada").to_list() == [5, -3]
    assert out.get_column("Fuente").unique().to_list() == ["Curifor"]


def test_conectar_sin_credenciales_falla_claro(monkeypatch):
    monkeypatch.delenv("FLEXLINE_SQL_USER", raising=False)
    monkeypatch.delenv("FLEXLINE_SQL_PASSWORD", raising=False)
    import pytest
    with pytest.raises(RuntimeError, match="credenciales"):
        F.conectar()
