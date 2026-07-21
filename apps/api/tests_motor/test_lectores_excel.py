"""Tests de los lectores de Excel (reportes de Flexline que viven en SharePoint).

Los Excel reales son privados y no estan en el repo, asi que cada test FABRICA un
archivo con las mismas particularidades verificadas en los archivos del 20-jul-2026:
titulo y filtros arriba (la fila de encabezados NO esta fija), columna A vacia,
fechas dd/mm/aaaa como texto, `tipoproducto` con prefijo de orden (`4Repuesto`) y
`SUCURSAL` con prefijo de informe (`08 TALCA`).
"""
from datetime import date

import polars as pl
import pytest
from openpyxl import Workbook

from src.motor import lectores_excel as lx
from src.motor.conectores import sql_flexline as F


def _crear_excel(ruta, encabezados, filas, *, filas_previas=0, col_a_vacia=True):
    """Escribe un Excel con `filas_previas` filas de basura antes del encabezado."""
    wb = Workbook()
    ws = wb.active
    for i in range(filas_previas):
        ws.append([None, "Seguimiento Compras"] if i == 2 else [None])
    desplazo = [None] if col_a_vacia else []
    ws.append(desplazo + list(encabezados))
    for fila in filas:
        ws.append(desplazo + list(fila))
    wb.save(ruta)
    return ruta


# --------------------------- deteccion de encabezados --------------------------- #
def test_encuentra_el_encabezado_aunque_no_este_en_la_primera_fila(tmp_path):
    """El reporte trae titulo y filtros arriba: el importado real empieza en la fila 9."""
    ruta = _crear_excel(
        tmp_path / "seg.xlsx",
        ["Producto", "Cantidad", "Fecha Orden de Compra"],
        [["70 123", 5, "14/01/2025"]],
        filas_previas=9,
    )
    df = lx.leer_reporte(
        ruta,
        {"Producto": "Producto", "Cantidad": "Cantidad", "FechaOC": "Fecha Orden de Compra"},
    )
    assert df.height == 1
    assert df["Producto"][0] == "70 123"


def test_encabezado_ausente_falla_con_mensaje_claro(tmp_path):
    ruta = _crear_excel(tmp_path / "otro.xlsx", ["Columna X"], [["dato"]])
    with pytest.raises(ValueError, match="No se encontro la fila de encabezados"):
        lx.leer_reporte(ruta, {"Producto": "Producto"})


def test_columna_faltante_queda_nula(tmp_path):
    """Los tres seguimientos no traen las mismas columnas; el esquema debe cuadrar igual."""
    ruta = _crear_excel(tmp_path / "seg.xlsx", ["Producto", "Cantidad"], [["P1", 3]])
    df = lx.leer_reporte(
        ruta,
        {"Producto": "Producto", "Cantidad": "Cantidad", "Motivo": "Motivo Compra"},
        obligatorias=["Producto"],
    )
    assert df["Motivo"].null_count() == 1


def test_nombres_de_columna_toleran_tildes_y_simbolos(tmp_path):
    """`N° Orden de Compra` cambia de acentuacion entre exportaciones."""
    ruta = _crear_excel(
        tmp_path / "seg.xlsx", ["Producto", "N Orden de Compra"], [["P1", "0000123"]]
    )
    df = lx.leer_reporte(ruta, {"Producto": "Producto", "NOC": "N° Orden de Compra"})
    assert df["NOC"][0] == "0000123"


# --------------------------- seguimientos --------------------------- #
def test_seguimiento_frontera_a_esquema_del_motor(tmp_path):
    ruta = _crear_excel(
        tmp_path / "frontera.xlsx",
        [
            "Producto", "Nombre Local", "Razón Social Proveedor", "Cantidad",
            "Estado Documento Base", "Fecha Documento Base", "N° Documento Base",
            "Fecha Recepción",
        ],
        [
            ["70 5876101570", "BRASIL 18", "GENERAL MOTORS CHILE", 15,
             "Cerrado por sistema", "02/01/2025", "0000005758", "21/01/2025"],
            ["70 8973779480", "DIEZ DE JULIO (2)", "GENERAL MOTORS CHILE", 1,
             "Cerrado por sistema", "02/01/2025", "0000005760", None],
        ],
        filas_previas=8,
    )
    crudo = lx.leer_seguimiento_frontera_excel(ruta)
    assert crudo["FechaOC"].to_list() == [date(2025, 1, 2), date(2025, 1, 2)]
    assert crudo["FechaPE"].to_list() == [date(2025, 1, 21), None]
    assert crudo["Cantidad"].to_list() == [15, 1]

    out = F.normalizar_seguimiento_frontera(crudo, para_transito=True)
    assert out["SucursalID"].to_list() == ["BRASIL 18", "DIEZ DE JULIO (2)"]
    assert out["Origen"].unique().to_list() == [F.ORIGEN_FRONTERA]


