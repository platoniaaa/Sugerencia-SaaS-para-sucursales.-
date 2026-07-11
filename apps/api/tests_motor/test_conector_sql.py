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


def test_sucursal_id_map_incluye_fix_08jul():
    # El mapa nacional debe usar la ortografía canónica del sugerido (fix 08-jul-2026).
    assert F.mapear_sucursal_id("SUC160") == "TALCA (2)"
    assert F.mapear_sucursal_id("SUC240") == "DIEZ DE JULIO (2)"
    assert F.mapear_sucursal_id("SUC310") == "RANCAGUA"
    # El importado conserva el SWITCH viejo (su Sucursal viene en blanco -> inocuo).
    assert F.SUCURSAL_ID_MAP_IMPORTADO["SUC160"] == "TALCA 2"
    assert F.SUCURSAL_ID_MAP_IMPORTADO["SUC240"] == "DIEZ DE JULIO"
    assert F.SUCURSAL_ID_MAP_IMPORTADO["SUC310"] == "RANCAGUA 2"


def test_ventas_frontera_query_pegado():
    # Ya no es None: es el SELECT E07 verbatim del modelo.
    q = F.VENTAS_FRONTERA_QUERY
    assert isinstance(q, str) and q
    for marca in ("@Empresa Varchar(20) = 'E07'", "FROM documento E0", "AS [SUCURSAL]",
                  "AS [Docto-Emitido]", "P.tipoproducto"):
        assert marca in q


def test_normalizar_ventas_frontera():
    raw = pl.DataFrame({
        "producto": ["P1", "P2", "P3", "P4", "P5"],
        "SUCURSAL": ["02 LINDEROS", "08 TALCA", "03 PLACILLA", "05 RANCAGUA", "07 CURICO"],
        "Tipo-Venta": ["CLIENTE", "GARANTIA", "CLIENTE", "CLIENTE", "VTA MEC"],
        "fecha": [date(2026, 1, 1)] * 5,
        "cantidad": [5, 4, 2, 7, 3],
        "Documento": ["FACTURA ST", "NOTA CREDITO ST", "FACTURA REPUESTOS (E)", "FACTURA ST", "CARGO INTERNO"],
        "Docto-Emitido": ["Emitido", "Emitido", "Emitido", "Emision Pendiente", "Emitido"],
        "tipoproducto": ["REPUESTO", "REPUESTO", "REPUESTO", "REPUESTO", "MO_ST"],
    })
    out = F.normalizar_ventas_frontera(raw)
    assert out.columns == ["Producto", "SUCURSAL", "TipoVenta", "Fecha", "CantidadAjustada", "Fuente"]
    # P3 (Documento fuera del set), P4 (no Emitido) y P5 (no REPUESTO) se descartan.
    assert out.get_column("Producto").to_list() == ["P1", "P2"]
    # SUCURSAL: "02 LINDEROS" se des-prefija; "08 TALCA" pasa igual (no está en las 5).
    assert out.get_column("SUCURSAL").to_list() == ["LINDEROS", "08 TALCA"]
    # NOTA CREDITO ST NO está en la lista de NC -> la NC de Frontera SUMA (+4).
    assert out.get_column("CantidadAjustada").to_list() == [5, 4]
    assert out.get_column("Fuente").unique().to_list() == ["Frontera"]


def test_normalizar_ventas_curifor_con_historico():
    raw = pl.DataFrame({
        "Producto": ["A1", "A2"],
        "SUCURSAL": ["LINDEROS", "TALCA"],
        "Tipo-Venta": ["VTA MESON", "VTA MESON"],
        "Fecha": [date(2026, 6, 1)] * 2,
        "Cantidad": [5, 9],
        "tipoDocto": ["FACTURA", "FACTURA"],
        "tipoproducto": ["REPUESTOS", "MO_ST"],  # A2 se filtra
    })
    historico = pl.DataFrame({
        "Producto": ["H1", "H2"],
        "SUCURSAL": ["CURICO", "PLACILLA"],
        "Tipo-Venta": ["VTA MESON", "VTA MESON"],
        "Fecha": [date(2019, 3, 1), date(2020, 4, 1)],
        "Cantidad": [4, 3],
        "tipoDocto": ["NC-ELECTR REPTO", "FACTURA"],  # H1 es NC -> resta
        "tipoproducto": ["REPUESTOS", "REPUESTOS"],
    })
    out = F.normalizar_ventas_curifor(raw, historico=historico)
    assert out.get_column("Producto").to_list() == ["A1", "H1", "H2"]  # A2 (MO_ST) fuera
    assert out.get_column("CantidadAjustada").to_list() == [5, -4, 3]
    assert out.get_column("Fuente").unique().to_list() == ["Curifor"]
    # Sin histórico sigue funcionando igual (solo la venta SQL de repuestos).
    solo = F.normalizar_ventas_curifor(raw)
    assert solo.get_column("Producto").to_list() == ["A1"]


