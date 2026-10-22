"""Que fuente le toca HOY a cada archivo real de las dos carpetas del motor.

Es la red de seguridad de "Fuentes de datos": la configuracion pasa del .env a la
plataforma, y la semilla tiene que elegir EXACTAMENTE lo mismo que hoy. Si un
cambio de patrones, de `listar()` o de la semilla mueve un solo archivo de
fuente, este test lo dice antes de que lo diga la corrida de las 09:30.

Los nombres son el escaneo del 16-10-2026 de las dos carpetas del .env del PC
del motor: 37 en MOTOR_CRUDOS_DIR (Documentos/Desarrollos/Bases de datos, se lee
con subcarpetas) y 21 en MOTOR_STOCK_DIR (el acceso directo a Data BI › Datos de
SharePoint, se lee solo el primer nivel y solo para el stock). Se copian como
archivos vacios a una carpeta temporal: para ELEGIR el motor mira el nombre, la
extension y la fecha. Solo los candidatos a respaldo de venta se abren (se les
mira el encabezado), y esos se escriben como Excel de verdad.

El resultado esperado se fijo corriendo el codigo de hoy (rama
arreglar-job-diario @ 4de6a2e), no a mano.
"""
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.jobs import correr_motor_real as job
from src.motor import config_fuentes as cf
from src.motor import fuentes

# Un respaldo de venta: "VENTAS". Lo que tiene el ano pero no la forma de un
# respaldo: "DESCARTADO". Lo que nadie lee: None. El resto, las fuentes que lo
# toman como candidato (con mas de una, la `lee` primero).
VENTAS, DESCARTADO = "VENTAS", "DESCARTADO"

CRUDOS = [
    ("Base mix reemplazos/BASE NUEVO MIX 2026_1.xlsx", ("mix_reemplazos",)),
    ("Lista ERP/lista_erp.xlsx", ("lista_erp",)),
    ("Lista de precios/Lista de precios curifor/LISTA DE PRECIOS.xlsx", ("catalogo",)),
    # La lista de Ford calza tambien con el cajon de proveedores: comparten
    # archivo una que se lee y una que solo se reconoce, y eso esta bien.
    ("Lista de precios/Lista de precios proveedores/Lista de precio ford al 28.07.2026.xlsx",
     ("precios_ford", "precios_proveedor")),
    ("Lista de precios/Lista de precios proveedores/Lista de precio ford.xlsx",
     ("precios_ford", "precios_proveedor")),
    ("Lista de precios/Lista de precios proveedores/Precios Gildemeister 20260728.xlsx",
     ("precios_gildemeister",)),
    ("Pautas de mantención/Pauta Mantencion OMODA JAECOO Julio 2025 (1).xlsb", None),
    ("Pautas de mantención/Pauta Mantención Hyundai 2026.xlsx", ("pautas_mantencion",)),
    ("Pautas de mantención/Pauta Servicio Ford - 17-06-2026.xlsm", ("pautas_mantencion",)),
    ("Pautas de mantención/Pauta de mantencion Baic Enero 2026.xlsx", ("pautas_mantencion",)),
    ("Pautas de mantención/Pauta de mantencion JAC Enero 2026.xlsx", ("pautas_mantencion",)),
    ("Pautas de mantención/Pauta de mantencion JIM Enero 2026.xlsx", ("pautas_mantencion",)),
    ("Pautas de mantención/Pauta de mantencion Mahindra Enero 2026.xlsx", ("pautas_mantencion",)),
    ("Pautas de mantención/Pauta de mantencion Shineray Enero 2026.xlsx", ("pautas_mantencion",)),
    ("Pautas de mantención/Pauta de mantencion Swm Enero 2026.xlsx", ("pautas_mantencion",)),
    ("Pautas de mantención/Pautas de mantencion GAC 2026.xlsx", ("pautas_mantencion",)),
    ("Pautas de mantención/pauta-ford-prepicking.js", None),
    # Las copias "desde 2020" compiten por fecha con las de la subcarpeta.
    ("Seguimiento Compras desde 2020.xlsx", ("seguimiento_curifor_nacional",)),
    ("Seguimiento Compras importado desde 2020.xlsx", ("seguimiento_curifor_importado",)),
    ("Seguimiento de Compras frontera desde 2020.xlsx", ("seguimiento_frontera",)),
    ("Seguimientos de compras/seguimiento_compras_frontera.xlsx", ("seguimiento_frontera",)),
    ("Seguimientos de compras/seguimiento_compras_importado.xlsx", ("seguimiento_curifor_importado",)),
    ("Seguimientos de compras/seguimiento_compras_nacional.xlsx", ("seguimiento_curifor_nacional",)),
    ("Vales de consumo/vales de consumo (2).xlsx", None),
    # Fuera de la ventana de 12 meses: no se leen.
    ("Ventas/2018 (2).xlsx", None),
    ("Ventas/2019 (1).xlsx", None),
    ("Ventas/2020 2023 (2).xlsx", None),
    ("Ventas/2024 (2).xlsx", None),
    ("Ventas/2025 (4).xlsx", VENTAS),
    ("Ventas/2026 (6).xlsx", VENTAS),
    # El reporte por canal que tumbo la corrida del 08-09-2026.
    ("Ventas/Lubricantes Motorcraft - Ventas mensuales por canal 2025-2026.xlsx", DESCARTADO),
    ("Ventas/vtas frontera.xlsx", ("ventas_frontera",)),
    ("Vigentes Ford/Vigentes ford curifor_20260822_resultado.xlsx", ("vigentes_ford",)),
    ("Vigentes Ford/Vigentes ford curifor_20260907_resultado.xlsx", ("vigentes_ford",)),
    ("Vigentes Ford/Vigentes ford curifor_20260928_resultado.xlsx", ("vigentes_ford",)),
    ("stock/STOCK_BODEGAS_CURIFOR.xlsx", ("stock_bodegas",)),
    ("stock/stock_frontera.xlsx", ("stock_bodegas_frontera",)),
]

