"""`MOTOR_CRUDOS_DIR` puede apuntar a varias carpetas, separadas por `;`.

Por que hace falta: los crudos dejaron de estar todos en un solo lugar. Las
ventas las mantiene otra persona en la biblioteca de SharePoint "Respaldos BBDD"
(ahi las actualiza sola, sin que nadie las baje a mano), pero los vigentes de
FORD los GENERA el extractor en este PC y los deja en la carpeta local. Con una
sola carpeta configurable habia que elegir cual de las dos se pierde.

Lo que se prueba es el contrato: varias carpetas se leen como si fueran una, el
orden entre ellas no decide (manda la fecha del archivo, como siempre), y una
ruta que no existe no rompe la corrida -una biblioteca de SharePoint puede estar
desconectada un rato-.
"""
import importlib

import pytest


@pytest.fixture
def fuentes_en(tmp_path, monkeypatch):
    """Recarga el modulo con MOTOR_CRUDOS_DIR apuntando a las carpetas dadas.

    `CRUDOS_DIR` se resuelve al importar, asi que no basta con cambiar la
    variable de entorno: hay que volver a importar el modulo.
    """
    def _montar(*carpetas, crear=True, stock=()):
        rutas = []
        for nombre in carpetas:
            p = tmp_path / nombre
            if crear:
                p.mkdir(parents=True, exist_ok=True)
            rutas.append(str(p))
        monkeypatch.setenv("MOTOR_CRUDOS_DIR", ";".join(rutas))
        # Vacia a proposito si el test no la usa: sin esto se colaria la carpeta
        # de stock del .env de este PC y los tests dependerian de la maquina.
        monkeypatch.setenv("MOTOR_STOCK_DIR", ";".join(str(tmp_path / c) for c in stock))
        from src.motor import fuentes

        importlib.reload(fuentes)
        return fuentes, [tmp_path / c for c in carpetas]

    yield _montar
    # Deja el modulo como estaba para el resto de la suite.
    monkeypatch.delenv("MOTOR_CRUDOS_DIR", raising=False)
    monkeypatch.delenv("MOTOR_STOCK_DIR", raising=False)
    from src.motor import fuentes

    importlib.reload(fuentes)


def _excel(ruta, nombre):
    """Un archivo con nombre y extension de Excel, vacio.

    Para ELEGIR un archivo el motor solo mira el nombre, la extension y la fecha;
    no lo abre. Escribir un .xlsx de verdad ataria estos tests a tener xlsxwriter
    instalado, que es justo lo que no hace falta probar aca.
    """
    ruta.mkdir(parents=True, exist_ok=True)
    destino = ruta / nombre
    destino.touch()
    return destino


def test_una_sola_carpeta_sigue_funcionando_igual(fuentes_en):
    f, (carpeta,) = fuentes_en("crudos")
    _excel(carpeta / "stock", "STOCK_BODEGAS_CURIFOR.xlsx")

    assert f.ruta_de("stock_bodegas").name == "STOCK_BODEGAS_CURIFOR.xlsx"
    assert f.CRUDOS_DIRS == [carpeta]
    # CRUDOS_DIR se mantiene como la primera: lo usan el job y los mensajes.
    assert f.CRUDOS_DIR == carpeta


def test_encuentra_archivos_en_cualquiera_de_las_carpetas(fuentes_en):
    """El caso real: un crudo que mantiene otra persona en SharePoint y otro que
    genera este PC."""
    f, (sharepoint, local) = fuentes_en("RespaldosBBDD", "Bases de datos")
    _excel(sharepoint / "stock", "STOCK_BODEGAS_CURIFOR.xlsx")
    _excel(local / "Vigentes Ford", "Vigentes ford curifor_20260928_resultado.xlsx")

    assert f.ruta_de("stock_bodegas").parent == sharepoint / "stock"
    assert f.ruta_de("vigentes_ford").parent == local / "Vigentes Ford"


