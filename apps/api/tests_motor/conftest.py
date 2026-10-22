"""Hace importable `src.motor` al correr `pytest tests_motor` desde apps/api,
sin depender de PYTHONPATH ni de las dependencias de la plataforma (fastapi, etc.).
"""
import sys
from pathlib import Path

import pytest

# apps/api/ es el padre de tests_motor/; ahí vive el paquete `src`.
_API_DIR = Path(__file__).resolve().parents[1]
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))


@pytest.fixture(autouse=True)
def _fuentes_aisladas(tmp_path_factory, monkeypatch):
    """Ningun test toca la configuracion de fuentes de este PC ni la plataforma.

    - `MOTOR_FUENTES=env`: el kill switch. Una corrida que se cuele por un test
      no le pregunta nada a la plataforma; el test que prueba la cascada lo saca.
    - La cache, las copias de la corrida, los reportes pendientes y la corrida en
      curso van a una carpeta temporal: en el PC del motor `data/` es la de verdad.
    - Sin esperas: un archivo recien creado parece "bajando de OneDrive".
    - El GET de la configuracion y el POST del reporte contestan "sin
      credenciales". En el PC del motor el .env SI las tiene: sin esto, un test
      que corre `job.run` llegaria a la plataforma de verdad (y `_token` lo
      cortaria con `LlamadaRealDesdeUnTest`).
    """
    from src.motor import config_fuentes as cf
    from src.motor import fuentes, lectores_excel

    def _sin_plataforma(*a, **k):
        raise cf._SinPlataforma()

    base = tmp_path_factory.mktemp("fuentes")
    monkeypatch.setattr(cf, "obtener_config_fuentes", lambda: None)
    monkeypatch.setattr(cf, "_post_reporte", _sin_plataforma)
    monkeypatch.setenv("MOTOR_FUENTES", "env")
    monkeypatch.setattr(cf, "CACHE", base / "fuentes_config_cache.json")
    monkeypatch.setattr(cf, "CORRIDA_DIR", base / "corrida")
    monkeypatch.setattr(cf, "PENDIENTES_DIR", base / "reportes_pendientes")
    monkeypatch.setattr(cf, "EN_CURSO", base / "corrida_en_curso.json")
    monkeypatch.setattr(cf, "RECIENTE_SEG", 0)
    monkeypatch.setattr(cf, "_dormir", lambda s: None)
    monkeypatch.setattr(cf, "_onedrive_corriendo", lambda: None)
    yield
    fuentes.soltar_manifiesto()
    lectores_excel.LECTURAS.clear()


# --- Fuentes de datos: un OneDrive de mentira y una plataforma de mentira -------

CABECERA_VENTAS = ["Fecha", "Producto", "Cantidad", "tipoDocto", "tipoproducto", "SUCURSAL"]


def escribir_xlsx(ruta, cabeceras, filas=()):
    from openpyxl import Workbook

    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.append(cabeceras)
    for f in filas:
        ws.append(f)
    wb.save(ruta)
    return ruta


def escribir_stock(ruta, n):
    """Un Excel de stock como el del ERP, con `n` filas."""
    return escribir_xlsx(ruta, ["Producto", "Bodega", "Stock", "Costo"],
                         [[f"17 P{i}", "LINDEROS", 1, "100,0"] for i in range(n)])


@pytest.fixture
def arbol(tmp_path, monkeypatch):
    """Las dos carpetas del .env dentro de un OneDrive de mentira, con un archivo
    por cada fuente que se lee, como estan hoy en el PC del motor."""
    import os
    import time
    from datetime import date
    from types import SimpleNamespace

    from src.jobs import correr_motor_real as job
    from src.motor import fuentes

    od = tmp_path / "OneDrive - Org"
    crudos = od / "Documentos" / "Desarrollos" / "Bases de datos"
    databi = od / "Abastecimiento y Logística-Data BI - Datos"
    seg = crudos / "Seguimientos de compras"
    precios = crudos / "Lista de precios"
    archivos = {
        "stock_bodegas": crudos / "stock" / "STOCK_BODEGAS_CURIFOR.xlsx",
        "stock_bodegas_frontera": crudos / "stock" / "stock_frontera.xlsx",
        "seguimiento_curifor_nacional": seg / "seguimiento_compras_nacional.xlsx",
        "seguimiento_curifor_importado": seg / "seguimiento_compras_importado.xlsx",
        "seguimiento_frontera": seg / "seguimiento_compras_frontera.xlsx",
        "mix_reemplazos": crudos / "Base mix reemplazos" / "BASE NUEVO MIX 2026_1.xlsx",
        "catalogo": precios / "LISTA DE PRECIOS.xlsx",
        "ventas_frontera": crudos / "Ventas" / "vtas frontera.xlsx",
        "lista_erp": crudos / "Lista ERP" / "lista_erp.xlsx",
        "precios_ford": precios / "Lista de precio ford.xlsx",
        "precios_gildemeister": precios / "Precios Gildemeister 20260728.xlsx",
        "vigentes_ford": crudos / "Vigentes Ford" / "Vigentes ford curifor_20260928_resultado.xlsx",
    }
    for clave, p in archivos.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"{clave} v1".encode())
    anio = date.today().year
    ventas = [escribir_xlsx(crudos / "Ventas" / f"{anio - 1} (4).xlsx", CABECERA_VENTAS),
              escribir_xlsx(crudos / "Ventas" / f"{anio} (6).xlsx", CABECERA_VENTAS)]
    motorcraft = escribir_xlsx(
        crudos / "Ventas" / f"Lubricantes Motorcraft - Ventas mensuales por canal {anio}.xlsx",
        ["Canal", "Mes", "Litros"])
    # El stock de SharePoint compite con la copia local; hoy gana el mas nuevo.
    databi.mkdir(parents=True, exist_ok=True)
    stock_sp = databi / "Stock bodegas.xlsx"
    stock_sp.write_bytes(b"stock de sharepoint")
    viejo = time.time() - 3600
    os.utime(stock_sp, (viejo, viejo))
    (databi / "Curifor - Seguimiento Compras.xlsx").write_bytes(b"no es del motor")

    monkeypatch.setenv("OneDriveCommercial", str(od))
    monkeypatch.setenv("COMPUTERNAME", "PC-MOTOR")
    monkeypatch.setattr(fuentes, "CRUDOS_DIRS", [crudos])
    monkeypatch.setattr(fuentes, "CRUDOS_DIR", crudos)
    monkeypatch.setattr(fuentes, "STOCK_DIRS", [databi])
    monkeypatch.setattr(job, "CRUDOS_DIR", crudos)
    job._AVISOS_FUENTES.clear()
    return SimpleNamespace(od=od, crudos=crudos, databi=databi, archivos=archivos,
                           ventas=ventas, motorcraft=motorcraft, stock_sp=stock_sp)


