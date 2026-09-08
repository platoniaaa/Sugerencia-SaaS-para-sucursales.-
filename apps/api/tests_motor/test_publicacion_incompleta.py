"""Cuando falla un paso de publicacion, la corrida NO puede terminar en verde.

Cada publicador se traga su excepcion a proposito -que falle el stock no debe
impedir que se publiquen los reemplazos- pero hasta el 01-09-2026 eso significaba
que `run` no distinguia "no habia nada que publicar" de "fallo", devolvia 0 y el
lanzador imprimia "Listo. Los compradores ya ven los datos nuevos.".

Paso tres veces en cuatro dias:

- 28-08: fallo la recarga de InStock (502). Zafamos: el 502 pego antes del
  borrado, asi que la lista quedo intacta por milisegundos.
- 01-09 (madrugada): fallo InStock otra vez.
- 01-09: fallaron CINCO pasos -stock, transito, ventas, equivalencias y
  proveedor-. El sugerido quedo con stock nuevo y la tabla de stock con el viejo:
  la grilla y la ficha del mismo repuesto mostraban numeros distintos, y el
  sugerido descontaba un transito viejo.

Quedar a medias es peor que no publicar nada, porque no se nota.
"""
import httpx
import pytest

from src.jobs import correr_motor_real as motor


@pytest.fixture(autouse=True)
def sin_fallos_previos():
    """`_FALLOS` es de modulo: sin esto un test arrastra el fallo del anterior."""
    motor._FALLOS.clear()
    yield
    motor._FALLOS.clear()


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    """Los reintentos esperan 15s y 30s de verdad. En el test no."""
    monkeypatch.setattr(motor.time, "sleep", lambda _s: None)


def _http(codigo: int) -> httpx.HTTPStatusError:
    pedido = httpx.Request("POST", "https://sugerido-api.onrender.com/api/admin/stock-unificado")
    return httpx.HTTPStatusError(
        f"Server error '{codigo}' for url ...",
        request=pedido,
        response=httpx.Response(codigo, request=pedido),
    )


# --- Que es transitorio y que no ------------------------------------------------


@pytest.mark.parametrize("codigo", [502, 503, 504])
def test_los_errores_de_render_despertando_son_transitorios(codigo):
    """Render devuelve esto mientras levanta el servicio. No es un error del dato."""
    assert motor._es_transitorio(_http(codigo)) is True


@pytest.mark.parametrize("e", [
    ValueError("la columna Producto no existe"),
    KeyError("token"),
])
def test_un_error_del_dato_no_es_transitorio(e):
    """Reintentar un error de datos solo hace perder tres minutos: va a fallar igual."""
    assert motor._es_transitorio(e) is False


def test_un_401_no_se_reintenta():
    """Credenciales malas no se arreglan esperando."""
    assert motor._es_transitorio(_http(401)) is False


# --- El reintento ---------------------------------------------------------------


def test_reintenta_el_502_y_lo_logra_al_segundo_intento():
    """Es el caso real: el primer intento despierta a Render y el segundo entra."""
    intentos = {"n": 0}

    def publicar():
        intentos["n"] += 1
        if intentos["n"] == 1:
            motor.fallo_publicacion("el stock", _http(502))
            return None
        return {"filas_cargadas": 30391}

    r = motor.publicar_con_reintentos("el stock", publicar)

    assert intentos["n"] == 2
    assert r == {"filas_cargadas": 30391}
    assert motor._FALLOS == [], "un paso que termino bien no puede quedar como fallo"


def test_un_error_que_no_es_transitorio_no_se_reintenta():
    intentos = {"n": 0}

    def publicar():
        intentos["n"] += 1
        motor.fallo_publicacion("el stock", ValueError("columna faltante"))
        return None

    assert motor.publicar_con_reintentos("el stock", publicar) is None
    assert intentos["n"] == 1
    assert len(motor._FALLOS) == 1