def test_entre_dos_copias_gana_la_mas_reciente_este_donde_este(fuentes_en):
    """El criterio no cambia por estar en carpetas distintas: manda la fecha.

    Importa durante la transicion: el mismo respaldo va a existir un tiempo en
    las dos carpetas, y lo que tiene que ganar es el ultimo, no el de la carpeta
    que quedo primera en la configuracion.
    """
    import os
    import time

    f, (primera, segunda) = fuentes_en("primera", "segunda")
    vieja = _excel(primera, "STOCK_BODEGAS_CURIFOR.xlsx")
    nueva = _excel(segunda, "STOCK_BODEGAS_CURIFOR.xlsx")
    antes = time.time() - 3600
    os.utime(vieja, (antes, antes))

    assert f.ruta_de("stock_bodegas") == nueva
    # Y las dos siguen siendo candidatas: `rutas_de` las concatena.
    assert set(f.rutas_de("stock_bodegas")) == {vieja, nueva}


def test_una_carpeta_que_no_existe_no_rompe_la_corrida(fuentes_en):
    """La biblioteca de SharePoint puede estar desconectada o aun sin sincronizar.

    Que el motor reviente por eso seria peor que seguir con lo que si tiene a
    mano: la frescura ya avisa cuando un crudo quedo viejo.
    """
    f, (existe, _) = fuentes_en("existe", "todavia-no-sincronizada", crear=False)
    existe.mkdir(parents=True, exist_ok=True)
    _excel(existe / "stock", "STOCK_BODEGAS_CURIFOR.xlsx")

    assert f.ruta_de("stock_bodegas").name == "STOCK_BODEGAS_CURIFOR.xlsx"


def test_el_error_de_fuente_faltante_nombra_todas_las_carpetas(fuentes_en):
    """Si no aparece, hay que saber DONDE se busco; con dos carpetas, en cual
    de las dos hay que dejar el archivo no es obvio."""
    f, (a, b) = fuentes_en("una", "otra")
    # Sin esto el test pasa igual con el codigo viejo: la ruta sin separar
    # contiene las dos como texto.
    assert f.CRUDOS_DIRS == [a, b]

    with pytest.raises(FileNotFoundError) as e:
        f.ruta_de("stock_bodegas")
    assert str(a) in str(e.value) and str(b) in str(e.value)


def test_el_inventario_dice_de_que_carpeta_salio_cada_archivo(fuentes_en):
    f, (sharepoint, local) = fuentes_en("RespaldosBBDD", "Bases de datos")
    _excel(sharepoint / "Seguimientos", "seguimiento_compras_nacional.xlsx")
    _excel(local / "stock", "STOCK_BODEGAS_CURIFOR.xlsx")

    reporte = f.inventariar()
    assert str(sharepoint) in reporte and str(local) in reporte
    assert "[OK]    seguimiento_curifor_nacional" in reporte
    assert "[OK]    stock_bodegas" in reporte


# --------------------------------------------------------------------------
# MOTOR_STOCK_DIR: la carpeta de SharePoint donde el equipo sube el stock cada
# dia (Data BI/Datos). Se lee SOLO para el stock porque trae tambien archivos
# que no son del motor: seguimientos de compras y produccion post-venta.
# --------------------------------------------------------------------------
def _envejecer(ruta, horas):
    import os
    import time

    t = time.time() - horas * 3600
    os.utime(ruta, (t, t))


def test_la_carpeta_de_stock_alimenta_el_stock(fuentes_en):
    f, (local,) = fuentes_en("Bases de datos", stock=("Datos",))
    viejo = _excel(local / "stock", "STOCK_BODEGAS_CURIFOR.xlsx")
    _envejecer(viejo, 5)
    nuevo = _excel(f.STOCK_DIRS[0], "Stock bodegas.xlsx")

    assert f.ruta_de("stock_bodegas") == nuevo