def test_seguimiento_importado_sin_sucursal_queda_desconocido(tmp_path):
    """El importado trae [Sucursal] en blanco: aporta al fallback global, no a una sucursal."""
    ruta = _crear_excel(
        tmp_path / "importado.xlsx",
        [
            "Producto", "Sucursal", "Razón Social Proveedor", "Motivo Compra",
            "Fecha Orden de Compra", "N° Orden de Compra", "Cantidad",
            "Estado Documento Base", "Fecha Documento Base", "Fecha Documento Recepción",
            "Estado Documento Recepción", "Código Local",
        ],
        [
            ["102 190101001", None, "BEST CHOICE", "0", "14/01/2025", "00003457", 60,
             "Cerrado por sistema", "14/01/2025", "17/03/2025", "Cerrado por sistema",
             "CD REPUESTOS"],
        ],
        filas_previas=9,
    )
    crudo = lx.leer_seguimiento_importado_excel(ruta)
    out = F.normalizar_seguimiento_importado(crudo, para_transito=True)
    assert out["SucursalID"].to_list() == ["DESCONOCIDO"]
    assert out["Origen"].unique().to_list() == [F.ORIGEN_IMPORTADO]
    # La recepcion de la importacion hace de Fecha P/E para el lead time.
    lt = F.normalizar_seguimiento_importado(crudo, para_lead_time=True)
    assert lt["FechaPE"].to_list() == [date(2025, 3, 17)]


def test_seguimiento_nacional_mapea_codigo_de_local(tmp_path):
    ruta = _crear_excel(
        tmp_path / "nacional.xlsx",
        [
            "Producto", "Código Local", "Razón Social Proveedor", "Motivo Compra",
            "Fecha Orden de Compra", "N° Orden de Compra", "Cantidad",
            "Estado Orden de Compra", "Estado Documento Base", "Fecha Documento Base",
            "Fecha Documento P/E",
        ],
        [
            ["19 ABC", "SUC070", "FORD CHILE", "REPOSICION", "02/01/2025", "1", 4,
             "Pendiente", "Cerrado", "02/01/2025", "20/01/2025"],
            ["19 XYZ", "SUC280", "FORD CHILE", "REPOSICION", "03/01/2025", "2", 7,
             "Pendiente", "Cerrado", "03/01/2025", None],
        ],
        filas_previas=9,
    )
    out = F.normalizar_seguimiento(lx.leer_seguimiento_nacional_excel(ruta), para_transito=True)
    assert out["SucursalID"].to_list() == ["LINDEROS", "CD REPUESTOS"]
    assert out["Cantidad"].to_list() == [4, 7]


def test_union_de_los_tres_seguimientos_cuadra(tmp_path):
    """Aunque cada origen traiga columnas distintas, la UNION debe funcionar."""
    nac = _crear_excel(
        tmp_path / "n.xlsx",
        ["Producto", "Código Local", "Cantidad", "Fecha Orden de Compra"],
        [["P1", "SUC070", 1, "02/01/2025"]],
    )
    imp = _crear_excel(
        tmp_path / "i.xlsx",
        ["Producto", "Cantidad", "Fecha Orden de Compra"],
        [["P2", 2, "03/01/2025"]],
    )
    fro = _crear_excel(
        tmp_path / "f.xlsx",
        ["Producto", "Nombre Local", "Cantidad", "Fecha Documento Base"],
        [["P3", "LINDEROS", 3, "04/01/2025"]],
    )
    union = F.unir_seguimiento(
        F.normalizar_seguimiento(lx.leer_seguimiento_nacional_excel(nac), para_transito=True),
        F.normalizar_seguimiento_importado(lx.leer_seguimiento_importado_excel(imp), para_transito=True),
        F.normalizar_seguimiento_frontera(lx.leer_seguimiento_frontera_excel(fro), para_transito=True),
    )
    assert union.height == 3
    assert union["Origen"].to_list() == [
        F.ORIGEN_NACIONAL, F.ORIGEN_IMPORTADO, F.ORIGEN_FRONTERA
    ]