# La carpeta de Data BI trae seguimientos y produccion post-venta que NO son del
# motor: calzan con los patrones, pero esta carpeta se lee solo para el stock.
DATABI = [
    ("Anteriores/Base productos.xlsx", None),
    ("Anteriores/Curifor Anteriores - Seguimiento de Compras.xlsx", None),
    ("Anteriores/Curifor Imp Anteriores - Seguimiento Compras.xlsx", None),
    ("Anteriores/Hist - Stock Curifor.xlsx", None),
    ("Anteriores/Hist - Stock Frontera.xlsx", None),
    ("Anteriores/Producción Mensual Post-Venta Curifor Anteriores.xlsx", None),
    ("Anteriores/Producción Mensual Post-Venta Frontera Anteriores.xlsx", None),
    ("Anteriores/Seguimiento de Compras Frontera Anteriores.xlsx", None),
    ("Anteriores/Seguimiento_Pendientes_0109.xlsx", None),
    ("Curifor - Producción Mensual Post-Venta.xlsx", None),
    ("Curifor - Seguimiento Compras Importado.xlsx", None),
    ("Curifor - Seguimiento Compras.xlsx", None),
    ("Dashboards actualizados BI/Abastecimiento.pbix", None),
    ("Dashboards actualizados BI/Informes de Gestión (1).pbix", None),
    ("Dashboards actualizados BI/Seguimiento ordenes de trabajo CURIFOR.pbix", None),
    ("Dashboards actualizados BI/Ventas Digitales.pbix", None),
    ("Frontera - Producción Mensual Post-Venta.xlsx", None),
    ("Frontera - Seguimiento de Compras.xlsx", None),
    ("Stock bodegas Frontera.xlsx", ("stock_bodegas_frontera",)),
    ("Stock bodegas.xlsx", ("stock_bodegas",)),
    ("desktop.ini", None),
]

CABECERA_VENTAS = ["Fecha", "Producto", "Cantidad", "tipoDocto", "tipoproducto", "SUCURSAL"]
HOY = date(2026, 10, 16)


def _xlsx(ruta: Path, cabeceras: list) -> None:
    wb = Workbook()
    wb.active.append(cabeceras)
    wb.save(ruta)