def test_la_carpeta_de_stock_no_alimenta_las_otras_fuentes(fuentes_en):
    """El riesgo real de sumarla a MOTOR_CRUDOS_DIR: archivos mas nuevos de otra
    gente ganandole por fecha a los nuestros."""
    f, (local,) = fuentes_en("Bases de datos", stock=("Datos",))
    datos = f.STOCK_DIRS[0]
    nuestro_seg = _excel(local / "Seguimientos", "seguimiento_compras_nacional.xlsx")
    nuestras_vtas = _excel(local / "Ventas Frontera", "ventas frontera 2026.xlsx")
    _envejecer(nuestro_seg, 48)
    _envejecer(nuestras_vtas, 48)
    ajeno_seg = _excel(datos, "Curifor - Seguimiento Compras.xlsx")
    ajena_prod = _excel(datos, "Frontera - Producción Mensual Post-Venta.xlsx")

    # Los dos ajenos SI calzan con esos patrones: por eso hace falta la separacion.
    assert f._matchea(ajeno_seg.name, f.FUENTES["seguimiento_curifor_nacional"])
    assert f._matchea(ajena_prod.name, f.FUENTES["ventas_frontera"])
    assert f.ruta_de("seguimiento_curifor_nacional") == nuestro_seg
    assert f.rutas_de("ventas_frontera") == [nuestras_vtas]


def test_la_carpeta_de_stock_no_se_lee_por_dentro(fuentes_en):
    """La subcarpeta "Anteriores" guarda versiones viejas: aunque una tenga fecha
    mas nueva -alguien la movio hoy-, no puede pasar por el stock del dia."""
    f, _ = fuentes_en("Bases de datos", stock=("Datos",))
    del_dia = _excel(f.STOCK_DIRS[0], "Stock bodegas.xlsx")
    _envejecer(del_dia, 2)
    _excel(f.STOCK_DIRS[0] / "Anteriores", "Stock bodegas 2025-11-27.xlsx")

    assert f.rutas_de("stock_bodegas") == [del_dia]


def test_entre_el_stock_local_y_el_de_sharepoint_manda_la_fecha(fuentes_en):
    """Mientras alguien siga dejando la copia local, gana la mas reciente: son el
    mismo reporte, asi que da lo mismo cual, pero nunca el de ayer."""
    f, (local,) = fuentes_en("Bases de datos", stock=("Datos",))
    sharepoint = _excel(f.STOCK_DIRS[0], "Stock bodegas.xlsx")
    copia = _excel(local / "stock", "STOCK_BODEGAS_CURIFOR.xlsx")
    _envejecer(sharepoint, 3)

    assert f.ruta_de("stock_bodegas") == copia


def test_la_carpeta_de_stock_desconectada_no_rompe_la_corrida(fuentes_en):
    f, (local,) = fuentes_en("Bases de datos", stock=("Datos-sin-sincronizar",))
    assert not f.STOCK_DIRS[0].exists()
    _excel(local / "stock", "STOCK_BODEGAS_CURIFOR.xlsx")

    assert f.ruta_de("stock_bodegas").name == "STOCK_BODEGAS_CURIFOR.xlsx"


def test_si_falta_el_stock_el_error_nombra_tambien_la_carpeta_de_stock(fuentes_en):
    f, (local,) = fuentes_en("Bases de datos", stock=("Datos",))
    with pytest.raises(FileNotFoundError) as e:
        f.ruta_de("stock_bodegas")
    assert str(local) in str(e.value) and str(f.STOCK_DIRS[0]) in str(e.value)


def test_sin_variable_de_stock_todo_sigue_igual(fuentes_en):
    f, (local,) = fuentes_en("Bases de datos")
    assert f.STOCK_DIRS == []
    _excel(local / "stock", "STOCK_BODEGAS_CURIFOR.xlsx")
    assert f.ruta_de("stock_bodegas").name == "STOCK_BODEGAS_CURIFOR.xlsx"
