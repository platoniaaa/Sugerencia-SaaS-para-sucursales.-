"""Tests de las tablas chicas que el motor calcula en vez de leer del snapshot del BI.

Cada una replica una tabla calculada del modelo. Los casos cubren las reglas que NO
son obvias, que son donde se rompe la paridad si alguien las "mejora" sin mirar el DAX.
"""
from datetime import date

import polars as pl

from src.motor import dimensiones as dim


def test_dim_sucursal_trae_las_regiones_que_usa_el_lead_time():
    """Region alimenta el LT del CD a la sucursal (RM = 1 dia, resto = 2)."""
    d = dim.dim_sucursal()
    assert d.columns == ["SucursalID", "Nombre", "Region", "Tipo", "EsOperativa", "CodigoLocal"]
    reg = dict(zip(d["SucursalID"], d["Region"]))
    assert reg["LINDEROS"] == "RM"
    assert reg["CHILLAN VIEJO"] == "Nuble"
    assert reg["CD REPUESTOS"] == "RM"
    # Las bodegas virtuales no son sucursales operativas.
    oper = dict(zip(d["SucursalID"], d["EsOperativa"]))
    assert oper["TRANSITO"] is False and oper["TALCA"] is True


def _ventas(filas):
    return pl.DataFrame(
        {"Producto": [f[0] for f in filas], "Descripcion Producto": [f[1] for f in filas],
         "Fecha": [f[2] for f in filas], "Cantidad": [f[3] for f in filas]},
        schema={"Producto": pl.Utf8, "Descripcion Producto": pl.Utf8,
                "Fecha": pl.Date, "Cantidad": pl.Int64},
    )


_STOCK_VACIO = pl.DataFrame(schema={"Producto": pl.Utf8, "Familia": pl.Utf8})


def test_filtro1_sale_del_prefijo_del_codigo():
    """El rubro es el prefijo numerico ("70 2723982" -> 70 -> CHEVROLET)."""
    v = _ventas([
        ("70 123", "ACEITE", date(2026, 3, 1), 1),
        ("19 ABC", "FILTRO", date(2026, 3, 1), 1),
        ("21 XYZ", "LUBRI", date(2026, 3, 1), 1),
        ("SINPREFIJO", "OTRO", date(2026, 3, 1), 1),
    ])
    maestro = pl.DataFrame({"Producto": ["70 123"], "Categoria": ["MECANICA"]})
    d = dim.calcular_dim_producto(v, maestro, _STOCK_VACIO)
    f = dict(zip(d["Producto"], d["FILTRO1_Final"]))
    assert f["70 123"] == "CHEVROLET"
    assert f["19 ABC"] == "FORD"
    assert f["21 XYZ"] == "LUBRICANTES"
    assert f["SINPREFIJO"] is None  # sin rubro y sin ser de Frontera


def test_filtro1_reglas_brilliance_y_frontera():
    v = _ventas([
        ("1234567-ABCD", "PIEZA", date(2026, 3, 1), 1),   # 7 digitos + guion
        ("8972529350", "PIEZA FRONTERA", date(2026, 3, 1), 1),  # sin rubro, de Frontera
    ])
    maestro = pl.DataFrame(schema={"Producto": pl.Utf8, "Categoria": pl.Utf8})
    d = dim.calcular_dim_producto(v, maestro, _STOCK_VACIO, ["8972529350"])
    f = dict(zip(d["Producto"], d["FILTRO1_Final"]))
    assert f["1234567-ABCD"] == "GILDEMEISTER LIVIANOS"
    assert f["8972529350"] == "CHEVROLET"


def test_unidad_de_medida_detecta_los_mililitros():
    """Los aceites se venden en mL y el sugerido no debe tratarlos como unidades."""
    v = _ventas([
        ("A", "ACEITE 5W30 (ML)", date(2026, 3, 1), 1),
        ("B", "ACEITE (500ML)", date(2026, 3, 1), 1),
        ("C-TML", "ACEITE SUELTO", date(2026, 3, 1), 1),
        ("D", "REFRIGERANTE (LT)", date(2026, 3, 1), 1),
        ("E", "GRASA (KG)", date(2026, 3, 1), 1),
        ("F", "PASTILLA FRENO", date(2026, 3, 1), 1),
    ])
    maestro = pl.DataFrame(schema={"Producto": pl.Utf8, "Categoria": pl.Utf8})
    d = dim.calcular_dim_producto(v, maestro, _STOCK_VACIO)
    u = dict(zip(d["Producto"], d["UnidadMedida"]))
    assert u["A"] == "ML" and u["B"] == "ML" and u["C-TML"] == "ML"
    assert u["D"] == "LITRO" and u["E"] == "KG" and u["F"] == "UNIDAD"


def test_categoria_viene_del_listado_maestro():
    """De aqui salen COLISION y CAMPANAS, que quedan fuera del sugerido."""
    v = _ventas([("P1", "X", date(2026, 3, 1), 1), ("P2", "Y", date(2026, 3, 1), 1)])
    maestro = pl.DataFrame({"Producto": ["P1"], "Categoria": ["COLISION"]})
    d = dim.calcular_dim_producto(v, maestro, _STOCK_VACIO)
    c = dict(zip(d["Producto"], d["Categoria"]))
    assert c["P1"] == "COLISION" and c["P2"] is None


def test_mapeo_descarta_el_master_que_tambien_es_reemplazo():
    """B es master de C, pero tambien figura como reemplazo de A: su grupo es ambiguo.

    El DAX saca de la lista de masters solo a B (`Conflictos`), no a A. B sigue
    existiendo como MIEMBRO del grupo de A; el que desaparece es C, que dependia
    del grupo descartado."""
    mix = pl.DataFrame({
        "Producto": ["A", "B", "SOLO"],
        "Reem1": ["B", "C", "R1"],
        "Reem2": [None, None, None],
        "Reem3": [None, None, None],
    })
    v = _ventas([("SOLO", "X", date(2026, 3, 1), 5), ("R1", "X", date(2026, 3, 1), 1)])
    m = dim.calcular_mapeo_master(mix, v, date(2026, 7, 1))
    assert set(m["Producto"]) == {"A", "B", "SOLO", "R1"}
    assert "C" not in set(m["Producto"])


def test_mapeo_descarta_los_masters_que_comparten_reemplazo():
    """Un producto no puede pertenecer a dos grupos."""
    mix = pl.DataFrame({
        "Producto": ["A", "B"], "Reem1": ["X", "X"],
        "Reem2": [None, None], "Reem3": [None, None],
    })
    v = _ventas([("A", "d", date(2026, 3, 1), 1)])
    assert dim.calcular_mapeo_master(mix, v, date(2026, 7, 1)).height == 0


def test_mapeo_elige_como_master_al_que_mas_vendio_en_6_meses():
    """El master NO es el del mix: es el miembro con mas venta en la ventana."""
    mix = pl.DataFrame({
        "Producto": ["A"], "Reem1": ["B"], "Reem2": [None], "Reem3": [None],
    })
    v = _ventas([
        ("A", "d", date(2026, 3, 1), 1),
        ("B", "d", date(2026, 3, 1), 99),
        # Fuera de la ventana de 6 meses: no cuenta.
        ("A", "d", date(2025, 1, 1), 500),
    ])
    m = dim.calcular_mapeo_master(mix, v, date(2026, 7, 1))
    assert set(m["Producto_Master"]) == {"B"}


def test_importados_son_los_del_seguimiento_importado():
    seg = pl.DataFrame({"Producto": ["P1", "P1", "P2", None]})
    assert dim.calcular_importados(seg)["Producto"].to_list() == ["P1", "P2"]
