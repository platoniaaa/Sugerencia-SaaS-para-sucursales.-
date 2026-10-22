"""El costo de TODOS los productos de Curifor llega a la lista de precios.

Para lo que evalua el sugerido, el costo viaja en `dim_producto`. Para el resto
-la mitad de la lista- la unica via es este paso, y estuvo muerta hasta el
07-10-2026: 305 productos con el costo de la carga del 04-09-2026.
"""
import csv

import polars as pl
import pytest

from src.jobs import correr_motor_real as job


@pytest.fixture
def salida(tmp_path, monkeypatch):
    ruta = tmp_path / "costos.csv"
    monkeypatch.setattr(job, "SALIDA_COSTOS", ruta)
    return ruta


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return {r["producto"]: float(r["costo"]) for r in csv.DictReader(f)}


def _costo(filas):
    """La fuente `costo` tal como la arma `fuentes_reales`: texto, como viene."""
    return pl.DataFrame(filas, schema=["Producto", "Costo"], orient="row")


def test_el_costo_con_coma_decimal_se_publica(salida):
    """El Excel trae "95233,75000000": con un cast a secas quedaba vacio."""
    job._guardar_costos_precios({"costo": _costo([("13 A", "95233,75000000"), ("13 B", "1.234,5")])})

    assert _leer(salida) == {"13 A": 95233.75, "13 B": 1234.5}


def test_varios_lotes_manda_el_mayor_y_el_codigo_sin_espacios(salida):
    """82 codigos del Excel traen un espacio al final; la lista los tiene sin el."""
    job._guardar_costos_precios({"costo": _costo([
        ("15 MXD1454M ", "1000"), ("15 MXD1454M", "1200"), ("15 MXD1454M", "900")])})

    assert _leer(salida) == {"15 MXD1454M": 1200.0}


def test_un_costo_vacio_o_cero_no_viaja(salida):
    """Un cero no es un costo: la plataforma conserva el ultimo conocido."""
    job._guardar_costos_precios({"costo": _costo([("13 A", "0"), ("13 B", ""), ("13 C", "500")])})

    assert _leer(salida) == {"13 C": 500.0}


def test_el_costo_de_frontera_no_entra(salida):
    """La lista es de Curifor: el costo de otra empresa no le sirve."""
    frontera = pl.DataFrame({"Producto": ["13 A"], "Bodega": ["X"], "SucursalID": ["E07"],
                             "Stock": [1.0], "Costo": ["99999"]})
    job._guardar_costos_precios({"costo": _costo([("13 A", "1000")]),
                                 "stock_bodegas_frontera": frontera})

    assert _leer(salida) == {"13 A": 1000.0}


def test_sin_la_fuente_no_escribe_nada(salida):
    assert job._guardar_costos_precios({}) is None
    assert not salida.exists()


def test_se_publica_por_lotes(salida, monkeypatch):
    job._guardar_costos_precios({"costo": _costo([(f"13 P{i:05d}", "100") for i in range(12000)])})
    lotes = []

    def falso(paso, ruta, filas):
        lotes.append((ruta, len(filas)))
        return {"actualizados": len(filas), "ignorados": 0}

    monkeypatch.setattr(job, "_publicar_json", falso)
    r = job.publicar_costos_precios()

    assert [n for _, n in lotes] == [5000, 5000, 2000]
    assert {ruta for ruta, _ in lotes} == {"/api/admin/precios/costos"}
    assert r == {"actualizados": 12000, "ignorados": 0}


def test_un_lote_caido_hace_fallar_el_paso(salida, monkeypatch):
    job._guardar_costos_precios({"costo": _costo([("13 A", "100")])})
    monkeypatch.setattr(job, "_publicar_json", lambda *a: None)

    assert job.publicar_costos_precios() is None