@pytest.fixture
def carpetas(tmp_path, monkeypatch):
    """Las dos carpetas del .env, dentro de un OneDrive de mentira, con los 58
    nombres. Cada archivo con una fecha distinta, para que el ganador por fecha no
    dependa del orden en que el sistema entrega los archivos."""
    import os

    od = tmp_path / "OneDrive - Org"
    crudos = od / "Documentos" / "Desarrollos" / "Bases de datos"
    databi = od / "Abastecimiento y Logística-Data BI - Datos"
    t = 1_790_000_000
    for raiz, lista in ((crudos, CRUDOS), (databi, DATABI)):
        for rel, esperado in lista:
            p = raiz / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if esperado == VENTAS:
                _xlsx(p, CABECERA_VENTAS)
            elif esperado == DESCARTADO:
                _xlsx(p, ["Canal", "Mes", "Litros", "Monto"])
            else:
                p.touch()
            t += 600
            os.utime(p, (t, t))
    monkeypatch.setenv("OneDriveCommercial", str(od))
    monkeypatch.setenv("COMPUTERNAME", "PC-MOTOR")
    monkeypatch.setattr(fuentes, "CRUDOS_DIRS", [crudos])
    monkeypatch.setattr(fuentes, "CRUDOS_DIR", crudos)
    monkeypatch.setattr(fuentes, "STOCK_DIRS", [databi])
    monkeypatch.setattr(job, "CRUDOS_DIR", crudos)
    job._AVISOS_FUENTES.clear()
    return crudos, databi


def _asignacion_de_hoy(crudos: Path, databi: Path) -> dict[Path, object]:
    """Lo que hace el codigo de siempre: `_candidatos` por fuente y la seleccion
    de respaldos de venta por descarte."""
    toma: dict[Path, list[str]] = {}
    for clave in fuentes.FUENTES:
        if clave == "ventas":
            continue
        for p in fuentes._candidatos(clave):
            toma.setdefault(p, []).append(clave)
    salida: dict[Path, object] = {p: tuple(c) for p, c in toma.items()}
    for p in job._archivos_de_ventas(job._fin_mes_cerrado(HOY)):
        salida[p] = VENTAS
    for aviso in job._AVISOS_FUENTES:
        nombre = aviso.split("'")[1]
        salida[next(p for p in crudos.rglob("*") if p.name == nombre)] = DESCARTADO
    return salida


def test_son_los_58_nombres_del_escaneo():
    assert len(CRUDOS) == 37 and len(DATABI) == 21
    assert len({r for r, _ in CRUDOS}) == 37 and len({r for r, _ in DATABI}) == 21


def test_cada_archivo_real_va_a_la_fuente_que_le_toca_hoy(carpetas):
    crudos, databi = carpetas
    hoy = _asignacion_de_hoy(crudos, databi)

    distintos = []
    for raiz, lista in ((crudos, CRUDOS), (databi, DATABI)):
        for rel, esperado in lista:
            obtenido = hoy.get(raiz / rel)
            if obtenido != esperado:
                distintos.append(f"{rel}: se esperaba {esperado}, hoy da {obtenido}")
    assert distintos == []


def test_los_respaldos_de_venta_son_los_del_log(carpetas):
    """La misma linea que `logs/motor_2026-10-16.log`."""
    nombres = [p.name for p in job._archivos_de_ventas(job._fin_mes_cerrado(HOY))]

    assert nombres == ["2025 (4).xlsx", "2026 (6).xlsx"]


def test_la_semilla_elige_lo_mismo_que_el_env(carpetas, monkeypatch):
    """config_efectiva() -> semilla -> la misma resolucion que hoy, fuente por
    fuente: los mismos candidatos, en el mismo orden, y el mismo ganador."""
    semilla = cf.leer_config(cf.config_efectiva())
    plataforma, _ = cf.resolver_config(semilla, HOY, "PC-MOTOR")
    env = cf.resolver_env(HOY)

    assert set(env) == set(fuentes.FUENTES)
    for clave in fuentes.FUENTES:
        a, b = env[clave], plataforma[clave]
        assert [x.ruta for x in b.candidatos] == [x.ruta for x in a.candidatos], clave
        assert [x.ruta for x in b.elegidos] == [x.ruta for x in a.elegidos], clave
        assert b.hecho == a.hecho, clave
    # Las 13 que se leen tienen archivo; de las 4 que solo se reconocen, hoy hay
    # pautas y listas de proveedor, pero no la salida de WINGS ni la de sucursales.
    assert {c for c, e in env.items() if e.hecho == "falta"} == {"lista_new_wings", "dim_sucursal"}
    comparacion = cf.comparar(env, plataforma, HOY)
    lee = cf.claves_que_se_leen()
    assert len(lee) == 13
    assert all(comparacion[c]["resultado"] == "coincide" for c in lee)