def test_unir_ventas():
    cur = pl.DataFrame({
        "Producto": ["A1"], "SUCURSAL": ["LINDEROS"], "TipoVenta": ["VTA MESON"],
        "Fecha": [date(2026, 1, 1)], "CantidadAjustada": [5], "Fuente": ["Curifor"],
    })
    fro = pl.DataFrame({
        "Producto": ["P1"], "SUCURSAL": ["CURICO"], "TipoVenta": ["CLIENTE"],
        "Fecha": [date(2026, 1, 1)], "CantidadAjustada": [3], "Fuente": ["Frontera"],
    })
    out = F.unir_ventas(cur, fro)
    assert out.height == 2
    assert set(out.get_column("Fuente").to_list()) == {"Curifor", "Frontera"}


def test_normalizar_seguimiento_importado():
    raw = pl.DataFrame({
        "Producto": ["I1", "I2"],
        "Sucursal": ["SUC160", ""],  # el importado real trae [Sucursal] en blanco
        "RazonSocial": ["Prov A", "Prov B"],
        "FechaOC": [date(2026, 1, 1), date(2026, 2, 1)],
        "NOC": [10, 20],
        "Motivo": ["reposicion", "reposicion"],
    })
    out = F.normalizar_seguimiento_importado(raw)
    assert out.get_column("Origen").unique().to_list() == ["Curifor Importado"]
    # Usa el SWITCH del importado: SUC160 -> "TALCA 2" (no "(2)"); en blanco -> DESCONOCIDO.
    assert out.get_column("SucursalID").to_list() == ["TALCA 2", "DESCONOCIDO"]


def test_normalizar_seguimiento_frontera():
    raw = pl.DataFrame({
        "Producto": ["F1", "F2", "F3"],
        "NombreLocal": ["DIEZ DE JULIO (2)", "CURICO", "OTRO"],
        "RazonSocial": ["Prov A", "Prov B", "Prov C"],
        "FechaOC": [date(2026, 1, 1)] * 3,  # el llamador mapea 'Fecha Documento Base' -> FechaOC
    })
    out = F.normalizar_seguimiento_frontera(raw)
    assert out.columns == ["Producto", "SucursalID", "RazonSocial", "FechaOC", "NOC", "Origen", "Motivo"]
    assert out.get_column("Origen").unique().to_list() == ["Frontera Nacional"]
    assert out.get_column("SucursalID").to_list() == ["DIEZ DE JULIO (2)", "CURICO", "DESCONOCIDO"]
    # Frontera no trae Motivo ni N° OC -> nulos (como el BLANK del modelo).
    assert out.get_column("Motivo").null_count() == 3
    assert out.get_column("NOC").null_count() == 3


def test_normalizar_seguimiento_para_lead_time():
    raw = pl.DataFrame({
        "Producto": ["P1"],
        "Sucursal": ["SUC070"],
        "RazonSocial": ["Prov A"],
        "FechaOC": [date(2026, 1, 1)],
        "NOC": [100],
        "Motivo": ["reposicion"],
        "FechaPE": [date(2026, 1, 8)],
    })
    out = F.normalizar_seguimiento(raw, para_lead_time=True)
    # Esquema exacto que consume lead_time_proveedor (con FechaPE, sin Producto/NOC).
    assert out.columns == ["RazonSocial", "SucursalID", "FechaOC", "FechaPE", "Origen", "Motivo"]
    assert out.get_column("SucursalID").to_list() == ["LINDEROS"]
    assert out.get_column("FechaPE").to_list() == [date(2026, 1, 8)]


def test_unir_seguimiento():
    nac = pl.DataFrame({
        "Producto": ["N1"], "Sucursal": ["SUC070"], "RazonSocial": ["Prov"],
        "FechaOC": [date(2026, 1, 1)], "NOC": [1], "Motivo": ["reposicion"],
    })
    imp = pl.DataFrame({
        "Producto": ["I1"], "Sucursal": [""], "RazonSocial": ["Prov"],
        "FechaOC": [date(2026, 1, 1)], "NOC": [2], "Motivo": ["reposicion"],
    })
    fro = pl.DataFrame({
        "Producto": ["F1"], "NombreLocal": ["LINDEROS"], "RazonSocial": ["Prov"],
        "FechaOC": [date(2026, 1, 1)],
    })
    out = F.unir_seguimiento(
        F.normalizar_seguimiento(nac),
        F.normalizar_seguimiento_importado(imp),
        F.normalizar_seguimiento_frontera(fro),
    )
    assert out.height == 3
    assert set(out.get_column("Origen").to_list()) == {"Curifor Nacional", "Curifor Importado", "Frontera Nacional"}
    assert out.get_column("SucursalID").to_list() == ["LINDEROS", "DESCONOCIDO", "LINDEROS"]
