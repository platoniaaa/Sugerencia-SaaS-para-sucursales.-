"""Fuentes de datos en modo `activa`: el motor lee lo que dice la plataforma.

Tres conductas cambian a proposito al activar, y solo al activar:

1. Una fuente obligatoria que falta, o cuya carpeta este PC no tiene, FRENA la
   publicacion. Hoy pasa en silencio: un archivo que falta se salta, y si faltan
   los tres seguimientos el motor usa la copia congelada del 10-07.
2. Los dos stocks y el seguimiento nacional no pueden llegar vacios ni con menos
   del 60 % de las filas de la corrida anterior.
3. Dos fuentes que se leen no pueden elegir el mismo archivo.

Y nada vuelve a buscarse con el .env: lo que la configuracion no encuentra falta.
"""
import os
import time
from datetime import date, timedelta

from conftest import escribir_stock, escribir_xlsx, fuente_de, semilla, CABECERA_VENTAS

from src.jobs import correr_motor_real as job
from src.motor import fuentes_reales


def _leer_stocks():
    """Lo que hace `construir_csv` con los stocks: leerlos con el lector real, que
    anota las filas en `LECTURAS`."""
    fuentes_reales.leer_stock(job._buscar("stock_bodegas"))
    fuentes_reales.leer_stock(job._buscar("stock_bodegas_frontera"))


def _envejecer(ruta, dias_corridos):
    t = time.time() - dias_corridos * 86400
    os.utime(ruta, (t, t))


def test_en_activa_se_lee_lo_que_dice_la_plataforma(arbol, plataforma, correr):
    """El ensayo de la tanda 1: el stock desde SharePoint, aunque la copia local
    sea mas nueva."""
    cfg = semilla("activa")
    fuente_de(cfg, "stock_bodegas")["ubicaciones"] = [
        {"carpeta": "databi_datos", "subcarpeta": "", "recursiva": False}]
    plataforma.config = cfg

    r = correr()

    assert r.codigo == 0 and len(r.enviados) == 1
    assert r.lecturas["stock_bodegas"] == ("Stock bodegas.xlsx", b"stock de sharepoint")
    fin = plataforma.reportes[-1]
    assert (fin["reporte"]["modo"], fin["reporte"]["resolucion"]) == ("activa", "plataforma")
    assert fin["config_version"] == 1


def test_una_obligatoria_que_falta_frena_con_motivo(arbol, plataforma, correr):
    cfg = semilla("activa")
    fuente_de(cfg, "mix_reemplazos")["incluye"] = ["*no existe*"]
    plataforma.config = cfg

    r = correr()

    assert r.codigo == 1 and r.enviados == []
    fin = plataforma.reportes[-1]
    assert fin["resultado"] == "frenada"
    assert "Falta el archivo de Mix de reemplazos" in fin["motivo"]
    assert fin["reporte"]["fuentes"]["mix_reemplazos"]["hecho"] == "falta"
    # La incidencia de siempre (`_fallar` -> `avisar_falla`), con el motivo claro.
    (motivo, detalle), = r.incidencias
    assert "faltan archivos" in motivo and "Mix de reemplazos" in detalle


def test_si_este_pc_no_tiene_la_carpeta_frena(arbol, plataforma, correr):
    cfg = semilla("activa")
    cfg["carpetas"].append({
        "clave": "motor_sp", "nombre": "Data BI › Motor", "tipo": "sharepoint",
        "params": {"nombre_atajo": "Abastecimiento y Logística-Data BI - Motor"},
        "rutas_por_pc": {}, "activa": True})
    fuente_de(cfg, "seguimiento_curifor_importado")["ubicaciones"] = [
        {"carpeta": "motor_sp", "subcarpeta": "", "recursiva": False}]
    plataforma.config = cfg

    r = correr()

    fin = plataforma.reportes[-1]
    assert r.codigo == 1 and r.enviados == []
    assert "Este PC no tiene la carpeta Data BI › Motor" in fin["motivo"]
    assert fin["reporte"]["fuentes"]["seguimiento_curifor_importado"]["hecho"] == "carpeta_no_encontrada"
    carpetas = {c["clave"]: c for c in fin["reporte"]["carpetas"]}
    assert carpetas["motor_sp"]["existe"] is False


def test_una_opcional_que_falta_no_frena_ni_se_busca_en_el_env(arbol, plataforma, correr):
    cfg = semilla("activa")
    fuente_de(cfg, "lista_erp")["incluye"] = ["*no existe*"]
    plataforma.config = cfg

    r = correr()

    assert r.codigo == 0 and len(r.enviados) == 1
    # Esta en la carpeta del .env, pero la configuracion manda: falta.
    assert arbol.archivos["lista_erp"].exists()
    assert r.lecturas["lista_erp"] is None


