"""El export del ERP alimenta la lista de precios de la plataforma.

Abastecimiento exporta `lista_erp.xlsx` a mano, semanal: 410 mil filas, una hoja,
el producto repetido por lote/serie y la columna "Tipo" dos veces. De ahi salen
los repuestos nuevos con stock y el precio ERP de todos.

Lo que estos tests cuidan:

1. Que el lector deje UNA fila por producto y no se confunda con el "Tipo"
   duplicado: el primero distingue repuesto de servicio, el segundo no sirve.
2. Que se publique SOLO cuando el archivo cambio. Son 80 lotes; mandarlos todos
   los dias por gusto es lo que hace que una carga de 15 minutos dure 25.
3. Que un lote caido no deje la marca escrita: manana se reintenta entero.
4. Que el codigo con espacio al final llegue tal cual en `codigo_erp`: es el que
   tiene que salir en el archivo que se sube al ERP.
"""
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.jobs import correr_motor_real as job
from src.motor import lectores_excel as lx

CABECERA = ["Producto", "Descripción", "Unidad", "Stock", "Stock Proyectado", "Costo",
            "Precio Venta", "%Max. D/R", "Tipo", "Stock Mínimo", "Stock Máximo", "Familia",
            "SubFamilia", "Tipo", "SubTipo", "Procedencia"]


def _fila(prod, desc, stock, costo, pv, tipo="REPUESTOS", proc="NACIONAL", tipo2="Zx"):
    return [prod, desc, "UNIDAD", stock, 0, costo, pv, "0,00", tipo, 0, 0, "RUBRO 17",
            "SUB", tipo2, "", proc]


def _erp_xlsx(tmp_path: Path, filas: list, nombre="lista_erp.xlsx") -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(CABECERA)
    for f in filas:
        ws.append(f)
    ruta = tmp_path / nombre
    wb.save(ruta)
    return ruta


# --- El lector ------------------------------------------------------------------


def test_una_fila_por_producto_con_el_stock_sumado(tmp_path):
    ruta = _erp_xlsx(tmp_path, [
        _fila("17 A", "AMORTIGUADOR", 3, 1000, 1780),   # lote 1
        _fila("17 A", "AMORTIGUADOR", 2, 1000, 1780),   # lote 2
        _fila("17 B", "BUJIA", 0, 500, 900),
    ])

    df = lx.leer_lista_erp(ruta)

    por = {r["producto"]: r for r in df.to_dicts()}
    assert set(por) == {"17 A", "17 B"}
    assert por["17 A"]["stock"] == 5
    assert por["17 A"]["precio_erp"] == 1780
    assert por["17 A"]["glosa"] == "AMORTIGUADOR"


def test_el_tipo_que_importa_es_el_primero(tmp_path):
    """La segunda columna "Tipo" es el tipo de repuesto (Zx, Otro...) y no
    distingue nada. Un servicio tiene MO_TERC en la primera."""
    ruta = _erp_xlsx(tmp_path, [
        _fila("17 TRAB DE TERCERO", "ALINEACION", 0, 0, 1, tipo="MO_TERC", tipo2="Otro"),
        _fila("17 A", "AMORTIGUADOR", 3, 1000, 1780, tipo="REPUESTOS", tipo2="Zx"),
    ])

    por = {r["producto"]: r for r in lx.leer_lista_erp(ruta).to_dicts()}

    assert por["17 TRAB DE TERCERO"]["tipo_erp"] == "MO_TERC"
    assert por["17 A"]["tipo_erp"] == "REPUESTOS"


def test_las_columnas_que_viajan_son_las_que_espera_la_plataforma(tmp_path):
    ruta = _erp_xlsx(tmp_path, [_fila("17 A", "X", 1, 1, 1)])

    assert set(lx.leer_lista_erp(ruta).columns) == {
        "producto", "glosa", "stock", "costo", "precio_erp", "tipo_erp", "procedencia",
        "codigo_erp"}


def test_el_codigo_con_espacio_al_final_viaja_tal_cual(tmp_path):
    """En el ERP hay codigos creados con un espacio al final. Por dentro se cruzan
    sin el espacio, pero el archivo que se sube al ERP tiene que llevarlo: viaja
    aparte, en `codigo_erp`, y solo cuando difiere (13-10-2026)."""
    ruta = _erp_xlsx(tmp_path, [
        _fila("15 MXD1454M ", "BALATA", 2, 1000, 1780),   # lote 1
        _fila("15 MXD1454M ", "BALATA", 1, 1000, 1780),   # lote 2
        _fila("17 A", "AMORTIGUADOR", 3, 1000, 1780),
    ])

    por = {r["producto"]: r for r in lx.leer_lista_erp(ruta).to_dicts()}

    assert set(por) == {"15 MXD1454M", "17 A"}
    assert por["15 MXD1454M"]["codigo_erp"] == "15 MXD1454M "
    assert por["15 MXD1454M"]["stock"] == 3
    assert por["17 A"]["codigo_erp"] is None


