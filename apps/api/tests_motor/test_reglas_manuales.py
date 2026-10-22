"""El motor aplica cada dia las reglas de sugerencias manuales.

El workflow de GitHub que debia hacerlo fallaba con 403 desde hace mas de 40
corridas: "nunca menos de N unidades" se calculaba el dia en que se creaba la
regla y nunca mas. Ahora lo pide el motor, con los datos del dia ya publicados.
"""
import inspect

import httpx

from src.jobs import correr_motor_real as job


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
            llamadas.append(url)
            if url.endswith("/api/auth/login"):
                return _Resp(200, {"token": "t"})
            return _Resp(codigo, datos)
    return _C


def _preparar(monkeypatch, codigo, datos):
    llamadas = []
    job.olvidar_token()
    monkeypatch.setattr(job, "_credenciales", lambda: ("http://api", "a@b.cl", "x"))
    monkeypatch.setattr(httpx, "Client", _cliente(codigo, datos, llamadas))
    return llamadas


def test_pide_aplicar_las_reglas(monkeypatch):
    llamadas = _preparar(monkeypatch, 200, {"recurrencias_procesadas": 3})
    assert job.publicar_reglas_manuales() == {"recurrencias_procesadas": 3}
    assert llamadas[-1] == "http://api/api/admin/procesar-recurrentes"
    job.olvidar_token()


def test_una_plataforma_sin_el_endpoint_no_es_un_fallo(monkeypatch):
    _preparar(monkeypatch, 404, {})
    marca = len(job._FALLOS)
    assert job.publicar_reglas_manuales() is None
    assert len(job._FALLOS) == marca
    job.olvidar_token()


def test_va_despues_del_stock_y_del_transito():
    """Con los datos de ayer la regla pediria lo que ya se compro."""
    # La secuencia de la corrida vive en `_correr`; `_run` solo la envuelve.
    fuente = inspect.getsource(job._correr)
    i = fuente.index("publicar_reglas_manuales")
    assert fuente.index("publicar_stock_unificado") < i
    assert fuente.index("publicar_transito") < i