def test_si_falla_en_todos_los_intentos_queda_registrado():
    def publicar():
        motor.fallo_publicacion("el stock", _http(503))
        return None

    assert motor.publicar_con_reintentos("el stock", publicar) is None
    assert len(motor._FALLOS) == 1, "solo cuenta el ultimo intento, no los tres"
    assert motor._FALLOS[0]["paso"] == "el stock"


def test_no_hay_nada_que_publicar_no_es_un_fallo():
    """Un publicador devuelve None cuando el archivo no existe o no hay credenciales.

    Confundir eso con un error dejaria la corrida en rojo cada vez que falta un
    insumo opcional, y a la semana nadie mira el resultado.
    """
    assert motor.publicar_con_reintentos("el stock", lambda: None) is None
    assert motor._FALLOS == []


def test_los_argumentos_llegan_al_publicador():
    """Varios pasos reciben las fuentes de la corrida."""
    visto = {}

    def publicar(fuentes):
        visto.update(fuentes)
        return {"filas_cargadas": 1}

    motor.publicar_con_reintentos("los reemplazos", publicar, {"mapeo": "x"})

    assert visto == {"mapeo": "x"}


# --- El registro ----------------------------------------------------------------


def test_el_fallo_guarda_el_paso_y_el_error():
    """El detalle es lo que va a la incidencia: sin el, el admin ve 'fallo algo'."""
    motor.fallo_publicacion("el transito", _http(503))

    f = motor._FALLOS[0]
    assert f["paso"] == "el transito"
    assert "503" in f["error"]
    assert f["transitorio"] is True


# --- La carga principal tambien reintenta ---------------------------------------
#
# `enviar()` era la unica llamada sin proteccion, y es LA que importa: sin ella no
# hay sugerido nuevo. El 03-09-2026 la corrida murio con un 502 en
# `/api/admin/cargar-sugerido` mientras Render despertaba y la plataforma quedo
# todo el dia con el dato del dia anterior.


def _respuesta(codigo: int) -> httpx.HTTPStatusError:
    pedido = httpx.Request("POST", "https://x/api/admin/cargar-sugerido")
    return httpx.HTTPStatusError(
        f"Server error '{codigo}' for url", request=pedido,
        response=httpx.Response(codigo, request=pedido))


def test_la_carga_principal_reintenta_el_502(monkeypatch, tmp_path):
    intentos = {"n": 0}

    def falso(csv_path, oficial=False):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise _respuesta(502)
        return {"filas_cargadas": 17100}

    monkeypatch.setattr(motor, "_enviar_una_vez", falso)
    monkeypatch.setattr(motor.time, "sleep", lambda s: None)

    assert motor.enviar(tmp_path / "x.csv", oficial=True)["filas_cargadas"] == 17100
    assert intentos["n"] == 2


def test_la_carga_principal_no_reintenta_lo_que_no_es_transitorio(monkeypatch, tmp_path):
    """Un 401 o un CSV mal formado no se arreglan esperando."""
    intentos = {"n": 0}

    def falso(csv_path, oficial=False):
        intentos["n"] += 1
        raise _respuesta(401)

    monkeypatch.setattr(motor, "_enviar_una_vez", falso)
    monkeypatch.setattr(motor.time, "sleep", lambda s: None)

    with pytest.raises(httpx.HTTPStatusError):
        motor.enviar(tmp_path / "x.csv", oficial=True)
    assert intentos["n"] == 1


def test_si_la_plataforma_no_vuelve_la_carga_falla(monkeypatch, tmp_path):
    """Reintentar no es tapar: agotados los intentos, el error sale y el job cae."""
    intentos = {"n": 0}

    def falso(csv_path, oficial=False):
        intentos["n"] += 1
        raise _respuesta(503)

    monkeypatch.setattr(motor, "_enviar_una_vez", falso)
    monkeypatch.setattr(motor.time, "sleep", lambda s: None)

    with pytest.raises(httpx.HTTPStatusError):
        motor.enviar(tmp_path / "x.csv", oficial=True)
    assert intentos["n"] == motor.REINTENTOS
