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
        "producto", "glosa", "stock", "costo", "precio_erp", "tipo_erp", "procedencia"}


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

    monkeypatch.setattr(fuentes, "CRUDOS_DIR", tmp_path)
    monkeypatch.setattr(job, "MARCA_LISTA_ERP", tmp_path / "marca.txt")

    assert job.publicar_lista_erp() is None


def test_la_frescura_avisa_pero_no_frena():
    assert job.FRESCURA_DIAS["lista_erp"] == 10
    assert "lista_erp" in job.FRESCURA_SOLO_AVISA