def test_un_archivo_con_el_anio_que_queda_sin_fuente_cae_en_ventas_y_frena(arbol, plataforma, correr):
    """El riesgo de siempre del descarte: si un cambio de patrones deja sin fuente
    un archivo con el ano en el nombre, pasa a ser candidato a respaldo de venta.
    En `activa` frena con un motivo que nombra el archivo (hoy reventaba igual,
    sin decir cual era)."""
    cfg = semilla("activa")
    fuente_de(cfg, "vigentes_ford")["incluye"] = ["*no existe*"]
    plataforma.config = cfg

    r = correr()

    fin = plataforma.reportes[-1]
    assert r.codigo == 1 and r.enviados == []
    assert "No se pudo abrir 'Vigentes ford curifor_20260928_resultado.xlsx'" in fin["motivo"]
    assert fin["reporte"]["fuentes"]["ventas"]["hecho"] == "error_lectura"


def test_una_fuente_desactivada_no_frena_y_sus_archivos_no_caen_en_ventas(arbol, plataforma, correr):
    """"Activa" desmarcado en el panel: el motor no la lee, asi que tampoco puede
    frenar por ella (el panel la muestra gris, "el motor no la lee"). Y sus
    archivos siguen reconocidos: el mix lleva el ano en el nombre ("BASE NUEVO MIX
    2026_1.xlsx") y, sin su patron, se probaba como respaldo de venta."""
    cfg = semilla("activa")
    for clave in ("seguimiento_frontera", "mix_reemplazos", "vigentes_ford"):
        fuente_de(cfg, clave)["activa"] = False
    plataforma.config = cfg

    r = correr()

    fin = plataforma.reportes[-1]
    assert (r.codigo, fin["resultado"], len(r.enviados)) == (0, "ok", 1)
    assert r.lecturas["mix_reemplazos"] is None and r.lecturas["seguimiento_frontera"] is None
    assert [n for n, _ in r.lecturas["ventas"]] == [p.name for p in arbol.ventas]
    assert fin["reporte"]["fuentes"]["mix_reemplazos"]["hecho"] == "desactivada"
    assert fin["reporte"]["fuentes"]["ventas"]["hecho"] == "encontrado"


def test_en_prueba_una_fuente_desactivada_no_dice_que_frenaria(arbol, plataforma, correr):
    cfg = semilla("prueba")
    fuente_de(cfg, "mix_reemplazos")["activa"] = False
    plataforma.config = cfg

    r = correr()

    fuentes = plataforma.reportes[-1]["reporte"]["fuentes"]
    assert r.codigo == 0
    assert fuentes["mix_reemplazos"]["prueba"]["hecho"] == "desactivada"
    assert fuentes["mix_reemplazos"]["prueba"]["frenaria"] is None
    # Los respaldos de la plataforma no se confunden con el mix.
    assert fuentes["ventas"]["prueba"]["resultado"] == "coincide"
    assert fuentes["ventas"]["prueba"]["frenaria"] is None


def test_en_prueba_una_obligatoria_que_falta_no_frena(arbol, plataforma, correr):
    cfg = semilla("prueba")
    fuente_de(cfg, "mix_reemplazos")["incluye"] = ["*no existe*"]
    plataforma.config = cfg

    r = correr()

    assert r.codigo == 0 and len(r.enviados) == 1
    prueba = plataforma.reportes[-1]["reporte"]["fuentes"]["mix_reemplazos"]["prueba"]
    assert prueba["frenaria"] == "Falta el archivo de Mix de reemplazos"


# --- archivo vacio o incompleto -------------------------------------------------------


def _con_stocks(arbol, n_curifor, n_frontera=10):
    escribir_stock(arbol.archivos["stock_bodegas"], n_curifor)
    escribir_stock(arbol.archivos["stock_bodegas_frontera"], n_frontera)


def test_el_stock_con_0_filas_frena(arbol, plataforma, correr):
    _con_stocks(arbol, 0)
    plataforma.config = semilla("activa")

    r = correr(al_construir=_leer_stocks)

    fin = plataforma.reportes[-1]
    assert r.codigo == 1 and r.enviados == []
    assert fin["resultado"] == "frenada"
    assert fin["motivo"].startswith("Un archivo llegó vacío o incompleto")
    assert "Stock bodegas Curifor: llegó con 0 filas" in fin["motivo"]
    assert fin["reporte"]["fuentes"]["stock_bodegas"]["filas"] == 0


def test_el_stock_que_cae_a_la_mitad_frena(arbol, plataforma, correr):
    _con_stocks(arbol, 50)
    cfg = semilla("activa")
    cfg["anterior"] = {"stock_bodegas": {"sha256": "otro", "filas": 100,
                                         "modificado_en": "2026-10-15T09:34:00-03:00"}}
    plataforma.config = cfg

    r = correr(al_construir=_leer_stocks)

    assert r.codigo == 1 and r.enviados == []
    assert "llegó con 50 filas y la corrida anterior traía 100" in plataforma.reportes[-1]["motivo"]


def test_el_stock_con_70_por_ciento_de_las_filas_pasa(arbol, plataforma, correr):
    _con_stocks(arbol, 70)
    cfg = semilla("activa")
    cfg["anterior"] = {"stock_bodegas": {"sha256": "otro", "filas": 100}}
    plataforma.config = cfg

    r = correr(al_construir=_leer_stocks)

    assert r.codigo == 0 and len(r.enviados) == 1
    assert plataforma.reportes[-1]["reporte"]["fuentes"]["stock_bodegas"]["filas"] == 70


