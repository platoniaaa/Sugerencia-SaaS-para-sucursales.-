"""A quien se le compra cada producto, sin mirar la sucursal.

Es el escalon global de la jerarquia que ya usaba el motor para el lead time. Se
saco aparte porque la plataforma lo necesita para las filas que el motor no
evalua: un repuesto que entra por minimo InStock salia sin proveedor aunque
tuviera 90 ordenes de compra a FORD (caso real, 10-08-2026: 14 de los 52
productos sin proveedor tenian OC conocidas).
"""
from datetime import date

import polars as pl

from src.motor.lead_time import proveedor_por_producto

OC = date(2026, 1, 1)


def _seg(filas):
    return pl.DataFrame(
        [
            {"Producto": p, "SucursalID": s, "RazonSocial": r, "FechaOC": OC,
             "NOC": 1, "Origen": o, "Motivo": m}
            for p, s, r, o, m in filas
        ],
        schema={"Producto": pl.Utf8, "SucursalID": pl.Utf8, "RazonSocial": pl.Utf8,
                "FechaOC": pl.Date, "NOC": pl.Int64, "Origen": pl.Utf8, "Motivo": pl.Utf8},
    )


def _dict(df):
    return {r["Producto"]: r["proveedor"] for r in df.to_dicts()}


def test_devuelve_el_proveedor_de_la_oc():
    df = _seg([("13 ABC", "LINDEROS", "FORD MOTOR", "Curifor Nacional", "reposicion")])
    assert _dict(proveedor_por_producto(df)) == {"13 ABC": "FORD MOTOR"}


def test_junta_todas_las_sucursales():
    """Lo importante del cambio: no importa en que sucursal se compro."""
    df = _seg([
        ("13 ABC", "TALCA", "FORD MOTOR", "Curifor Nacional", "reposicion"),
        ("13 ABC", "CURICO", "FORD MOTOR", "Curifor Nacional", "reposicion"),
    ])
    r = proveedor_por_producto(df)
    assert r.height == 1
    assert _dict(r) == {"13 ABC": "FORD MOTOR"}


def test_manda_la_compra_de_reposicion():
    """Una OC de garantia dice a quien se le compro esa vez, no a quien se repone."""
    df = _seg([
        ("13 ABC", "TALCA", "AAA REPUESTOS", "Curifor Nacional", "garantia"),
        ("13 ABC", "TALCA", "FORD MOTOR", "Curifor Nacional", "reposicion"),
    ])
    # Sin el filtro de motivo ganaria "AAA REPUESTOS" por orden alfabetico.
    assert _dict(proveedor_por_producto(df)) == {"13 ABC": "FORD MOTOR"}


def test_si_no_hay_reposicion_sirve_cualquier_oc():
    """Mejor un proveedor deducido de una garantia que dejar la celda vacia."""
    df = _seg([("13 ABC", "TALCA", "AAA REPUESTOS", "Curifor Nacional", "garantia")])
    assert _dict(proveedor_por_producto(df)) == {"13 ABC": "AAA REPUESTOS"}


def test_el_importado_no_se_filtra_por_motivo():
    """El importado no informa motivo; filtrarlo lo dejaria siempre fuera."""
    df = _seg([("13 ABC", "CD REPUESTOS", "FORD BRASIL", "Curifor Importado", None)])
    assert _dict(proveedor_por_producto(df)) == {"13 ABC": "FORD BRASIL"}


def test_desempata_case_insensitive_como_el_dax():
    """MIN de DAX ignora mayusculas; el de polars ordena por bytes y pondria
    "Zeta" antes que "alfa"."""
    df = _seg([
        ("13 ABC", "TALCA", "alfa repuestos", "Curifor Nacional", "reposicion"),
        ("13 ABC", "TALCA", "Zeta repuestos", "Curifor Nacional", "reposicion"),
    ])
    assert _dict(proveedor_por_producto(df)) == {"13 ABC": "alfa repuestos"}


def test_las_oc_sin_razon_social_no_inventan_proveedor():
    df = _seg([("13 ABC", "TALCA", None, "Curifor Nacional", "reposicion")])
    assert proveedor_por_producto(df).height == 0


def test_un_seguimiento_vacio_no_revienta():
    """Si falta el Excel del seguimiento, el motor tiene que seguir corriendo."""
    r = proveedor_por_producto(_seg([]))
    assert r.height == 0
    assert r.columns == ["Producto", "proveedor"]


def test_coincide_con_lo_que_el_motor_ya_ponia_en_el_sugerido():
    """La regla es la MISMA que la del sugerido: si se separan, la plataforma
    mostraria un proveedor y el sugerido otro para el mismo repuesto."""
    from src.motor.lead_time import _proveedor_lt

    df = _seg([
        ("13 ABC", "TALCA", "FORD MOTOR", "Curifor Nacional", "reposicion"),
        ("13 XYZ", "TALCA", "AAA REPUESTOS", "Curifor Nacional", "garantia"),
    ])
    # Una sucursal que NO compro ninguno de los dos: cae al escalon global, que
    # es exactamente lo que calcula `proveedor_por_producto`.
    abc = pl.DataFrame({"producto_master": ["13 ABC", "13 XYZ"],
                        "sucursal_final": ["CHILLAN", "CHILLAN"]})
    del_sugerido = {r["producto_master"]: r["proveedor_lt"]
                    for r in _proveedor_lt(abc, df).to_dicts()}
    assert del_sugerido == _dict(proveedor_por_producto(df))
