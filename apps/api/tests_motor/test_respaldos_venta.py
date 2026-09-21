"""Un archivo ajeno en la carpeta de crudos no puede tumbar la corrida.

Los respaldos de venta se eligen POR DESCARTE: cualquier .xlsx bajo la carpeta de
crudos que tenga el año en el nombre y no sea una fuente conocida entra a la
lista. No hay patrón que los identifique.

El 08-09-2026 alguien dejó ahí "Lubricantes Motorcraft - Ventas mensuales por
canal 2025-2026.xlsx" -un reporte por canal, no una venta línea a línea- y el
motor no publicó nada ese día: ni la corrida automática de las 9:30 ni la manual.

Ahora se descarta lo que no tenga la forma esperada. Descartar NO es ignorar: el
nombre sale en el log y en las advertencias de la carga, porque un respaldo de
verdad que cambió de formato tiene que verse.
"""
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.motor import lectores_excel


def _xlsx(tmp_path: Path, nombre: str, cabeceras: list, filas: list | None = None) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(cabeceras)
    for f in filas or []:
        ws.append(f)
    ruta = tmp_path / nombre
    wb.save(ruta)
    return ruta


CABECERA_VENTAS = ["Fecha", "Producto", "Cantidad", "tipoDocto", "tipoproducto", "SUCURSAL"]


def test_reconoce_un_respaldo_de_venta(tmp_path):
    ruta = _xlsx(tmp_path, "2026 (6).xlsx", CABECERA_VENTAS,
                 [["2026-01-01", "17 A", 3, "FACTURA", "REPUESTO", "01 LINDEROS"]])

    assert lectores_excel.parece_respaldo_de_venta(ruta) is True


def test_descarta_un_reporte_que_no_es_venta(tmp_path):
    """El caso exacto: un reporte mensual por canal."""
    ruta = _xlsx(tmp_path, "Lubricantes Motorcraft - Ventas mensuales por canal 2025-2026.xlsx",
                 ["Canal", "Mes", "Litros", "Monto"],
                 [["Mostrador", "2026-01", 120, 900000]])

    assert lectores_excel.parece_respaldo_de_venta(ruta) is False


def test_descarta_un_excel_vacio(tmp_path):
    assert lectores_excel.parece_respaldo_de_venta(_xlsx(tmp_path, "2026 vacio.xlsx", [])) is False


def test_un_respaldo_al_que_le_falta_UNA_columna_obligatoria_se_descarta(tmp_path):
    """Y por eso el descarte se avisa: si un respaldo de verdad cambia de formato,
    esto lo saca de la corrida y nadie tiene que adivinar por qué bajó la venta."""
    sin_cantidad = [c for c in CABECERA_VENTAS if c != "Cantidad"]
    ruta = _xlsx(tmp_path, "2026 (7).xlsx", sin_cantidad)

    assert lectores_excel.parece_respaldo_de_venta(ruta) is False


def test_la_prueba_no_lee_los_datos(tmp_path):
    """`solo_encabezados` corta apenas encuentra la cabecera: un respaldo pesa
    40 MB y se probaria dos veces en cada corrida."""
    ruta = _xlsx(tmp_path, "2026 (8).xlsx", CABECERA_VENTAS,
                 [["2026-01-01", "17 A", 3, "FACTURA", "REPUESTO", "01 LINDEROS"]] * 5)

    df = lectores_excel.leer_reporte(
        ruta, lectores_excel.COLUMNAS_VENTAS,
        obligatorias=lectores_excel.OBLIGATORIAS_VENTAS, solo_encabezados=True)

    assert df.height == 0
    assert "Producto" in df.columns


def test_sin_solo_encabezados_sigue_leyendo_todo(tmp_path):
    """La bandera no puede cambiar el comportamiento normal del lector."""
    ruta = _xlsx(tmp_path, "2026 (9).xlsx", CABECERA_VENTAS,
                 [["2026-01-01", "17 A", 3, "FACTURA", "REPUESTO", "01 LINDEROS"]] * 4)

    df = lectores_excel.leer_reporte(
        ruta, lectores_excel.COLUMNAS_VENTAS, obligatorias=lectores_excel.OBLIGATORIAS_VENTAS)

    assert df.height == 4


# --- El descarte tiene que valer para TODOS los que usan la seleccion -----------
#
# `_archivos_de_ventas` la llaman `construir_csv` y `publicar_ventas_historicas`.
# El 08-09-2026 el filtro estaba en el primero: el sugerido publico bien y la
# carga de ventas historicas se cayo con el mismo archivo. Por eso el descarte
# vive DENTRO de la seleccion, no en el llamador.


def test_la_seleccion_ya_viene_filtrada(tmp_path, monkeypatch):
    from src.jobs import correr_motor_real as job

    _xlsx(tmp_path, "2026 (6).xlsx", CABECERA_VENTAS,
          [["2026-01-01", "17 A", 3, "FACTURA", "REPUESTO", "01 LINDEROS"]])
    _xlsx(tmp_path, "Lubricantes Motorcraft - por canal 2026.xlsx",
          ["Canal", "Mes", "Litros"], [["Mostrador", "2026-01", 12]])

    monkeypatch.setattr(job, "CRUDOS_DIR", tmp_path)
    job._AVISOS_FUENTES.clear()

    nombres = [p.name for p in job._archivos_de_ventas(date(2026, 9, 1))]

    assert nombres == ["2026 (6).xlsx"]
    assert len(job._AVISOS_FUENTES) == 1
    assert "Motorcraft" in job._AVISOS_FUENTES[0]


def test_el_aviso_no_se_repite_entre_llamadas(tmp_path, monkeypatch):
    """La seleccion corre dos veces por corrida; el aviso es uno solo."""
    from src.jobs import correr_motor_real as job

    _xlsx(tmp_path, "no es venta 2026.xlsx", ["Canal"], [["Mostrador"]])
    monkeypatch.setattr(job, "CRUDOS_DIR", tmp_path)
    job._AVISOS_FUENTES.clear()

    job._archivos_de_ventas(date(2026, 9, 1))
    job._archivos_de_ventas(date(2026, 9, 1))

    assert len(job._AVISOS_FUENTES) == 1
