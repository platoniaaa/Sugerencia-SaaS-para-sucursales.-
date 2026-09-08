"""Que atraso frena la carga y cual solo se avisa.

La guarda de frescura existe porque olvidar una exportacion no da ningun error:
el motor calcula igual y publica un sugerido con el stock de la semana pasada.

Pero tenerla como bloqueante para TODOS los archivos por igual salio mal. Las
ventas de Frontera se atrasaron y la carga diaria quedo caida 8 dias seguidos
(27-08 al 03-09-2026), lo que obligo a publicar a mano con --ignorar-frescura,
que apaga la guarda para todo -incluido el stock, que si importa-. Una guarda que
obliga a saltearse todas las guardas es peor que no tenerla.

Medido sobre 17.100 filas: 49 son Solo Frontera y ninguna pide algo. El 95,5% del
valor sugerido es Curifor puro.
"""
from datetime import date, timedelta

import pytest

from src.jobs import correr_motor_real as motor


@pytest.fixture()
def crudos(tmp_path, monkeypatch):
    """Una carpeta de crudos con un archivo por fuente, todos recien tocados."""
    from src.motor import fuentes

    rutas = {}
    for nombre in motor.FRESCURA_DIAS:
        f = tmp_path / f"{nombre}.xlsx"
        f.write_bytes(b"x")
        rutas[nombre] = f
    monkeypatch.setattr(fuentes, "ruta_de", lambda n: rutas[n])
    return rutas


def _envejecer(ruta, dias: int) -> None:
    import os

    viejo = (date.today() - timedelta(days=dias)).toordinal()
    t = (viejo - date(1970, 1, 1).toordinal()) * 86400
    os.utime(ruta, (t, t))


def test_el_stock_atrasado_frena_la_carga(crudos):
    """Publicar con el stock de hace tres dias hace comprar de mas. Eso si frena."""
    _envejecer(crudos["stock_bodegas"], 5)

    frena = motor.frescura_que_frena()

    assert len(frena) == 1
    assert "stock_bodegas" in frena[0]


def test_las_ventas_de_frontera_atrasadas_NO_frenan_la_carga(crudos):
    """Es el caso que dejo el job caido 8 dias."""
    _envejecer(crudos["ventas_frontera"], 60)

    assert motor.frescura_que_frena() == []


def test_pero_el_atraso_de_frontera_se_sigue_avisando(crudos):
    """Que no frene no significa esconderlo: el dato viejo se informa igual, y el
    aviso dice explicitamente que no frena, para que nadie lo confunda con la
    causa de un fallo."""
    _envejecer(crudos["ventas_frontera"], 60)

    avisos = motor.revisar_frescura()

    assert len(avisos) == 1
    assert "ventas_frontera" in avisos[0]
    assert "no frena la carga" in avisos[0]


def test_frontera_atrasada_no_tapa_un_atraso_que_si_importa(crudos):
    """El riesgo de la excepcion: que sirva de excusa para no ver lo demas."""
    _envejecer(crudos["ventas_frontera"], 60)
    _envejecer(crudos["stock_bodegas"], 5)

    frena = motor.frescura_que_frena()

    assert len(frena) == 1
    assert "stock_bodegas" in frena[0]


def test_con_todo_al_dia_no_frena_nada(crudos):
    assert motor.frescura_que_frena() == []
    assert motor.revisar_frescura() == []


# --- Dias habiles, no corridos --------------------------------------------------
#
# Los archivos se exportan en dias de trabajo. Contando dias corridos, uno del
# viernes tiene 3 dias el lunes, y cualquier limite de 2 lo da por vencido: la
# carga se frenaba TODOS los lunes por un archivo que era del ultimo dia habil.
# Paso el 07-09-2026 con `stock_frontera.xlsx`.


@pytest.mark.parametrize("desde,hasta,esperado", [
    # viernes -> lunes: el sabado y el domingo no cuentan
    (date(2026, 9, 4), date(2026, 9, 7), 1),
    # lunes -> martes
    (date(2026, 9, 7), date(2026, 9, 8), 1),
    # miercoles -> lunes siguiente: jue, vie, lun
    (date(2026, 9, 2), date(2026, 9, 7), 3),
    # viernes -> viernes siguiente
    (date(2026, 9, 4), date(2026, 9, 11), 5),
    # el mismo dia
    (date(2026, 9, 7), date(2026, 9, 7), 0),
    # sabado -> lunes
    (date(2026, 9, 5), date(2026, 9, 7), 1),
])
def test_los_fines_de_semana_no_cuentan(desde, hasta, esperado):
    assert motor.dias_habiles(desde, hasta) == esperado


def test_un_archivo_del_viernes_no_vence_el_lunes(crudos, monkeypatch):
    """El caso exacto que freno la carga del 07-09-2026.

    `stock_bodegas_frontera` admite 2 dias. El archivo era del viernes: 3 dias
    corridos, 1 habil. Con dias corridos la carga se frenaba todos los lunes.
    """
    import os

    viernes = date(2026, 9, 4)
    t = (viernes.toordinal() - date(1970, 1, 1).toordinal()) * 86400
    os.utime(crudos["stock_bodegas_frontera"], (t, t))

    lunes = date(2026, 9, 7)
    assert motor.frescura_que_frena(lunes) == []


def test_pero_un_archivo_de_hace_una_semana_si_vence(crudos):
    """Relajar el conteo no puede volver inutil la guarda."""
    import os

    hace_una_semana = date(2026, 8, 31)
    t = (hace_una_semana.toordinal() - date(1970, 1, 1).toordinal()) * 86400
    os.utime(crudos["stock_bodegas"], (t, t))

    frena = motor.frescura_que_frena(date(2026, 9, 7))

    assert len(frena) == 1
    assert "stock_bodegas" in frena[0]