def test_la_guarda_de_filas_es_solo_de_activa(arbol, plataforma, correr):
    _con_stocks(arbol, 0)
    plataforma.config = semilla("prueba")

    r = correr(al_construir=_leer_stocks)

    assert r.codigo == 0 and len(r.enviados) == 1


# --- mismo archivo, ventas, plazos -------------------------------------------------


def test_dos_fuentes_con_el_mismo_archivo_frenan(arbol, plataforma, correr):
    cfg = semilla("activa")
    fuente_de(cfg, "precios_gildemeister").update(incluye=["*precio*ford*"], excluye=[])
    plataforma.config = cfg

    r = correr()

    assert r.codigo == 1 and r.enviados == []
    assert ("El archivo Lista de precio ford.xlsx lo eligieron dos fuentes: Lista de precios Ford "
            "y Lista de precios Gildemeister") in plataforma.reportes[-1]["motivo"]


def test_por_descarte_corre_sobre_las_ubicaciones_de_ventas(arbol, plataforma, correr):
    """La tanda 2: los respaldos en una carpeta propia, no en `MOTOR_CRUDOS_DIR`."""
    anio = date.today().year
    propia = arbol.od / "Documentos" / "Respaldos de venta"
    escribir_xlsx(propia / f"{anio} (7).xlsx", CABECERA_VENTAS)
    cfg = semilla("activa")
    cfg["carpetas"].append({"clave": "respaldos", "nombre": "Respaldos de venta",
                            "tipo": "onedrive", "params": {"ruta": "Documentos/Respaldos de venta"},
                            "rutas_por_pc": {}, "activa": True})
    fuente_de(cfg, "ventas")["ubicaciones"] = [
        {"carpeta": "respaldos", "subcarpeta": "", "recursiva": True}]
    plataforma.config = cfg

    r = correr()

    assert r.codigo == 0
    assert [n for n, _ in r.lecturas["ventas"]] == [f"{anio} (7).xlsx"]


def test_los_plazos_salen_de_la_configuracion(arbol, plataforma, correr):
    # Una semana: 5 dias habiles. Con el plazo de hoy (2) frenaria.
    for p in (arbol.archivos["stock_bodegas"], arbol.stock_sp):
        _envejecer(p, 7)
    cfg = semilla("activa")
    fuente_de(cfg, "stock_bodegas")["frecuencia_dias"] = 5
    plataforma.config = cfg

    assert correr().codigo == 0

    # Y al reves: un plazo que la configuracion acorta, frena.
    fuente_de(cfg, "lista_erp").update(frecuencia_dias=1, al_vencer="frena")
    _envejecer(arbol.archivos["lista_erp"], 7)
    plataforma.config = cfg
    r = correr()
    assert r.codigo == 1
    assert "lista_erp.xlsx: 5 dias habiles (se espera al dia cada 1)" in plataforma.reportes[-1]["motivo"]

    # Si solo avisa, no frena.
    fuente_de(cfg, "lista_erp")["al_vencer"] = "avisa"
    plataforma.config = cfg
    assert correr().codigo == 0


def test_el_plazo_de_ventas_se_mide_con_el_respaldo_mas_nuevo(arbol, plataforma, correr):
    """Ventas trae dos archivos: el respaldo del ano pasado no se vuelve a tocar.
    El plazo se mide con el mas nuevo, igual que el panel ("Al día"); con el
    primero en orden de nombre, la corrida frenaba todos los dias."""
    cfg = semilla("activa")
    fuente_de(cfg, "ventas")["frecuencia_dias"] = 30
    plataforma.config = cfg
    _envejecer(arbol.ventas[0], 200)       # "<ano-1> (4).xlsx"

    r = correr()

    fin = plataforma.reportes[-1]
    assert (r.codigo, fin["resultado"]) == (0, "ok")
    assert fin["reporte"]["fuentes"]["ventas"]["edad_dias_habiles"] == 0

    # Si el mas nuevo tambien se atrasa, frena y nombra ese.
    _envejecer(arbol.ventas[1], 70)        # 10 semanas: 50 dias habiles
    r = correr()
    assert r.codigo == 1
    assert (f"{arbol.ventas[1].name}: 50 dias habiles (se espera al dia cada 30)"
            in plataforma.reportes[-1]["motivo"])


def test_en_prueba_el_plazo_de_ventas_tambien_mira_el_mas_nuevo(arbol, plataforma, correr):
    cfg = semilla("prueba")
    fuente_de(cfg, "ventas")["frecuencia_dias"] = 30
    plataforma.config = cfg
    _envejecer(arbol.ventas[0], 200)

    correr()

    ventas = plataforma.reportes[-1]["reporte"]["fuentes"]["ventas"]
    assert ventas["prueba"]["frenaria"] is None
    assert ventas["edad_dias_habiles"] == 0


def test_la_fecha_de_la_semana_pasada_da_5_dias_habiles():
    """El supuesto de arriba: una semana corrida son 5 dias habiles, siempre."""
    hoy = date.today()
    assert job.dias_habiles(hoy - timedelta(days=7), hoy) == 5