def test_la_semilla_es_la_de_la_especificacion(carpetas):
    """La tabla "Semilla esperada" de §3.5 de la especificacion."""
    cfg = cf.config_efectiva("PC-MOTOR")
    carpetas_ = {c["clave"]: c for c in cfg["carpetas"]}
    fuentes_ = {f["clave"]: f for f in cfg["fuentes"]}

    assert carpetas_["bases_de_datos"]["tipo"] == "onedrive"
    assert carpetas_["bases_de_datos"]["params"]["ruta"] == "Documentos/Desarrollos/Bases de datos"
    assert carpetas_["databi_datos"]["tipo"] == "sharepoint"
    assert (carpetas_["databi_datos"]["params"]["nombre_atajo"]
            == "Abastecimiento y Logística-Data BI - Datos")
    # Nada de la ruta absoluta con el usuario de Windows.
    assert str(carpetas[0]) not in str(cfg)

    for clave in ("stock_bodegas", "stock_bodegas_frontera"):
        assert fuentes_[clave]["ubicaciones"] == [
            {"carpeta": "bases_de_datos", "subcarpeta": "", "recursiva": True},
            {"carpeta": "databi_datos", "subcarpeta": "", "recursiva": False},
        ]
    assert fuentes_["ventas"]["modo"] == "por_descarte"
    assert fuentes_["ventas"]["extensiones"] == [".xlsx"]
    assert fuentes_["ventas"]["ubicaciones"] == [
        {"carpeta": "bases_de_datos", "subcarpeta": "", "recursiva": True}]

    plazos = {c: (f["frecuencia_dias"], f["al_vencer"]) for c, f in fuentes_.items()}
    assert plazos["stock_bodegas"] == plazos["stock_bodegas_frontera"] == (2, "frena")
    assert plazos["seguimiento_curifor_nacional"] == (2, "frena")
    assert plazos["seguimiento_curifor_importado"] == plazos["seguimiento_frontera"] == (7, "frena")
    assert plazos["mix_reemplazos"] == plazos["catalogo"] == (120, "frena")
    assert plazos["ventas_frontera"] == (35, "avisa")
    assert plazos["lista_erp"] == (10, "avisa")
    for clave in ("precios_ford", "precios_gildemeister", "vigentes_ford", "ventas"):
        assert plazos[clave][0] is None

    obligatorias = {c for c, f in fuentes_.items() if f["obligatoria"]}
    assert obligatorias == {
        "stock_bodegas", "stock_bodegas_frontera", "ventas", "seguimiento_curifor_nacional",
        "seguimiento_curifor_importado", "seguimiento_frontera", "mix_reemplazos", "catalogo"}

    cat = cfg["catalogo"]
    assert {c for c, d in cat.items() if d["requerida"]} == {
        "stock_bodegas", "stock_bodegas_frontera", "ventas"}
    assert {c for c, d in cat.items() if d["uso"] == "reconoce"} == {
        "lista_new_wings", "precios_proveedor", "dim_sucursal", "pautas_mantencion"}
    assert {c for c, d in cat.items() if d["frecuencia_max"]} == {
        "stock_bodegas", "stock_bodegas_frontera", "seguimiento_curifor_nacional"}
    assert all(cat[c]["frecuencia_max"] == 5 and cat[c]["al_vencer_fijo"] == "frena"
               for c in ("stock_bodegas", "stock_bodegas_frontera", "seguimiento_curifor_nacional"))
    assert all(d["efecto_si_falta"] for d in cat.values())
