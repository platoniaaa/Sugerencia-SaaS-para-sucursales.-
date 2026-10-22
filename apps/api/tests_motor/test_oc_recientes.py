"""El motor manda las OC recientes para cerrar lo de una sola vez ya comprado.

Nadie aprieta "Marcar como pedido" en la plataforma: sin las OC, una sugerencia de
una sola vez seguia sumando despues de comprada y la descarga siguiente del
sugerido la volvia a pedir.
"""
import csv
import inspect
from datetime import date, timedelta

import httpx
import polars as pl

from src.jobs import correr_motor_real as job

HOY = date(2026, 10, 8)


def _seg(filas):
    columnas = ("Producto", "SucursalID", "NOC", "FechaOC", "Cantidad", "Motivo", "EstadoOC")
    return pl.DataFrame(
        [dict(zip(columnas, f)) | {"Origen": "Curifor Nacional"} for f in filas],
        schema={"Producto": pl.Utf8, "SucursalID": pl.Utf8, "NOC": pl.Utf8,
                "FechaOC": pl.Date, "Cantidad": pl.Int64, "Motivo": pl.Utf8,
                "EstadoOC": pl.Utf8, "Origen": pl.Utf8},
    )


def _filas(monkeypatch, tmp_path, seg):
    monkeypatch.setattr(job, "SALIDA_OC", tmp_path / "oc.csv")
    ruta = job._guardar_oc_recientes({"seguimiento_transito": seg}, hoy=HOY)
    if ruta is None:
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_una_fila_por_oc_con_sus_lineas_sumadas(monkeypatch, tmp_path):
    ayer = HOY - timedelta(days=1)
    filas = _filas(monkeypatch, tmp_path, _seg([
        (" 25 DG9Z8100A ", "LINDEROS", "5758", ayer, 3, "COMPRA CALZADA", "Pendiente"),
        ("25 DG9Z8100A", "LINDEROS", "5758", ayer, 4, "COMPRA CALZADA", "Pendiente"),
    ]))
    assert [(f["producto"], f["sucursal_id"], f["n_oc"], f["fecha_oc"], float(f["cantidad"]))
            for f in filas] == [("25 DG9Z8100A", "LINDEROS", "5758", ayer.isoformat(), 7.0)]


def test_van_todos_los_motivos_y_las_ya_recibidas(monkeypatch, tmp_path):
    """Los pedidos especiales se compran como compra calzada, que el transito no cuenta."""
    ayer = HOY - timedelta(days=1)
    filas = _filas(monkeypatch, tmp_path, _seg([
        ("A", "LINDEROS", "1", ayer, 1, "COMPRA CALZADA", "Cerrado por sistema"),
        ("B", "LINDEROS", "2", ayer, 1, "REPOSICION", "Pendiente"),
        ("C", "LINDEROS", "3", ayer, 1, "GARANTIA", "Abierto con referencia"),
    ]))
    assert sorted(f["producto"] for f in filas) == ["A", "B", "C"]


def test_quedan_fuera_las_viejas_las_anuladas_y_las_sin_sucursal(monkeypatch, tmp_path):
    ayer = HOY - timedelta(days=1)
    vieja = HOY - timedelta(days=job.DIAS_OC_RECIENTES + 1)
    filas = _filas(monkeypatch, tmp_path, _seg([
        ("VIEJA", "LINDEROS", "1", vieja, 1, "REPOSICION", "Pendiente"),
        ("ANULADA", "LINDEROS", "2", ayer, 1, "REPOSICION", "Anulada"),
        ("SIN SUCURSAL", "DESCONOCIDO", "3", ayer, 1, "IMPORTACION VOR", ""),
        ("SIN CANTIDAD", "LINDEROS", "4", ayer, 0, "REPOSICION", "Pendiente"),
        ("SIRVE", "LINDEROS", "5", ayer, 2, "REPOSICION", "Pendiente"),
    ]))
    assert [f["producto"] for f in filas] == ["SIRVE"]


class _Resp:
    def __init__(self, codigo, datos):
        self.status_code, self._datos = codigo, datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._datos


def _cliente(codigo, datos, llamadas):
    class _C:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            llamadas.append((url, json))
            if url.endswith("/api/auth/login"):
                return _Resp(200, {"token": "t"})
            return _Resp(codigo, datos)
    return _C


def _preparar(monkeypatch, tmp_path, codigo, datos):
    llamadas = []
    job.olvidar_token()
    monkeypatch.setattr(job, "SALIDA_OC", tmp_path / "oc.csv")
    job._guardar_oc_recientes({"seguimiento_transito": _seg([
        ("25 DG9Z8100A", "LINDEROS", "5758", HOY, 7, "COMPRA CALZADA", "Pendiente"),
    ])}, hoy=HOY)
    monkeypatch.setattr(job, "_credenciales", lambda: ("http://api", "a@b.cl", "x"))
    monkeypatch.setattr(httpx, "Client", _cliente(codigo, datos, llamadas))
    return llamadas


def test_manda_las_oc_a_la_plataforma(monkeypatch, tmp_path):
    llamadas = _preparar(monkeypatch, tmp_path, 200, {"sugerencias_cerradas": 1})
    assert job.publicar_oc_recientes() == {"sugerencias_cerradas": 1}
    url, cuerpo = llamadas[-1]
    assert url == "http://api/api/admin/oc-recientes"
    assert cuerpo["filas"] == [{
        "producto": "25 DG9Z8100A", "sucursal_id": "LINDEROS", "n_oc": "5758",
        "fecha_oc": HOY.isoformat(), "cantidad": 7.0, "motivo": "COMPRA CALZADA",
        "origen": "Curifor Nacional",
    }]
    job.olvidar_token()


def test_una_plataforma_sin_el_endpoint_no_es_un_fallo(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path, 404, {})
    marca = len(job._FALLOS)
    assert job.publicar_oc_recientes() is None
    assert len(job._FALLOS) == marca
    job.olvidar_token()


def test_van_despues_del_transito_y_antes_de_las_reglas():
    # La secuencia de la corrida vive en `_correr`; `_run` solo la envuelve.
    fuente = inspect.getsource(job._correr)
    i = fuente.index("publicar_oc_recientes")
    assert fuente.index("publicar_transito") < i < fuente.index("publicar_reglas_manuales")