def test_si_el_erp_tambien_trae_el_codigo_limpio_va_el_limpio(tmp_path):
    """Si una fila del producto trae el codigo sin espacio, el ERP lo tiene asi."""
    ruta = _erp_xlsx(tmp_path, [
        _fila("17 B ", "BUJIA", 1, 500, 900),
        _fila("17 B", "BUJIA", 1, 500, 900),
    ])

    (fila,) = lx.leer_lista_erp(ruta).to_dicts()

    assert fila["producto"] == "17 B" and fila["codigo_erp"] is None


def test_sin_las_columnas_del_erp_se_dice_cuales_faltan(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Producto", "Descripción"])
    ws.append(["17 A", "X"])
    ruta = tmp_path / "lista_erp.xlsx"
    wb.save(ruta)

    with pytest.raises(ValueError, match="Precio Venta"):
        lx.leer_lista_erp(ruta)


# --- La fuente ------------------------------------------------------------------


def test_el_archivo_se_encuentra_por_su_nombre_y_no_se_confunde(tmp_path, monkeypatch):
    """`lista_erp.xlsx` es la fuente; `LISTA DE PRECIOS.xlsx` (el libro) y las
    listas de proveedor no."""
    from src.motor import fuentes

    _erp_xlsx(tmp_path, [_fila("17 A", "X", 1, 1, 1)])
    (tmp_path / "LISTA DE PRECIOS.xlsx").write_bytes(b"")
    (tmp_path / "Lista de precio ford al 28.07.2026.xlsx").write_bytes(b"")
    # Desde que los crudos pueden estar en varias carpetas (7ca3765) la busqueda
    # recorre CRUDOS_DIRS; parchar solo CRUDOS_DIR dejaba al test leyendo el
    # lista_erp.xlsx real de este PC (83 creados en vez de 1).
    monkeypatch.setattr(fuentes, "CRUDOS_DIRS", [tmp_path])
    monkeypatch.setattr(fuentes, "CRUDOS_DIR", tmp_path)

    assert fuentes.ruta_de("lista_erp").name == "lista_erp.xlsx"


# --- Publicar solo cuando cambia -----------------------------------------------


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    from src.motor import fuentes

    ruta = _erp_xlsx(tmp_path, [
        _fila("17 A", "AMORTIGUADOR", 3, 1000, 1780),
        _fila("17 B", "BUJIA", 0, 500, 900),
    ])
    # Desde que los crudos pueden estar en varias carpetas (7ca3765) la busqueda
    # recorre CRUDOS_DIRS; parchar solo CRUDOS_DIR dejaba al test leyendo el
    # lista_erp.xlsx real de este PC (83 creados en vez de 1).
    monkeypatch.setattr(fuentes, "CRUDOS_DIRS", [tmp_path])
    monkeypatch.setattr(fuentes, "CRUDOS_DIR", tmp_path)
    monkeypatch.setattr(job, "MARCA_LISTA_ERP", tmp_path / "marca.txt")
    enviados: list[list[dict]] = []

    def falso_publicar(paso, endpoint, filas):
        enviados.append(filas)
        return {"recibidos": len(filas), "actualizados": 1, "creados": 1,
                "no_entran": {"sin stock": 1}}

    monkeypatch.setattr(job, "_publicar_json", falso_publicar)
    return ruta, enviados


def test_publica_y_deja_la_marca(entorno):
    ruta, enviados = entorno

    r = job.publicar_lista_erp()

    assert r["creados"] == 1 and r["actualizados"] == 1
    assert r["no_entran"] == {"sin stock": 1}
    assert r["archivo"] == "lista_erp.xlsx"
    assert len(enviados) == 1 and len(enviados[0]) == 2
    assert enviados[0][0]["producto"] == "17 A"
    assert job.MARCA_LISTA_ERP.exists()


def test_el_mismo_archivo_no_se_publica_dos_veces(entorno):
    _, enviados = entorno

    job.publicar_lista_erp()
    r = job.publicar_lista_erp()

    assert r is None
    assert len(enviados) == 1


def test_un_archivo_nuevo_si_se_publica(entorno):
    ruta, enviados = entorno
    job.publicar_lista_erp()

    # Vuelve a exportar: mismo nombre, otro contenido (cambia el tamano).
    _erp_xlsx(ruta.parent, [_fila("17 A", "AMORTIGUADOR", 3, 1000, 1780)] * 5)
    r = job.publicar_lista_erp()

    assert r is not None
    assert len(enviados) == 2


def test_un_lote_caido_no_deja_la_marca(entorno, monkeypatch):
    _, enviados = entorno
    monkeypatch.setattr(job, "_publicar_json", lambda *a: None)

    assert job.publicar_lista_erp() is None
    assert not job.MARCA_LISTA_ERP.exists(), "manana tiene que reintentar entero"


def test_sin_archivo_no_es_un_fallo(tmp_path, monkeypatch):
    from src.motor import fuentes

    # Desde que los crudos pueden estar en varias carpetas (7ca3765) la busqueda
    # recorre CRUDOS_DIRS; parchar solo CRUDOS_DIR dejaba al test leyendo el
    # lista_erp.xlsx real de este PC (83 creados en vez de 1).
    monkeypatch.setattr(fuentes, "CRUDOS_DIRS", [tmp_path])
    monkeypatch.setattr(fuentes, "CRUDOS_DIR", tmp_path)
    monkeypatch.setattr(job, "MARCA_LISTA_ERP", tmp_path / "marca.txt")

    assert job.publicar_lista_erp() is None


def test_la_frescura_avisa_pero_no_frena():
    assert job.FRESCURA_DIAS["lista_erp"] == 10
    assert "lista_erp" in job.FRESCURA_SOLO_AVISA


# --- El costo con coma decimal ----------------------------------------------------


def test_el_costo_con_coma_decimal_se_lee(tmp_path):
    """El Excel de stock trae el costo como texto con coma: "95233,75000000".
    Con un cast a secas salia vacio en todas las filas y los productos nuevos
    nacian sin costo, o sea sin precio."""
    ruta = _erp_xlsx(tmp_path, [
        _fila("17 A", "AMORTIGUADOR", 3, "95233,75000000", 1780),
        _fila("17 B", "BUJIA", 1, "1.234,5", 900),
        _fila("17 C", "CORREA", 1, 500, 900),
    ])

    por = {r["producto"]: r for r in lx.leer_lista_erp(ruta).to_dicts()}

    assert por["17 A"]["costo"] == 95233.75
    assert por["17 B"]["costo"] == 1234.5
    assert por["17 C"]["costo"] == 500


# --- Las altas desde el stock del dia ----------------------------------------------


@pytest.fixture
def stock_del_dia(tmp_path, monkeypatch):
    """Un Excel de stock con formato del ERP y el feed falseado."""
    from src.motor import fuentes

    ruta = _erp_xlsx(tmp_path, [
        _fila("17 NUEVO", "AMORTIGUADOR", 2, "1000,5", 1780),
        _fila("17 YA", "BUJIA", 1, "500", 900),
    ], nombre="STOCK_BODEGAS_CURIFOR.xlsx")
    monkeypatch.setattr(fuentes, "CRUDOS_DIRS", [tmp_path])
    monkeypatch.setattr(fuentes, "CRUDOS_DIR", tmp_path)
    # Sin esto entraria la carpeta de SharePoint del .env de este PC.
    monkeypatch.setattr(fuentes, "STOCK_DIRS", [])
    monkeypatch.setattr(job, "MARCA_STOCK_PRECIOS", tmp_path / "marca_stock.txt")
    monkeypatch.setattr(job, "MARCA_LISTA_ERP", tmp_path / "marca_erp.txt")
    enviados: list[tuple[str, list[dict]]] = []

    def falso_publicar(paso, endpoint, filas):
        enviados.append((endpoint, filas))
        return {"recibidos": len(filas), "actualizados": 1, "creados": 1, "no_entran": {}}

    monkeypatch.setattr(job, "_publicar_json", falso_publicar)
    return ruta, enviados


def test_el_stock_del_dia_va_por_el_mismo_feed_que_el_erp(stock_del_dia):
    """Mismo endpoint y mismas columnas: las reglas de entrada siguen en un solo
    lugar, la plataforma."""
    _, enviados = stock_del_dia

    r = job.publicar_altas_desde_stock()

    assert r["creados"] == 1 and r["archivo"] == "STOCK_BODEGAS_CURIFOR.xlsx"
    assert [e for e, _ in enviados] == ["/api/admin/precios/erp"]
    filas = {f["producto"]: f for f in enviados[0][1]}
    assert set(filas) == {"17 NUEVO", "17 YA"}
    assert filas["17 NUEVO"]["costo"] == 1000.5, "nace con costo, o sea con precio"
    assert set(filas["17 NUEVO"]) == {
        "producto", "glosa", "stock", "costo", "precio_erp", "tipo_erp", "procedencia",
        "codigo_erp"}


def test_el_mismo_stock_no_se_manda_dos_veces(stock_del_dia):
    _, enviados = stock_del_dia

    job.publicar_altas_desde_stock()
    assert job.publicar_altas_desde_stock() is None
    assert len(enviados) == 1


def test_la_marca_del_stock_no_toca_la_del_export_del_erp(stock_del_dia):
    """Son dos archivos distintos: publicar uno no puede hacer creer al motor que
    el otro ya se publico."""
    job.publicar_altas_desde_stock()

    assert job.MARCA_STOCK_PRECIOS.exists()
    assert not job.MARCA_LISTA_ERP.exists()


def test_un_lote_caido_del_stock_no_deja_la_marca(stock_del_dia, monkeypatch):
    monkeypatch.setattr(job, "_publicar_json", lambda *a: None)

    assert job.publicar_altas_desde_stock() is None
    assert not job.MARCA_STOCK_PRECIOS.exists(), "manana tiene que reintentar entero"


def test_las_altas_van_antes_del_recalculo():
    """Si fueran despues, lo nuevo pasaria un dia entero sin precio."""
    import inspect

    # La secuencia de la corrida vive en `_correr`; `_run` solo la envuelve.
    fuente = inspect.getsource(job._correr)
    assert fuente.index("publicar_altas_desde_stock") < fuente.index("recalcular_precios)")
