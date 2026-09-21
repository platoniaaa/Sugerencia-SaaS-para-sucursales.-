"""Una sola corrida del motor a la vez en este PC.

El lunes 14-09-2026 corrieron tres motores en media hora: el que lanza la tarea
semanal de vigentes FORD al terminar (09:26), la tarea diaria (09:30) y una
manual (09:40). Dos a la vez no caben en memoria -Polars se cayo con "memory
allocation of 682183424 bytes failed"- y la que muere a mitad deja la plataforma
con unas tablas nuevas y otras viejas.

Lo que estos tests cuidan:

1. Que la segunda corrida NO arranque si hay una viva, y que salga limpio (0):
   la otra va a publicar lo mismo, no es un fallo.
2. Que un candado huerfano -el proceso ya no existe- no deje al motor
   bloqueado para siempre.
3. Que el candado se suelte aunque la corrida reviente.
"""
import os

import pytest

from src.jobs import correr_motor_real as job


@pytest.fixture
def candado(tmp_path, monkeypatch):
    ruta = tmp_path / "motor.lock"
    monkeypatch.setattr(job, "CANDADO", ruta)
    return ruta


def test_la_primera_corrida_toma_el_candado(candado):
    assert job.tomar_candado() is None
    assert candado.exists()
    assert candado.read_text(encoding="utf-8").startswith(str(os.getpid()))
    job.soltar_candado()
    assert not candado.exists()


def test_la_segunda_corrida_no_arranca_si_hay_una_viva(candado, monkeypatch):
    # El propio proceso de test hace de "la otra corrida": esta vivo seguro.
    candado.write_text(f"{os.getpid()} 2026-09-14 09:26:00", encoding="utf-8")
    llamadas = []
    monkeypatch.setattr(job, "_run", lambda **kw: llamadas.append(kw) or 0)

    assert job.run(oficial=True) == 0
    assert llamadas == [], "el motor corrio igual con otra corrida en curso"
    # Y no toco el candado ajeno.
    assert candado.read_text(encoding="utf-8").startswith(str(os.getpid()))


def test_un_candado_huerfano_se_pisa(candado, monkeypatch):
    """Si el PC se apago a mitad, el archivo queda pero el proceso no."""
    candado.write_text("999999999 2026-09-13 09:30:00", encoding="utf-8")
    monkeypatch.setattr(job, "_proceso_vivo", lambda pid: False)
    monkeypatch.setattr(job, "_run", lambda **kw: 0)

    assert job.run(oficial=True) == 0
    assert not candado.exists()


def test_el_candado_se_suelta_aunque_la_corrida_reviente(candado, monkeypatch):
    def revienta(**kw):
        raise RuntimeError("memory allocation of 682183424 bytes failed")

    monkeypatch.setattr(job, "_run", revienta)

    with pytest.raises(RuntimeError):
        job.run(oficial=True)
    assert not candado.exists()


def test_un_candado_ilegible_no_bloquea(candado, monkeypatch):
    candado.write_text("basura", encoding="utf-8")
    monkeypatch.setattr(job, "_run", lambda **kw: 0)

    assert job.run(oficial=True) == 0


# --- Un solo login por corrida ----------------------------------------------------
#
# El 21-09-2026 Render devolvio 429 (Too Many Requests) al login despues de un
# 502: cada paso de publicacion hacia su propio login -14 por corrida, mas uno
# por cada lote del feed del ERP- y desde el 429 fallaron InStock, compras, el
# recalculo y hasta la incidencia.


class _ClienteFalso:
    def __init__(self):
        self.logins = 0

    def post(self, url, **kw):
        assert url.endswith("/api/auth/login")
        self.logins += 1

        class R:
            def raise_for_status(self_inner):
                pass

            def json(self_inner):
                return {"token": f"t{self.logins}"}
        return R()


def test_el_token_se_pide_una_vez_y_se_reutiliza():
    job.olvidar_token()
    c = _ClienteFalso()

    t1 = job._token(c, "http://x", "a@b", "p")
    t2 = job._token(c, "http://x", "a@b", "p")
    t3 = job._token(c, "http://x", "a@b", "p")

    assert t1 == t2 == t3 == "t1"
    assert c.logins == 1
    job.olvidar_token()


def test_olvidar_el_token_obliga_a_entrar_de_nuevo():
    job.olvidar_token()
    c = _ClienteFalso()
    job._token(c, "http://x", "a@b", "p")

    job.olvidar_token()
    t = job._token(c, "http://x", "a@b", "p")

    assert t == "t2" and c.logins == 2
    job.olvidar_token()


def test_el_reintento_renueva_la_sesion(monkeypatch):
    """Si la sesion se invalido a mitad de corrida, el reintento entra de nuevo."""
    job.olvidar_token()
    job._TOKEN["valor"] = "viejo"
    monkeypatch.setattr(job, "ESPERA_BASE_SEG", 0)
    intentos = []

    def paso():
        intentos.append(job._TOKEN["valor"])
        if len(intentos) == 1:
            job.fallo_publicacion("prueba", RuntimeError("Client error '401 Unauthorized'"))
        return {"ok": True}

    r = job.publicar_con_reintentos("prueba", paso)

    assert r == {"ok": True}
    assert intentos[0] == "viejo" and intentos[1] is None, "el segundo intento parte sin token"
    job.olvidar_token()


def test_429_y_401_se_reintentan():
    assert job._es_transitorio(RuntimeError("Client error '429 Too Many Requests'"))
    assert job._es_transitorio(RuntimeError("Client error '401 Unauthorized'"))
    assert not job._es_transitorio(RuntimeError("Client error '403 Forbidden'"))