@pytest.fixture
def plataforma(monkeypatch):
    """GET /config devuelve `config` (o lanza `error`); POST /reporte guarda en
    `reportes` (o lanza `falla_post`). Saca el kill switch del fixture de arriba."""
    import json
    from types import SimpleNamespace

    from src.motor import config_fuentes as cf

    estado = SimpleNamespace(config=None, error=None, falla_post=None, reportes=[], pedidas=0)

    def obtener():
        estado.pedidas += 1
        if estado.error is not None:
            raise estado.error
        return estado.config

    def post(payload):
        if estado.falla_post is not None:
            raise estado.falla_post
        # Ida y vuelta por JSON: lo que no se pueda serializar revienta aca.
        estado.reportes.append(json.loads(json.dumps(payload)))

    monkeypatch.delenv("MOTOR_FUENTES", raising=False)
    monkeypatch.setattr(cf, "obtener_config_fuentes", obtener)
    monkeypatch.setattr(cf, "_post_reporte", post)
    return estado


def semilla(modo="prueba", **cambios):
    """La configuracion que sembraria la plataforma desde este PC."""
    from src.motor import config_fuentes as cf

    cfg = cf.config_efectiva("PC-MOTOR")
    cfg.update(modo=modo, version=1, hash="h1", anterior={}, **cambios)
    return cfg


def fuente_de(cfg, clave):
    return next(f for f in cfg["fuentes"] if f["clave"] == clave)


@pytest.fixture
def correr(tmp_path, monkeypatch):
    """Corre `job.run` entero con el calculo y la publicacion de mentira.

    `construir_csv` lee lo que leeria el de verdad -cada fuente con `_buscar`, los
    respaldos con `_archivos_de_ventas`- y lo anota en `lecturas`: nombre y
    contenido de cada archivo. Asi se compara QUE se leyo, que es lo que define
    lo que se publica."""
    import csv
    from datetime import date
    from types import SimpleNamespace

    from src.jobs import correr_motor_real as job
    from src.motor import config_fuentes as cf

    preparar_de_verdad = job.preparar_fuentes

    def _correr(oficial=True, ignorar_frescura=False, al_construir=None, sin_modulo=False):
        r = SimpleNamespace(lecturas={}, enviados=[], incidencias=[], codigo=None,
                            manifiestos=[])

        def preparar(corrida):
            m = preparar_de_verdad(corrida)
            r.manifiestos.append(m)
            return m

        # Sin el modulo es "hoy": nada de manifiesto, cada paso busca su archivo.
        monkeypatch.setattr(job, "preparar_fuentes",
                            (lambda corrida: None) if sin_modulo else preparar)

        def construir_csv(hoy=None):
            for clave in cf.claves_que_se_leen():
                if clave == "ventas":
                    continue
                p = job._buscar(clave, obligatorio=False)
                r.lecturas[clave] = None if p is None else (p.name, p.read_bytes())
            r.lecturas["ventas"] = [
                (p.name, p.read_bytes())
                for p in job._archivos_de_ventas(job._fin_mes_cerrado(date.today()))]
            if al_construir is not None:
                al_construir()
            ruta = tmp_path / "sugerido_motor.csv"
            with open(ruta, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["Producto", "Periodo Ultimo Mes", "Venta Mes 01"])
                w.writeheader()
                w.writerow({"Producto": "17 P1", "Periodo Ultimo Mes": "202609", "Venta Mes 01": 5})
            return ruta

        monkeypatch.setattr(job, "construir_csv", construir_csv)
        monkeypatch.setattr(job, "enviar", lambda p, oficial=False: r.enviados.append(p.read_bytes())
                            or {"filas_cargadas": 1, "advertencias": [], "paridad_pct": 100,
                                "filas_comunes": 1, "filas_solo_motor": 0, "filas_solo_bi": 0})
        monkeypatch.setattr(job, "avisar_falla", lambda m, d="": r.incidencias.append((m, d)) or False)
        monkeypatch.setattr(job, "CANDADO", tmp_path / "motor.lock")
        # Toda la publicacion apagada, salvo el reporte de fuentes (que va a la
        # plataforma de mentira por `config_fuentes._post_reporte`).
        apagar = {n for n in dir(job)
                  if n.startswith(("publicar_", "obtener_config"))
                  and n not in ("publicar_con_reintentos", "publicar_reporte_fuentes",
                                "publicar_reportes_pendientes")}
        apagar |= {"recargar_instock", "recalcular_precios"}
        for nombre in sorted(apagar):
            monkeypatch.setattr(job, nombre, lambda *a, **k: None)
        r.codigo = job.run(oficial=oficial, ignorar_frescura=ignorar_frescura)
        return r

    return _correr
