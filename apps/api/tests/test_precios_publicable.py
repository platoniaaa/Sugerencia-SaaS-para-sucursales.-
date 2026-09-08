"""Lo que el motor le manda a la lista de precios: el costo y la ultima compra.

Son las dos cosas que el modulo de precios no puede sacar de otro lado: el
sugerido solo cubre los productos que evalua, y el seguimiento unido pierde de
que archivo salio cada fila (que es lo que decide Importado vs Nacional).
"""
import datetime as dt

import polars as pl
import pytest

from src.jobs import correr_motor_real as job


@pytest.fixture()
def salidas(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "SALIDA_COSTOS", tmp_path / "costos.csv")
    monkeypatch.setattr(job, "SALIDA_COMPRAS", tmp_path / "compras.csv")
    return tmp_path


def _stock(filas):
    return pl.DataFrame(
        filas, schema={"Producto": pl.Utf8, "Bodega": pl.Utf8, "Stock": pl.Int64, "Costo": pl.Utf8},
        orient="row",
    )


def test_el_costo_sale_del_excel_de_stock_de_las_dos_empresas(salidas):
    fuentes = {
        "stock_bodegas": _stock([("71 AAA1", "B1", 5, "10000"), ("13 BBB2", "B1", 2, "5000")]),
        "stock_bodegas_frontera": _stock([("70 CCC3", "F1", 1, "7000")]),
    }
    assert job._guardar_costos_precios(fuentes) == job.SALIDA_COSTOS
    d = {r["producto"]: r["costo"] for r in pl.read_csv(job.SALIDA_COSTOS).to_dicts()}
    assert d == {"71 AAA1": 10000.0, "13 BBB2": 5000.0, "70 CCC3": 7000.0}


def test_un_producto_en_varias_bodegas_queda_con_un_solo_costo(salidas):
    fuentes = {"stock_bodegas": _stock([
        ("71 AAA1", "B1", 5, "10000"), ("71 AAA1", "B2", 3, "11000"),
        ("13 SINCOSTO", "B1", 1, "0"), ("14 VACIO", "B1", 1, None),
    ])}
    job._guardar_costos_precios(fuentes)
    d = {r["producto"]: r["costo"] for r in pl.read_csv(job.SALIDA_COSTOS).to_dicts()}
    # Un costo por producto, y el que no tiene costo no se manda: un cero pisaria
    # el ultimo costo conocido y dejaria el producto sin precio.
    assert d == {"71 AAA1": 11000.0}


def test_sin_columna_costo_no_escribe_nada(salidas):
    df = pl.DataFrame({"Producto": ["71 AAA1"], "Bodega": ["B1"], "Stock": [5]})
    assert job._guardar_costos_precios({"stock_bodegas": df}) is None
    assert job._guardar_costos_precios({}) is None


def test_la_ultima_compra_separa_importado_de_nacional(salidas, monkeypatch):
    def df(prod_fechas):
        return pl.DataFrame(
            {"Producto": [p for p, _ in prod_fechas],
             "FechaPE": [f for _, f in prod_fechas]},
            schema={"Producto": pl.Utf8, "FechaPE": pl.Date},
        )

    datos = {
        "seguimiento_curifor_importado": df([
            ("71 AAA1", dt.date(2026, 6, 1)), ("71 AAA1", dt.date(2026, 3, 1)),
        ]),
        # El mismo producto tambien compro nacional, mas viejo: la plataforma
        # compara las dos fechas y se queda con la mas reciente.
        "seguimiento_curifor_nacional": df([
            ("71 AAA1", dt.date(2026, 2, 1)), ("13 BBB2", dt.date(2026, 5, 20)),
        ]),
        "seguimiento_frontera": df([("13 BBB2", dt.date(2026, 7, 3))]),
    }
    monkeypatch.setattr(job, "_buscar", lambda fuente, obligatorio=True: fuente if fuente in datos else None)
    monkeypatch.setattr(job, "_LECTORES_TEST", datos, raising=False)
    import src.motor.lectores_excel as lx
    for attr, clave in (("leer_seguimiento_importado_excel", "seguimiento_curifor_importado"),
                        ("leer_seguimiento_nacional_excel", "seguimiento_curifor_nacional"),
                        ("leer_seguimiento_frontera_excel", "seguimiento_frontera")):
        monkeypatch.setattr(lx, attr, lambda ruta, _c=clave: datos[_c])

    assert job._guardar_compras_precios() == job.SALIDA_COMPRAS
    d = {r["producto"]: r for r in pl.read_csv(job.SALIDA_COMPRAS).to_dicts()}
    assert d["71 AAA1"]["ult_recep_importado"] == "2026-06-01"
    assert d["71 AAA1"]["ult_pe_nacional"] == "2026-02-01"
    # Frontera cuenta como nacional y es mas reciente que el nacional propio.
    assert d["13 BBB2"]["ult_pe_nacional"] == "2026-07-03"
    assert d["13 BBB2"].get("ult_recep_importado") in (None, "")


def test_sin_seguimientos_no_escribe_nada(salidas, monkeypatch):
    monkeypatch.setattr(job, "_buscar", lambda fuente, obligatorio=True: None)
    assert job._guardar_compras_precios() is None


def test_publicar_no_hace_nada_si_no_hay_archivo(salidas):
    assert job.publicar_costos_precios() is None
    assert job.publicar_compras_precios() is None
