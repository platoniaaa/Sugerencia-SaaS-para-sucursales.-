"""Lo que se publica como proveedor es lo MISMO que usa el sugerido.

Si el job reimplementara la deduccion, la plataforma mostraria un proveedor y el
sugerido otro para el mismo repuesto, y no habria forma de saber cual creer. Por
eso llama a `lead_time.proveedor_por_producto` y no arma la regla de nuevo.

Publicar esto nunca puede romper la corrida: el sugerido ya esta cargado cuando
se llega aca, asi que cualquier falla se avisa y se sigue.
"""
from datetime import date

import polars as pl

from src.jobs import correr_motor_real as job

OC = date(2026, 1, 1)


def _seguimiento() -> pl.DataFrame:
    return pl.DataFrame(
        [
            # Dos sucursales del mismo producto: tiene que salir UNA fila.
            {"Producto": "25 KV6Z9155D", "SucursalID": "LINDEROS", "RazonSocial": "FORD MOTOR",
             "FechaOC": OC, "NOC": 1, "Origen": "Curifor Nacional", "Motivo": "reposicion"},
            {"Producto": "25 KV6Z9155D", "SucursalID": "TALCA", "RazonSocial": "FORD MOTOR",
             "FechaOC": OC, "NOC": 2, "Origen": "Curifor Nacional", "Motivo": "reposicion"},
            {"Producto": "95 1751116000", "SucursalID": "CURICO", "RazonSocial": "GILDEMEISTER",
             "FechaOC": OC, "NOC": 3, "Origen": "Curifor Nacional", "Motivo": "reposicion"},
            # Sin razon social: no se puede deducir nada.
            {"Producto": "13 SINPROV", "SucursalID": "CURICO", "RazonSocial": None,
             "FechaOC": OC, "NOC": 4, "Origen": "Curifor Nacional", "Motivo": "reposicion"},
        ],
        schema={"Producto": pl.Utf8, "SucursalID": pl.Utf8, "RazonSocial": pl.Utf8,
                "FechaOC": pl.Date, "NOC": pl.Int64, "Origen": pl.Utf8, "Motivo": pl.Utf8},
    )


class _RespuestaFalsa:
    def __init__(self, datos):
        self._datos = datos

    def raise_for_status(self):
        pass

    def json(self):
        return self._datos


class _ClienteFalso:
    """Cliente httpx de mentira que anota lo que se le manda."""

    def __init__(self, enviado, **kw):
        self._enviado = enviado

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None, headers=None):
        self._enviado.append((url, json))
        if url.endswith("/api/auth/login"):
            return _RespuestaFalsa({"token": "t"})
        return _RespuestaFalsa({"filas_cargadas": len(json["filas"])})


def _publicar(monkeypatch, fuentes) -> tuple[dict | None, list]:
    import httpx

    enviado: list = []
    monkeypatch.setattr(job, "_credenciales", lambda: ("http://api", "a@b.cl", "x"))
    monkeypatch.setattr(httpx, "Client", lambda **kw: _ClienteFalso(enviado, **kw))
    return job.publicar_proveedor_producto(fuentes), enviado


def test_publica_una_fila_por_producto(monkeypatch):
    resumen, enviado = _publicar(monkeypatch, {"seguimiento": _seguimiento()})

    url, payload = enviado[-1]
    assert url == "http://api/api/admin/proveedor-producto"
    filas = {f["producto"]: f["proveedor"] for f in payload["filas"]}
    assert filas == {"25 KV6Z9155D": "FORD MOTOR", "95 1751116000": "GILDEMEISTER"}
    assert resumen["filas_cargadas"] == 2


def test_usa_la_misma_regla_que_el_sugerido(monkeypatch):
    """No se reimplementa la deduccion: se llama a la del motor."""
    from src.motor.lead_time import proveedor_por_producto

    seg = _seguimiento()
    _, enviado = _publicar(monkeypatch, {"seguimiento": seg})
    del_job = {f["producto"]: f["proveedor"] for f in enviado[-1][1]["filas"]}
    del_motor = {r["Producto"]: r["proveedor"] for r in proveedor_por_producto(seg).to_dicts()}
    assert del_job == del_motor


def test_sin_seguimiento_no_publica_nada(monkeypatch):
    """Si falta el Excel, se sigue: el sugerido ya quedo cargado."""
    assert _publicar(monkeypatch, {})[0] is None


def test_un_seguimiento_sin_razones_sociales_no_publica(monkeypatch):
    seg = _seguimiento().with_columns(pl.lit(None, dtype=pl.Utf8).alias("RazonSocial"))
    resumen, enviado = _publicar(monkeypatch, {"seguimiento": seg})
    assert resumen is None
    assert enviado == []  # ni siquiera se hace login


def test_si_la_plataforma_falla_no_rompe_la_corrida(monkeypatch):
    import httpx

    def _revienta(**kw):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(job, "_credenciales", lambda: ("http://api", "a@b.cl", "x"))
    monkeypatch.setattr(httpx, "Client", _revienta)
    assert job.publicar_proveedor_producto({"seguimiento": _seguimiento()}) is None


def test_sin_credenciales_no_publica(monkeypatch):
    monkeypatch.setattr(job, "_credenciales", lambda: ("http://api", None, None))
    assert job.publicar_proveedor_producto({"seguimiento": _seguimiento()}) is None