# --------------------------- ventas --------------------------- #
_ENCABEZADOS_VENTAS = [
    "Empresa", "Periodo", "tipoDocto", "Fecha", "Tipo-Venta", "Producto",
    "Cantidad", "tipoproducto", "SUCURSAL",
]


def test_ventas_traduce_el_vocabulario_del_respaldo(tmp_path):
    """El respaldo Excel usa `4Repuesto` y `08 TALCA`; el SQL usa `REPUESTOS` y `TALCA`.

    Sin esta traduccion el filtro de repuestos del conector no matchea nada y las
    ventas salen VACIAS (fallo real detectado contra el archivo 2024)."""
    ruta = _crear_excel(
        tmp_path / "2024.xlsx",
        _ENCABEZADOS_VENTAS,
        [
            ["E01", "202401", "FACTURA S/T", "2024-01-09 00:00:00", "VTA MESON",
             "80 JOCKEY", 3, "4Repuesto", "08 TALCA"],
            ["E01", "202401", "NC CLIENTE S/T", "2024-01-10 00:00:00", "VTA MESON",
             "80 JOCKEY", 2, "4Repuesto", "02 LINDEROS"],
            ["E01", "202401", "FACTURA S/T", "2024-01-11 00:00:00", "VTA MEC",
             "MO_FORD", 1, "1M.O.", "09 CHILLAN"],
            ["E01", "202401", "FACTURA S/T", "2024-01-12 00:00:00", "VTA MESON",
             "19 ABC", 4, "4Repuesto", "DIEZ DE JULIO (2)"],
        ],
        col_a_vacia=False,
    )
    crudo = lx.leer_ventas_excel(ruta)
    assert crudo["tipoproducto"].to_list() == ["REPUESTOS", "REPUESTOS", "1M.O.", "REPUESTOS"]
    # El prefijo de orden se quita; lo que ya viene canonico no se toca.
    assert crudo["SUCURSAL"].to_list() == ["TALCA", "LINDEROS", "CHILLAN", "DIEZ DE JULIO (2)"]
    assert crudo["Fecha"][0] == date(2024, 1, 9)

    out = F.normalizar_ventas_curifor(crudo)
    assert out.columns == ["Producto", "SUCURSAL", "TipoVenta", "Fecha", "CantidadAjustada", "Fuente"]
    assert out.height == 3  # la linea de mano de obra queda fuera
    # La nota de credito resta.
    assert out["CantidadAjustada"].to_list() == [3, -2, 4]
    assert out["Fuente"].unique().to_list() == ["Curifor"]


def test_ventas_concatena_varios_respaldos(tmp_path):
    """Los respaldos vienen partidos por ano y el motor los necesita juntos."""
    a = _crear_excel(
        tmp_path / "2023.xlsx", _ENCABEZADOS_VENTAS,
        [["E01", "202301", "FACTURA S/T", "2023-05-02 00:00:00", "VTA MESON",
          "P1", 1, "4Repuesto", "08 TALCA"]],
        col_a_vacia=False,
    )
    b = _crear_excel(
        tmp_path / "2024.xlsx", _ENCABEZADOS_VENTAS,
        [["E01", "202401", "FACTURA S/T", "2024-05-02 00:00:00", "VTA MESON",
          "P2", 2, "4Repuesto", "08 TALCA"]],
        col_a_vacia=False,
    )
    juntas = lx.leer_ventas_excel([a, b])
    assert juntas.height == 2
    assert sorted(juntas["Producto"].to_list()) == ["P1", "P2"]


def test_ventas_esquema_identico_al_golden_del_modelo(tmp_path):
    """El contrato con el motor: mismas columnas y tipos que `ventas_12m.csv`."""
    ruta = _crear_excel(
        tmp_path / "2024.xlsx", _ENCABEZADOS_VENTAS,
        [["E01", "202401", "FACTURA S/T", "2024-01-09 00:00:00", "VTA MESON",
          "80 JOCKEY", 3, "4Repuesto", "08 TALCA"]],
        col_a_vacia=False,
    )
    out = F.normalizar_ventas_curifor(lx.leer_ventas_excel(ruta))
    esperado = {
        "Producto": pl.Utf8, "SUCURSAL": pl.Utf8, "TipoVenta": pl.Utf8,
        "Fecha": pl.Date, "CantidadAjustada": pl.Int64, "Fuente": pl.Utf8,
    }
    assert dict(out.schema) == esperado
