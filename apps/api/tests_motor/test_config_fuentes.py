"""Fuentes de datos: la configuracion que el motor pide a la plataforma.

La regla de oro es que el motor NUNCA deja de correr por culpa de este modulo, y
que en modo `sin_configurar` y `prueba` publica EXACTAMENTE lo mismo que hoy.
Lo que estos tests cuidan:

1. `listar()` es la unica que recorre carpetas y deja fuera lo de Excel abierto.
2. La cascada: plataforma -> configuracion guardada -> .env, sin que un error de
   archivo la active y sin tragarse `LlamadaRealDesdeUnTest`.
3. El manifiesto: una copia por corrida, que no cambia si OneDrive reemplaza el
   original a mitad, con la misma huella del feed del ERP.
4. Que en `sin_configurar` y `prueba` se lee lo mismo que sin el modulo.
5. El PC titular y el reporte, que nunca rompe la corrida.
"""
import json
import os
import time
from datetime import date

import pytest
from conftest import escribir_xlsx, fuente_de, semilla

from src.jobs import correr_motor_real as job
from src.motor import config_fuentes as cf
from src.motor import fuentes, lectores_excel
from src.motor.config_fuentes import _post_reporte as POST_REAL
from src.motor.config_fuentes import obtener_config_fuentes as OBTENER_REAL


# --- listar ----------------------------------------------------------------------


def test_listar_deja_fuera_lo_de_excel_abierto_y_lo_que_no_es_planilla(tmp_path):
    for n in ("Stock bodegas.xlsx", "~$Stock bodegas.xlsx", "desktop.ini", "Ventas.pbix",
              "sub/seguimiento.csv", "sub/~$seguimiento.csv"):
        (tmp_path / n).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / n).write_bytes(b"x")

    todo = {p.relative_to(tmp_path).as_posix() for p in cf.listar(tmp_path)}
    arriba = {p.name for p in cf.listar(tmp_path, recursiva=False)}

    assert todo == {"Stock bodegas.xlsx", "sub/seguimiento.csv"}
    assert arriba == {"Stock bodegas.xlsx"}


def test_listar_marca_la_copia_en_conflicto_de_onedrive_sin_sacarla(tmp_path):
    """Hoy compite por fecha con el archivo bueno: se deja, pero se avisa."""
    (tmp_path / "Stock bodegas.xlsx").write_bytes(b"x")
    (tmp_path / "Stock bodegas-PC-MOTOR.xlsx").write_bytes(b"x")
    avisos = []

    nombres = {p.name for p in cf.listar(tmp_path, avisos=avisos, hostnames=["PC-MOTOR"])}

    assert nombres == {"Stock bodegas.xlsx", "Stock bodegas-PC-MOTOR.xlsx"}
    assert len(avisos) == 1 and "Stock bodegas-PC-MOTOR.xlsx" in avisos[0]


def test_listar_una_carpeta_que_no_existe_no_rompe(tmp_path):
    assert cf.listar(tmp_path / "sin sincronizar") == []


def test_los_tres_recorridos_de_hoy_pasan_por_listar():
    """`fuentes.py:234`, `:259` y `correr_motor_real.py:265`: ya no recorren por su cuenta."""
    import inspect

    for fn in (fuentes.archivos_crudos, fuentes.archivos_de_stock, cf.seleccion_de_ventas):
        assert "listar(" in inspect.getsource(fn)
    assert "rglob" not in inspect.getsource(job._archivos_de_ventas)


# --- .env con BOM ----------------------------------------------------------------


def test_el_env_con_bom_se_lee_desde_la_primera_linea(tmp_path, monkeypatch):
    """El .env de este PC parte con BOM. Con utf-8 a secas, la primera variable
    llegaba como '\\ufeffMOTOR_CRUDOS_DIR' y no calzaba con nada."""
    (tmp_path / ".env").write_text(
        "MOTOR_CRUDOS_DIR=C:\\datos\nPLATAFORMA_API_URL=http://plataforma.test\n",
        encoding="utf-8-sig")
    monkeypatch.setattr(fuentes, "_REPO_DIR", tmp_path)
    monkeypatch.delenv("MOTOR_CRUDOS_DIR", raising=False)

    assert (tmp_path / ".env").read_bytes().startswith(b"\xef\xbb\xbf")
    assert [str(p) for p in fuentes._carpetas_de("MOTOR_CRUDOS_DIR")] == ["C:\\datos"]

    (tmp_path / ".env").write_text("PLATAFORMA_API_URL=http://plataforma.test\n",
                                   encoding="utf-8-sig")
    assert job._leer_env() == {"PLATAFORMA_API_URL": "http://plataforma.test"}


@pytest.mark.parametrize("linea", ["MOTOR_FUENTES=env", "MOTOR_FUENTES = env",
                                   "MOTOR_FUENTES= env", "MOTOR_FUENTES =env"])
def test_el_kill_switch_se_lee_aunque_lleve_espacios(tmp_path, monkeypatch, linea):
    """En una emergencia alguien lo escribe a mano. Con espacios antes del '=' la
    tarea de las 09:30 no lo veia y seguia obedeciendo a la plataforma, mientras el
    agente (que lee el .env con '\\s*=\\s*') si lo veia."""
    monkeypatch.delenv("MOTOR_FUENTES", raising=False)
    (tmp_path / ".env").write_text("# motor\n" + linea + "\n", encoding="utf-8")
    monkeypatch.setattr(fuentes, "_REPO_DIR", tmp_path)

    assert cf._kill_switch() is True


def test_una_variable_que_empieza_igual_no_se_confunde(tmp_path, monkeypatch):
    monkeypatch.delenv("MOTOR_FUENTES", raising=False)
    (tmp_path / ".env").write_text("MOTOR_FUENTES_VIEJO=env\n", encoding="utf-8")
    monkeypatch.setattr(fuentes, "_REPO_DIR", tmp_path)

    assert fuentes._valor_env("MOTOR_FUENTES") is None


# --- cascada ----------------------------------------------------------------------


def _guardar_cache(cfg, cuando="2026-09-16T09:30:00-03:00"):
    cf.CACHE.parent.mkdir(parents=True, exist_ok=True)
    cf.CACHE.write_text(json.dumps({"guardada_en": cuando, "config": cfg}), encoding="utf-8")


def test_la_plataforma_responde_y_se_guarda_en_este_pc(arbol, plataforma):
    plataforma.config = semilla("prueba")

    cfg, origen, avisos, _ = cf.cargar_configuracion()

    assert (cfg.modo, origen) == ("prueba", "plataforma")
    assert json.loads(cf.CACHE.read_text(encoding="utf-8"))["config"]["modo"] == "prueba"


def test_plataforma_caida_usa_lo_guardado_aunque_tenga_30_dias(arbol, plataforma):
    _guardar_cache(semilla("activa"), "2026-09-16T09:30:00-03:00")
    plataforma.error = RuntimeError("502 Bad Gateway")

    cfg, origen, avisos, guardada = cf.cargar_configuracion()

    assert (cfg.modo, origen, guardada) == ("activa", "cache", "2026-09-16T09:30:00-03:00")
    assert any("502" in a for a in avisos)


def test_sin_configurar_en_la_plataforma_con_cache_activa_manda_la_cache(arbol, plataforma):
    """Si se movio o se vacio la base, la plataforma dice 'sin configurar': eso no
    puede apagar en silencio una configuracion que estaba activa."""
    _guardar_cache(semilla("activa"))
    plataforma.config = {"modo": "sin_configurar"}

    cfg, origen, _, _ = cf.cargar_configuracion()

    assert (cfg.modo, origen) == ("activa", "cache")
    # Y la cache no se pisa con el 'sin configurar'.
    assert json.loads(cf.CACHE.read_text(encoding="utf-8"))["config"]["modo"] == "activa"


def test_sin_cache_y_sin_plataforma_es_el_env(arbol, plataforma):
    plataforma.error = RuntimeError("ConnectError")

    cfg, origen, _, _ = cf.cargar_configuracion()

    assert (cfg, origen) == (None, "env")


@pytest.mark.parametrize("roto", [["no", "es", "objeto"], {"modo": "otro"},
                                  {"modo": "activa", "fuentes": [{"clave": "x", "modo": "raro"}]}])
def test_una_configuracion_invalida_pasa_a_la_cache_o_al_env(arbol, plataforma, roto):
    plataforma.config = roto

    cfg, origen, avisos, _ = cf.cargar_configuracion()
    assert (cfg, origen) == (None, "env")
    assert avisos

    _guardar_cache(semilla("prueba"))
    cfg, origen, _, _ = cf.cargar_configuracion()
    assert (cfg.modo, origen) == ("prueba", "cache")


def test_motor_fuentes_env_manda_y_ni_pregunta(arbol, plataforma, monkeypatch):
    monkeypatch.setenv("MOTOR_FUENTES", "env")
    plataforma.config = semilla("activa", pc_titular="OTRO-PC")

    cfg, origen, _, _ = cf.cargar_configuracion()

    assert (cfg, origen) == (None, "env")
    assert plataforma.pedidas == 0


def test_llamada_real_desde_un_test_atraviesa_la_cascada(arbol, plataforma):
    plataforma.error = job.LlamadaRealDesdeUnTest("un test intento entrar")

    with pytest.raises(job.LlamadaRealDesdeUnTest):
        cf.cargar_configuracion()


def test_un_error_de_archivo_no_activa_la_cascada(arbol, plataforma, monkeypatch):
    """Una huella que no se puede calcular o una copia sin permiso quedan como
    estado de esa fuente; la configuracion sigue siendo la de la plataforma."""
    plataforma.config = semilla("activa")

    def sin_permiso(p):
        if "STOCK_BODEGAS" in str(p):
            raise PermissionError("Acceso denegado")
        return "h"

    monkeypatch.setattr(cf, "sha256", sin_permiso)
    m = cf.preparar_fuentes(cf.nueva_corrida(oficial=True))

    assert (m.origen, m.resolucion) == ("plataforma", "plataforma")
    assert m.por_clave["stock_bodegas"].hecho == "error_lectura"
    assert "abierto o bloqueado" in m.por_clave["stock_bodegas"].mensaje
    assert "Acceso denegado" in m.por_clave["stock_bodegas"].detalle
    assert m.por_clave["stock_bodegas_frontera"].hecho == "encontrado"


def test_una_copia_sin_permiso_tampoco(arbol, plataforma, monkeypatch):
    import shutil

    plataforma.config = semilla("activa")
    original = shutil.copy2

    def copy2(a, b, *k, **kw):
        if "stock_frontera" in str(a):
            raise PermissionError("en uso por otro proceso")
        return original(a, b, *k, **kw)

    monkeypatch.setattr(shutil, "copy2", copy2)
    m = cf.preparar_fuentes(cf.nueva_corrida(oficial=True))

    f = m.por_clave["stock_bodegas_frontera"]
    assert m.origen == "plataforma"
    assert f.hecho == "error_lectura" and "en uso" in f.detalle
    assert f.mensaje == ("No se pudo copiar stock_frontera.xlsx: está abierto o bloqueado por "
                         "otro programa.")
    # Se sigue leyendo el original, como hoy: la lectura dira si de verdad no se puede.
    assert f.copias == (arbol.archivos["stock_bodegas_frontera"],)


def _bloquear(ruta):
    """Abre `ruta` sin compartirla, como el programa del ERP mientras escribe: nadie
    mas la puede leer hasta que se cierre. Devuelve con que cerrarla."""
    import ctypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = ctypes.c_void_p
    h = k32.CreateFileW(str(ruta), 0x80000000, 0, None, 3, 0x80, None)  # GENERIC_READ, sin compartir
    assert h not in (None, ctypes.c_void_p(-1).value)
    return lambda: k32.CloseHandle(ctypes.c_void_p(h))


@pytest.mark.skipif(os.name != "nt", reason="el bloqueo de archivos es de Windows")
def test_un_archivo_bloqueado_no_lleva_la_ruta_al_panel(arbol, plataforma):
    """`--probar` (lo que corre a diario el PC de la jefa) con el stock tomado por el
    programa del ERP. El mensaje va al texto rojo del panel y a la campanita: dice
    el archivo y la causa, sin la ruta con el usuario de Windows. El error crudo
    queda en `detalle`."""
    plataforma.config = {"modo": "sin_configurar"}
    stock = arbol.archivos["stock_bodegas"]
    soltar = _bloquear(stock)
    try:
        corrida = cf.nueva_corrida(oficial=False, tipo="probar")
        cf.preparar_fuentes(corrida, copiar=False, guardar_cache=False, reportar=False)
        estado = cf.payload_de_reporte(corrida, "fin")["reporte"]["fuentes"]["stock_bodegas"]
    finally:
        soltar()

    assert estado["hecho"] == "error_lectura"
    assert estado["mensaje"] == ("No se pudo leer STOCK_BODEGAS_CURIFOR.xlsx: está abierto o "
                                 "bloqueado por otro programa.")
    assert str(arbol.od) not in estado["mensaje"]
    assert "PermissionError" in estado["detalle"]


@pytest.mark.skipif(os.name != "nt", reason="el bloqueo de archivos es de Windows")
def test_un_respaldo_de_venta_bloqueado_no_lleva_la_ruta_al_motivo(arbol, plataforma, correr):
    plataforma.config = {"modo": "sin_configurar"}
    soltar = _bloquear(arbol.ventas[1])
    try:
        r = correr()
    finally:
        soltar()

    fin = plataforma.reportes[-1]
    ventas = fin["reporte"]["fuentes"]["ventas"]
    assert r.codigo == 1 and r.enviados == []
    assert ventas["hecho"] == "error_lectura"
    assert ventas["mensaje"] == (f"No se pudo abrir '{arbol.ventas[1].name}' para ver si es un "
                                 "respaldo de venta: está abierto o bloqueado por otro programa.")
    assert "PermissionError" in ventas["detalle"]
    # Ni el motivo de la corrida ni la incidencia (la campanita) llevan la ruta.
    (motivo, detalle), = r.incidencias
    for texto in (fin["motivo"], motivo, detalle):
        assert str(arbol.od) not in texto
    assert "está abierto o bloqueado por otro programa" in fin["motivo"]


# --- GET /config y POST /reporte ---------------------------------------------------


class _Respuesta:
    def __init__(self, status, datos=None):
        self.status_code, self._datos = status, datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"Server error '{self.status_code}'")

    def json(self):
        return self._datos


def _cliente(respuestas, llamadas):
    class Cliente:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, **kw):
            llamadas.append(("POST", url, kw.get("json")))
            if url.endswith("/api/auth/login"):
                return _Respuesta(200, {"token": "t"})
            return respuestas.pop(0)

        def get(self, url, **kw):
            llamadas.append(("GET", url, None))
            r = respuestas.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
    return Cliente


@pytest.fixture
def http(monkeypatch):
    import httpx

    llamadas, respuestas = [], []
    monkeypatch.setattr(job, "_credenciales",
                        lambda: ("http://plataforma.test", "motor@ejemplo.cl", "clave"))
    monkeypatch.setattr(httpx, "Client", _cliente(respuestas, llamadas))
    job.olvidar_token()
    yield respuestas, llamadas
    job.olvidar_token()


def test_get_config_reintenta_una_vez_a_los_15_segundos(http, monkeypatch):
    respuestas, llamadas = http
    esperas = []
    monkeypatch.setattr(cf, "_dormir", esperas.append)
    respuestas += [RuntimeError("ReadTimeout"), _Respuesta(200, {"modo": "sin_configurar"})]

    assert OBTENER_REAL() == {"modo": "sin_configurar"}
    assert esperas == [15]
    assert [u for m, u, _ in llamadas if m == "GET"] == [
        "http://plataforma.test/api/admin/fuentes/config"] * 2


def test_get_config_que_vuelve_a_fallar_lanza_para_la_cascada(http):
    respuestas, _ = http
    respuestas += [RuntimeError("ReadTimeout"), RuntimeError("ReadTimeout")]

    with pytest.raises(RuntimeError):
        OBTENER_REAL()


def test_sin_credenciales_no_se_pregunta(monkeypatch):
    monkeypatch.setattr(job, "_credenciales", lambda: ("http://plataforma.test", None, None))
    assert OBTENER_REAL() is None


def test_el_reporte_va_al_endpoint_de_fuentes(http):
    respuestas, llamadas = http
    respuestas.append(_Respuesta(200, {"ok": True}))

    POST_REAL({"id": "x", "fase": "inicio"})

    assert llamadas[-1] == ("POST", "http://plataforma.test/api/admin/fuentes/reporte",
                            {"id": "x", "fase": "inicio"})


def test_sin_el_endpoint_desplegado_el_reporte_no_queda_pendiente(http, monkeypatch):
    """Si el motor se despliega antes que la plataforma, no se acumulan reportes
    que nunca se van a poder mandar."""
    respuestas, _ = http
    monkeypatch.setattr(cf, "_post_reporte", POST_REAL)
    respuestas.append(_Respuesta(404))

    assert cf.enviar_reporte({"id": "x", "fase": "fin"}) is False
    assert not cf.PENDIENTES_DIR.exists() or not list(cf.PENDIENTES_DIR.glob("*.json"))


# --- resolver_carpeta ---------------------------------------------------------------


def _carpeta(**kw):
    datos = dict(clave="databi_datos", nombre="Data BI", tipo="sharepoint",
                 params={"nombre_atajo": "Abastecimiento y Logística-Data BI - Datos"})
    datos.update(kw)
    return cf.Carpeta(**datos)


def test_resolver_carpeta_onedrive_y_acceso_directo(arbol):
    od = cf.resolver_carpeta(cf.Carpeta("bases_de_datos", "Bases de datos", "onedrive",
                                        {"ruta": "Documentos/Desarrollos/Bases de datos"}))
    sp = cf.resolver_carpeta(_carpeta())

    assert (od.ruta, od.metodo) == (arbol.crudos, "onedrive")
    assert (sp.ruta, sp.metodo) == (arbol.databi, "atajo")
    assert cf.ruta_portable(od.ruta) == "%OneDriveCommercial%\\Documentos\\Desarrollos\\Bases de datos"


def test_resolver_carpeta_no_inventa_rutas(arbol):
    r = cf.resolver_carpeta(_carpeta(params={"nombre_atajo": "Otra biblioteca - Datos"}))

    assert r.ruta is None and r.metodo is None


def test_el_env_del_pc_manda_aunque_sea_una_ruta_local(arbol, tmp_path, monkeypatch):
    local = tmp_path / "C" / "datos"
    local.mkdir(parents=True)
    monkeypatch.setenv("MOTOR_CARPETA_DATABI_DATOS", str(local))

    r = cf.resolver_carpeta(_carpeta())

    assert (r.ruta, r.metodo) == (local, "env")


def test_la_ruta_portable_fuera_de_onedrive_no_lleva_el_usuario_de_windows(arbol, tmp_path, monkeypatch):
    """La salida de emergencia (MOTOR_CARPETA_<CLAVE>) puede apuntar fuera de
    OneDrive. La vista principal del panel muestra `ruta_portable`; la ruta con el
    usuario de Windows va solo en `ruta_absoluta`, que se ve en el detalle."""
    perfil = tmp_path / "Users" / "jefa"
    local = perfil / "Escritorio local" / "tablas ERP"
    local.mkdir(parents=True)
    otra = tmp_path / "D" / "datos"
    otra.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(perfil))
    monkeypatch.setenv("MOTOR_CARPETA_DATABI_DATOS", str(local))

    r = cf.resolver_carpeta(_carpeta())
    listado = cf._listado(r.clave, r.nombre, r.ruta, r.metodo, r.probadas, [], {}, ["PC-MOTOR"],
                          "configuracion")

    assert listado["ruta_portable"] == "%USERPROFILE%\\Escritorio local\\tablas ERP"
    assert listado["ruta_absoluta"] == str(local)
    assert cf.ruta_portable(otra) is None


def test_la_ruta_por_pc_fuera_de_onedrive_se_ignora_y_se_avisa(arbol, tmp_path):
    afuera = tmp_path / "C" / "datos"
    afuera.mkdir(parents=True)
    dentro = arbol.od / "Datos de la jefa"
    dentro.mkdir()

    ignorada = cf.resolver_carpeta(_carpeta(rutas_por_pc={"PC-MOTOR": str(afuera)}), "PC-MOTOR")
    usada = cf.resolver_carpeta(_carpeta(rutas_por_pc={"pc-motor": str(dentro)}), "PC-MOTOR")

    assert (ignorada.ruta, ignorada.metodo) == (arbol.databi, "atajo")
    assert ignorada.avisos and "fuera de OneDrive" in ignorada.avisos[0]
    assert (usada.ruta, usada.metodo) == (dentro, "ruta_por_pc")


@pytest.mark.parametrize("sufijo", ["", os.sep, os.sep + "."])
def test_la_ruta_por_pc_no_puede_ser_la_raiz_de_onedrive(arbol, sufijo):
    """§3.2: no se busca en todo OneDrive. Con la raiz como ruta de un PC, la
    ubicacion recursiva de Bases de datos recorria el OneDrive entero y el listado
    subia al panel nombres de archivos personales."""
    r = cf.resolver_carpeta(_carpeta(rutas_por_pc={"PC-MOTOR": str(arbol.od) + sufijo}), "PC-MOTOR")

    assert (r.ruta, r.metodo) == (arbol.databi, "atajo")
    assert r.avisos and "raíz de OneDrive" in r.avisos[0]


def test_la_ruta_por_pc_tampoco_puede_ser_la_carpeta_de_la_organizacion(arbol, tmp_path, monkeypatch):
    """%USERPROFILE%\\<Org>, donde deja las bibliotecas el boton "Sincronizar":
    su raiz es igual de amplia. Una carpeta de adentro si vale."""
    org = tmp_path / "perfil" / "Org"           # OneDrive de mentira: "OneDrive - Org"
    (org / "Biblioteca").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "perfil"))

    raiz = cf.resolver_carpeta(_carpeta(rutas_por_pc={"PC-MOTOR": str(org)}), "PC-MOTOR")
    adentro = cf.resolver_carpeta(_carpeta(rutas_por_pc={"PC-MOTOR": str(org / "Biblioteca")}),
                                  "PC-MOTOR")

    assert raiz.metodo == "atajo" and raiz.avisos
    assert (adentro.ruta, adentro.metodo) == (org / "Biblioteca", "ruta_por_pc")


def test_el_listado_no_entra_mas_abajo_de_3_niveles(tmp_path, monkeypatch):
    """El tope de 3 niveles se aplicaba despues de recorrer todo con `rglob`."""
    import pathlib

    raiz = tmp_path / "carpeta"
    (raiz / "a" / "b" / "c").mkdir(parents=True)
    (raiz / "a" / "b" / "c" / "Stock bodegas.xlsx").write_bytes(b"x")
    hondo = raiz / "a" / "b" / "c" / "d" / "e"
    hondo.mkdir(parents=True)
    (hondo / "lejos.xlsx").write_bytes(b"x")
    mirados = []
    for metodo in ("is_file", "stat"):
        real = getattr(pathlib.Path, metodo)
        monkeypatch.setattr(pathlib.Path, metodo,
                            lambda self, *a, _r=real, **k: mirados.append(self.name) or _r(self, *a, **k))

    listado = cf._listado("x", "X", raiz, "onedrive", (), [], {}, ["PC-MOTOR"], "configuracion")

    assert [a["ruta_relativa"] for a in listado["archivos"]] == ["a/b/c/Stock bodegas.xlsx"]
    assert "lejos.xlsx" not in mirados


def test_winreg_no_se_usa():
    """Sin TI: ni el registro de Windows ni Graph."""
    import inspect

    for modulo in (cf, fuentes):
        fuente = inspect.getsource(modulo)
        assert "import winreg" not in fuente and "graph.microsoft" not in fuente


# --- manifiesto y copia -------------------------------------------------------------


def _manifiesto(tipo_oficial=True):
    corrida = cf.nueva_corrida(oficial=tipo_oficial)
    m = cf.preparar_fuentes(corrida)
    fuentes.fijar_manifiesto(m)
    return corrida, m


def test_cambiar_el_original_a_mitad_de_corrida_no_cambia_lo_que_se_lee(arbol):
    """El stock que OneDrive reemplaza a mitad de corrida: el sugerido lo leia al
    partir y las altas de la lista de precios lo volvian a buscar al final."""
    _, m = _manifiesto()
    original = arbol.archivos["stock_bodegas"]
    original.write_bytes(b"stock reemplazado a mitad de corrida")

    leido = fuentes.ruta_de("stock_bodegas")

    assert leido.read_bytes() == b"stock_bodegas v1"
    assert cf.CORRIDA_DIR in leido.parents
    assert leido.name == original.name


def test_la_copia_conserva_la_huella_del_feed_del_erp(arbol):
    """`correr_motor_real.py:1214`: nombre|mtime|tamano. Si cambiara, el feed del
    ERP se volveria a mandar entero (410 mil filas) en cada corrida."""
    _manifiesto()
    original = arbol.archivos["lista_erp"]
    copia = fuentes.ruta_de("lista_erp")

    def huella(r):
        return f"{r.name}|{int(r.stat().st_mtime)}|{r.stat().st_size}"

    assert copia != original
    assert huella(copia) == huella(original)


def test_la_huella_se_calcula_sobre_la_copia(arbol):
    _, m = _manifiesto()
    f = m.por_clave["catalogo"]

    assert f.sha256[0] == cf.sha256(f.copias[0]) == cf.sha256(arbol.archivos["catalogo"])


def test_por_descarte_da_lo_mismo_que_hoy(arbol):
    fin = job._fin_mes_cerrado(date.today())
    sin = [p.name for p in job._archivos_de_ventas(fin)]
    avisos_sin = list(job._AVISOS_FUENTES)
    job._AVISOS_FUENTES.clear()

    _manifiesto()
    con = job._archivos_de_ventas(fin)

    assert [p.name for p in con] == sin == [p.name for p in arbol.ventas]
    assert all(cf.CORRIDA_DIR in p.parents for p in con)
    assert job._AVISOS_FUENTES == avisos_sin and "Motorcraft" in avisos_sin[0]


def test_lo_que_falta_da_el_mismo_error_que_hoy(arbol):
    arbol.archivos["vigentes_ford"].unlink()
    with pytest.raises(FileNotFoundError) as hoy:
        fuentes.ruta_de("vigentes_ford")

    _manifiesto()
    with pytest.raises(FileNotFoundError) as con:
        fuentes.ruta_de("vigentes_ford")

    assert str(con.value) == str(hoy.value)
    assert job._buscar("vigentes_ford", obligatorio=False) is None


def test_solo_queda_la_copia_de_la_ultima_corrida(arbol):
    vieja = cf.CORRIDA_DIR / "corrida-anterior" / "stock_bodegas"
    vieja.mkdir(parents=True)
    (vieja / "Stock.xlsx").write_bytes(b"x")

    corrida, _ = _manifiesto()

    assert [d.name for d in cf.CORRIDA_DIR.iterdir()] == [corrida["id"]]


def test_un_archivo_que_onedrive_no_termina_de_bajar_queda_inestable(arbol, monkeypatch):
    monkeypatch.setattr(cf, "_copiar", lambda origen, destino, pres: False)

    _, m = _manifiesto()
    f = m.por_clave["stock_bodegas"]

    assert f.hecho == "inestable"
    assert f.mensaje == "OneDrive no terminó de bajar el archivo."
    # Se lee el original, como hoy: esperar mas no sirve.
    assert fuentes.ruta_de("stock_bodegas") == arbol.archivos["stock_bodegas"]


def test_un_archivo_recien_modificado_espera_un_minuto(arbol, monkeypatch):
    esperas = []
    monkeypatch.setattr(cf, "RECIENTE_SEG", 180)
    monkeypatch.setattr(cf, "_dormir", esperas.append)
    viejo = time.time() - 3600
    for p in list(arbol.archivos.values()) + arbol.ventas:
        os.utime(p, (viejo, viejo))

    cf.preparar_fuentes(cf.nueva_corrida(oficial=True))
    # Todo tiene una hora: nadie espera.
    assert esperas == []

    # El stock recien llegado: un minuto de espera y, como no cambio, se sigue.
    os.utime(arbol.archivos["stock_bodegas"], None)
    m = cf.preparar_fuentes(cf.nueva_corrida(oficial=True))
    assert esperas == [60]
    assert m.por_clave["stock_bodegas"].hecho == "encontrado"


def test_el_tope_de_espera_es_de_cinco_minutos_por_corrida(arbol, monkeypatch):
    monkeypatch.setattr(cf, "RECIENTE_SEG", 10 ** 9)  # todo parece recien bajado
    esperas = []

    def dormir(s):
        esperas.append(s)
        # El archivo sigue cambiando: nunca se estabiliza.
        p = arbol.archivos["stock_bodegas"]
        p.write_bytes(p.read_bytes() + b".")

    monkeypatch.setattr(cf, "_dormir", dormir)
    m = cf.preparar_fuentes(cf.nueva_corrida(oficial=True))

    assert sum(esperas) == cf.TOPE_ESPERA_SEG
    assert m.por_clave["stock_bodegas"].hecho == "inestable"
    # Lo que no se vio moverse no queda inestable por haberse acabado el tiempo.
    assert m.por_clave["catalogo"].hecho == "encontrado"


def test_abierto_en_excel_y_mismo_contenido_que_ayer(arbol, plataforma):
    stock = arbol.archivos["stock_bodegas"]
    (stock.parent / ("~$" + stock.name[2:])).write_bytes(b"lock")
    cfg = semilla("prueba")
    cfg["anterior"] = {"stock_bodegas": {"sha256": cf.sha256(stock),
                                         "modificado_en": "2026-01-01T09:00:00-03:00",
                                         "filas": 10}}
    plataforma.config = cfg

    _, m = _manifiesto()
    f = m.por_clave["stock_bodegas"]

    assert f.abierto_en_excel is True
    assert f.mismo_contenido_que_anterior is True
    assert m.por_clave["catalogo"].mismo_contenido_que_anterior is False


def test_el_mismo_archivo_sin_tocar_no_es_mismo_contenido_con_fecha_nueva(arbol, plataforma):
    """La corrida anterior lo reporto con la fecha al segundo; el archivo trae
    milisegundos. Sin cambiar la fecha no hay "fecha nueva con contenido viejo"."""
    stock = arbol.archivos["stock_bodegas"]
    t = int(time.time()) - 600 + 0.7
    os.utime(stock, (t, t))
    cfg = semilla("prueba")
    cfg["anterior"] = {"stock_bodegas": {"sha256": cf.sha256(stock),
                                         "modificado_en": cf._iso(stock.stat().st_mtime),
                                         "filas": 10}}
    plataforma.config = cfg

    _, m = _manifiesto()
    assert m.por_clave["stock_bodegas"].mismo_contenido_que_anterior is False

    # Un segundo despues, mismo contenido: eso si es el caso del 09-10.
    os.utime(stock, (t + 1, t + 1))
    _, m = _manifiesto()
    assert m.por_clave["stock_bodegas"].mismo_contenido_que_anterior is True


# --- sin_configurar y prueba publican EXACTAMENTE lo mismo -------------------------


def test_sin_configurar_y_prueba_leen_exactamente_lo_mismo_que_hoy(arbol, plataforma, correr):
    hoy = correr(sin_modulo=True)
    assert hoy.codigo == 0

    plataforma.config = {"modo": "sin_configurar"}
    sin_configurar = correr()

    # En prueba, aunque la plataforma apunte el stock a otra carpeta, se lee el .env.
    cfg = semilla("prueba")
    fuente_de(cfg, "stock_bodegas")["ubicaciones"] = [
        {"carpeta": "databi_datos", "subcarpeta": "", "recursiva": False}]
    fuente_de(cfg, "stock_bodegas")["diferencia_esperada"] = True
    plataforma.config = cfg
    prueba = correr()

    # Las dos corridas con el modulo leyeron de verdad desde el manifiesto.
    assert hoy.manifiestos == []
    (m_sin,), (m_prueba,) = sin_configurar.manifiestos, prueba.manifiestos
    assert (m_sin.modo, m_sin.resolucion) == ("sin_configurar", "env")
    assert (m_prueba.modo, m_prueba.resolucion) == ("prueba", "env")
    assert cf.CORRIDA_DIR in m_prueba.por_clave["stock_bodegas"].copias[0].parents
    assert m_prueba.por_clave["stock_bodegas"].prueba["resultado"] == "difiere_esperado"

    assert sin_configurar.lecturas == hoy.lecturas
    assert prueba.lecturas == hoy.lecturas
    assert sin_configurar.enviados == prueba.enviados == hoy.enviados
    assert sin_configurar.codigo == prueba.codigo == 0
    assert hoy.lecturas["stock_bodegas"][1] == b"stock_bodegas v1"
    assert [n for n, _ in hoy.lecturas["ventas"]] == [p.name for p in arbol.ventas]


def test_en_prueba_se_reporta_coincide_difiere_y_difiere_esperado(arbol, plataforma, correr):
    cfg = semilla("prueba")
    # Ensayo: el stock desde SharePoint (marcado como diferencia esperada).
    stock = fuente_de(cfg, "stock_bodegas")
    stock["ubicaciones"] = [{"carpeta": "databi_datos", "subcarpeta": "", "recursiva": False}]
    stock["diferencia_esperada"] = True
    # Un cambio sin marcar.
    fuente_de(cfg, "precios_ford")["modo"] = "archivo_exacto"
    fuente_de(cfg, "precios_ford")["nombre_archivo"] = "Lista de precio ford al 28.07.2026.xlsx"
    escribir_xlsx(arbol.crudos / "Lista de precios" / "Lista de precio ford al 28.07.2026.xlsx",
                  ["PartNumber"])
    os.utime(arbol.crudos / "Lista de precios" / "Lista de precio ford al 28.07.2026.xlsx",
             (time.time() - 7200, time.time() - 7200))
    # Una obligatoria que en la plataforma no encuentra archivo.
    fuente_de(cfg, "mix_reemplazos")["incluye"] = ["*no existe*"]
    plataforma.config = cfg

    r = correr()
    fin = plataforma.reportes[-1]
    prueba = {c: f["prueba"] for c, f in fin["reporte"]["fuentes"].items()}

    assert r.codigo == 0 and fin["fase"] == "fin" and fin["resultado"] == "ok"
    assert prueba["catalogo"]["resultado"] == "coincide"
    assert prueba["stock_bodegas"]["resultado"] == "difiere_esperado"
    assert prueba["stock_bodegas"]["archivo"]["ruta_relativa"] == "Stock bodegas.xlsx"
    assert prueba["precios_ford"]["resultado"] == "difiere"
    assert prueba["mix_reemplazos"]["resultado"] == "falta"
    assert prueba["mix_reemplazos"]["frenaria"] == "Falta el archivo de Mix de reemplazos"
    # En prueba nada de eso frena: el sugerido salio igual.
    assert len(r.enviados) == 1


def _ensayo_del_stock_en_sharepoint(arbol, plataforma, contenido=b"stock_sharepoint"):
    """Prueba con el stock apuntado a Data BI (el ensayo de la tanda 1). Por defecto
    el archivo de SharePoint es del mismo tamano que el local: para saber si son el
    mismo hay que leer los dos originales. El .env sigue eligiendo el local, que es
    mas nuevo."""
    arbol.stock_sp.write_bytes(contenido)
    viejo = time.time() - 3600
    os.utime(arbol.stock_sp, (viejo, viejo))
    cfg = semilla("prueba")
    stock = fuente_de(cfg, "stock_bodegas")
    stock["ubicaciones"] = [{"carpeta": "databi_datos", "subcarpeta": "", "recursiva": False}]
    stock["diferencia_esperada"] = True
    plataforma.config = cfg


def test_comparar_un_original_que_no_termina_de_leerse_tiene_tope(arbol, plataforma, correr, monkeypatch):
    """En prueba, ver si los dos lados eligieron el mismo contenido lee los
    ORIGINALES. Si el de SharePoint esta solo en la nube y OneDrive se pega, esa
    lectura no puede colgar la corrida: va con el mismo tope que la copia y, si se
    acaba, da "difiere"."""
    import threading

    _ensayo_del_stock_en_sharepoint(arbol, plataforma)
    assert arbol.stock_sp.stat().st_size == arbol.archivos["stock_bodegas"].stat().st_size
    monkeypatch.setattr(cf, "TOPE_COPIA_ARCHIVO_SEG", 0.2)
    soltar = threading.Event()
    real = cf.sha256

    def sha(p):
        if str(p) == str(arbol.stock_sp):
            soltar.wait(10)            # OneDrive pegado
        return real(p)

    monkeypatch.setattr(cf, "sha256", sha)
    inicio = time.time()
    try:
        r = correr()
    finally:
        soltar.set()

    assert time.time() - inicio < 5
    assert r.codigo == 0 and len(r.enviados) == 1
    prueba = plataforma.reportes[-1]["reporte"]["fuentes"]["stock_bodegas"]["prueba"]
    assert prueba["resultado"] == "difiere_esperado"


def test_comparar_dos_archivos_de_distinto_tamano_no_los_lee(arbol, plataforma, correr, monkeypatch):
    _ensayo_del_stock_en_sharepoint(arbol, plataforma, b"stock de sharepoint, otro tamano")
    leidos = []
    real = cf.sha256
    monkeypatch.setattr(cf, "sha256", lambda p: leidos.append(str(p)) or real(p))

    correr()

    assert str(arbol.stock_sp) not in leidos
    prueba = plataforma.reportes[-1]["reporte"]["fuentes"]["stock_bodegas"]["prueba"]
    assert prueba["resultado"] == "difiere_esperado"


def test_probar_no_baja_de_la_nube_lo_que_solo_compara(arbol, plataforma, monkeypatch):
    """`--probar` (el PC de la jefa, todos los dias) y la oficial de un PC que no es
    el titular no copian nada: leer un archivo solo en la nube para sacarle la
    huella lo bajaria entero (la LISTA DE PRECIOS pesa 104 MB)."""
    _ensayo_del_stock_en_sharepoint(arbol, plataforma)
    en_la_nube = {str(arbol.stock_sp), str(arbol.archivos["catalogo"])}
    real_estado = cf.estado_onedrive
    monkeypatch.setattr(cf, "estado_onedrive",
                        lambda p: "solo_nube" if str(p) in en_la_nube else real_estado(p))
    leidos = []
    real = cf.sha256
    monkeypatch.setattr(cf, "sha256", lambda p: leidos.append(str(p)) or real(p))

    assert cf.main(["--probar"]) == 0

    assert not en_la_nube & set(leidos)
    # Lo que si esta en el PC se sigue midiendo.
    assert str(arbol.archivos["stock_bodegas_frontera"]) in leidos


# --- PC titular ----------------------------------------------------------------------


def test_un_pc_que_no_es_el_titular_no_calcula_ni_publica(arbol, plataforma, correr, capsys):
    plataforma.config = semilla("prueba", pc_titular="PC-JEFA",
                                pcs={"PC-JEFA": {"alias": "PC de la jefa"}})

    r = correr()

    assert r.codigo == 0
    assert r.enviados == [] and r.lecturas == {} and r.incidencias == []
    assert "NO SE PUBLICA: este PC no es el titular (PC de la jefa)" in capsys.readouterr().out
    fin = plataforma.reportes[-1]
    assert (fin["resultado"], fin["titular"], fin["tipo"]) == ("no_titular", False, "oficial")
    # Hace lo mismo que --probar --reportar: manda lo que usa hoy, para sembrar.
    assert fin["config_efectiva"]["fuentes"]
    assert fin["reporte"]["fuentes"]["stock_bodegas"]["prueba"]["resultado"] == "coincide"
    # Y no copia nada.
    assert not cf.CORRIDA_DIR.exists() or not any(cf.CORRIDA_DIR.iterdir())


def test_el_kill_switch_ignora_tambien_el_titular(arbol, plataforma, correr, monkeypatch):
    plataforma.config = semilla("activa", pc_titular="PC-JEFA")
    monkeypatch.setenv("MOTOR_FUENTES", "env")

    r = correr()

    assert r.codigo == 0 and len(r.enviados) == 1
    assert plataforma.pedidas == 0
    # No pide la configuracion, pero el reporte si va: el panel muestra que corrio
    # con la configuracion del PC (docs/adr/0004, data/crudos/README.md).
    assert plataforma.reportes[-1]["config_origen"] == "env"


# --- reporte ---------------------------------------------------------------------------


def test_inicio_y_fin_caen_en_la_misma_corrida(arbol, plataforma, correr):
    plataforma.config = {"modo": "sin_configurar"}

    correr()

    inicio, fin = plataforma.reportes
    assert (inicio["fase"], fin["fase"]) == ("inicio", "fin")
    assert inicio["id"] == fin["id"]
    assert (inicio["resultado"], fin["resultado"]) == ("en_curso", "ok")
    assert fin["publico"] is True and fin["titular"] is True
    assert fin["config_origen"] == "plataforma" and fin["reporte"]["modo"] == "sin_configurar"
    assert fin["config_efectiva"]["catalogo"]["stock_bodegas"]["requerida"] is True


def test_el_reporte_dice_que_archivo_leyo_cada_fuente_y_de_donde(arbol, plataforma, correr):
    plataforma.config = {"modo": "sin_configurar"}

    correr()
    fin = plataforma.reportes[-1]
    stock = fin["reporte"]["fuentes"]["stock_bodegas"]
    ventas = fin["reporte"]["fuentes"]["ventas"]
    carpetas = {c["clave"]: c for c in fin["reporte"]["carpetas"]}

    assert stock["hecho"] == "encontrado"
    assert stock["archivos"][0]["carpeta"] == "bases_de_datos"
    assert stock["archivos"][0]["ruta_relativa"] == "stock/STOCK_BODEGAS_CURIFOR.xlsx"
    assert stock["archivos"][0]["sha256"] == cf.sha256(arbol.archivos["stock_bodegas"])
    assert stock["carpetas_con_candidatos"] == ["bases_de_datos", "databi_datos"]
    assert stock["edad_dias_habiles"] == 0
    assert [a["ruta_relativa"] for a in ventas["archivos"]] == [
        f"Ventas/{p.name}" for p in arbol.ventas]
    assert ventas["descartados"][0]["nombre"] == arbol.motorcraft.name
    assert ventas["extra"] == {"periodo_ultimo_mes": "202609", "total_mes_cerrado": 5.0}
    assert carpetas["databi_datos"]["ruta_portable"] == (
        "%OneDriveCommercial%\\Abastecimiento y Logística-Data BI - Datos")
    elegidos = {a["ruta_relativa"] for a in carpetas["bases_de_datos"]["archivos"] if a["elegido"]}
    assert "stock/STOCK_BODEGAS_CURIFOR.xlsx" in elegidos
    ajeno = next(a for a in carpetas["databi_datos"]["archivos"]
                 if a["ruta_relativa"] == "Curifor - Seguimiento Compras.xlsx")
    assert ajeno["elegido"] is False


def test_el_listado_marca_un_archivo_compartido_con_la_fuente_que_lo_lee(arbol, plataforma):
    """"Lista de precio ford.xlsx" la eligen precios_ford (se lee) y precios_proveedor
    (solo se reconoce). En el listado del panel tiene que figurar la que lo lee."""
    plataforma.config = {"modo": "sin_configurar"}
    corrida, _ = _manifiesto()

    carpetas = {c["clave"]: c for c in cf.payload_de_reporte(corrida, "inicio")["reporte"]["carpetas"]}
    ford = next(a for a in carpetas["bases_de_datos"]["archivos"]
                if a["ruta_relativa"] == "Lista de precios/Lista de precio ford.xlsx")
    assert (ford["fuente"], ford["elegido"]) == ("precios_ford", True)


@pytest.mark.parametrize("caso", ["ruta_editada", "sin_onedrive"])
def test_el_listado_no_repite_la_clave_de_una_carpeta_configurada(arbol, plataforma, monkeypatch, caso):
    """En prueba el .env sigue leyendo su carpeta, y si la configurada se resuelve
    a otra ruta (un ensayo que la mueve, o un PC sin %OneDriveCommercial%) su
    listado salia con la MISMA clave. La plataforma arma un dict por clave y se
    quedaba con el del .env: los selectores y la vista previa mostraban la carpeta
    vieja mientras la fila del stock decia que este PC no la tenia."""
    cfg = semilla("prueba")
    if caso == "ruta_editada":
        nueva = arbol.od / "Documentos" / "Motor"
        (nueva / "stock").mkdir(parents=True)
        (nueva / "stock" / "Stock bodegas nuevo.xlsx").write_bytes(b"x")
        next(c for c in cfg["carpetas"] if c["clave"] == "bases_de_datos")["params"]["ruta"] = (
            "Documentos/Motor")
    plataforma.config = cfg
    if caso == "sin_onedrive":
        monkeypatch.delenv("OneDriveCommercial")
    corrida = cf.nueva_corrida(oficial=False, tipo="probar")

    cf.preparar_fuentes(corrida, copiar=False, guardar_cache=False, reportar=False)

    carpetas = cf.payload_de_reporte(corrida, "fin")["reporte"]["carpetas"]
    claves = [c["clave"] for c in carpetas]
    assert len(claves) == len(set(claves))
    bd = next(c for c in carpetas if c["clave"] == "bases_de_datos")
    assert bd["origen"] == "configuracion"
    if caso == "ruta_editada":
        assert [a["ruta_relativa"] for a in bd["archivos"]] == ["stock/Stock bodegas nuevo.xlsx"]
    else:
        assert bd["existe"] is False


def test_si_el_reporte_falla_la_corrida_no_cambia_y_queda_pendiente(arbol, plataforma, correr):
    plataforma.config = {"modo": "sin_configurar"}
    plataforma.falla_post = RuntimeError("502 Bad Gateway")
    fallos_antes = list(job._FALLOS)

    r = correr()

    assert r.codigo == 0 and len(r.enviados) == 1
    assert job._FALLOS == fallos_antes
    pendientes = sorted(cf.PENDIENTES_DIR.glob("*.json"))
    # El fin reemplaza al inicio de la misma corrida.
    assert [json.loads(p.read_text(encoding="utf-8"))["fase"] for p in pendientes] == ["fin"]

    plataforma.falla_post = None
    assert cf.reenviar_pendientes() == 1
    assert plataforma.reportes[-1]["resultado"] == "ok"
    assert not list(cf.PENDIENTES_DIR.glob("*.json"))


def test_se_reenvian_a_lo_mas_10_pendientes(arbol, plataforma):
    for i in range(12):
        cf._guardar_pendiente({"id": f"c{i:02d}", "fase": "fin"})

    assert cf.reenviar_pendientes() == 10
    assert len(list(cf.PENDIENTES_DIR.glob("*.json"))) == 2


def test_una_corrida_huerfana_se_reporta_como_cortada(arbol, plataforma, correr):
    """El PC se apago a mitad: queda `corrida_en_curso.json` de un proceso muerto."""
    cf.EN_CURSO.parent.mkdir(parents=True, exist_ok=True)
    cf.EN_CURSO.write_text(json.dumps({"pid": 999999, "payload": {
        "id": "corrida-del-martes", "fase": "inicio", "resultado": "en_curso",
        "pc": "PC-MOTOR", "tipo": "oficial"}}), encoding="utf-8")
    plataforma.config = {"modo": "sin_configurar"}

    correr()

    cortada = next(r for r in plataforma.reportes if r["id"] == "corrida-del-martes")
    assert (cortada["fase"], cortada["resultado"]) == ("fin", "cortada")
    assert "se cortó" in cortada["motivo"]
    assert not cf.EN_CURSO.exists()


def test_tambien_se_reporta_cuando_la_corrida_frena(arbol, plataforma, correr):
    plataforma.config = {"modo": "sin_configurar"}
    viejo = time.time() - 30 * 86400
    os.utime(arbol.archivos["stock_bodegas"], (viejo, viejo))
    os.utime(arbol.stock_sp, (viejo, viejo))

    r = correr()

    fin = plataforma.reportes[-1]
    assert r.codigo == 1 and r.enviados == []
    assert fin["resultado"] == "frenada"
    assert fin["motivo"].startswith("No se carga a produccion con archivos desactualizados.")


def test_si_falla_el_calculo_el_resultado_es_fallo(arbol, plataforma, correr, monkeypatch):
    plataforma.config = {"modo": "sin_configurar"}

    def revienta():
        raise ValueError("No se encontro la fila de encabezados")

    r = correr(al_construir=revienta)

    assert r.codigo == 1
    assert plataforma.reportes[-1]["resultado"] == "fallo"


def test_una_corrida_que_se_corta_se_reporta_como_cortada(arbol, plataforma, correr):
    plataforma.config = {"modo": "sin_configurar"}

    def ctrl_c():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        correr(al_construir=ctrl_c)

    assert plataforma.reportes[-1]["resultado"] == "cortada"
    assert not cf.EN_CURSO.exists()


def test_si_el_modulo_revienta_el_motor_corre_como_siempre(arbol, plataforma, correr, monkeypatch):
    plataforma.config = {"modo": "sin_configurar"}
    hoy = correr(sin_modulo=True)

    def revienta(*a, **k):
        raise RuntimeError("bug en el manifiesto")

    monkeypatch.setattr(cf, "resolver_env", revienta)
    r = correr()

    assert r.codigo == 0 and r.lecturas == hoy.lecturas
    assert any("bug en el manifiesto" in a for a in plataforma.reportes[-1]["reporte"]["avisos"])


def test_las_lecturas_registran_filas_hoja_y_encabezado(tmp_path):
    from conftest import escribir_stock

    from src.motor import fuentes_reales

    ruta = escribir_stock(tmp_path / "Stock bodegas.xlsx", 3)
    fuentes_reales.leer_stock(ruta)
    # Un reporte con titulo arriba: los encabezados estan en la fila 3.
    ventas = escribir_xlsx(tmp_path / "2026 (6).xlsx", ["Reporte de ventas"], [
        ["Desde 01-01-2026"],
        ["Fecha", "Producto", "Cantidad", "tipoDocto", "tipoproducto", "SUCURSAL"],
        ["2026-01-01", "17 A", 3, "F", "R", "01 L"]])
    lectores_excel.leer_ventas_excel(ventas)

    assert lectores_excel.LECTURAS[str(ruta)] == {"filas": 3, "hoja": "Sheet", "fila_encabezado": 1}
    assert lectores_excel.LECTURAS[str(ventas)] == {"filas": 1, "hoja": "Sheet", "fila_encabezado": 3}


# --- CLI --probar -------------------------------------------------------------------


def test_probar_muestra_13_de_13_y_no_escribe_nada(arbol, capsys):
    assert cf.main(["--probar"]) == 0
    salida = capsys.readouterr().out

    assert "13 de 13 fuentes que se leen dan lo mismo." in salida
    assert f"respaldos de venta: {[p.name for p in arbol.ventas]}" in salida
    assert not cf.CACHE.exists() and not cf.CORRIDA_DIR.exists() and not cf.EN_CURSO.exists()


def test_probar_reportar_manda_la_config_efectiva_con_tipo_probar(arbol, plataforma):
    plataforma.config = {"modo": "sin_configurar"}

    assert cf.main(["--probar", "--reportar"]) == 0

    (r,) = plataforma.reportes
    assert (r["tipo"], r["fase"], r["resultado"]) == ("probar", "fin", "ok")
    assert {f["clave"] for f in r["config_efectiva"]["fuentes"]} == set(fuentes.FUENTES)
    assert not cf.CACHE.exists()


def test_probar_reportar_reenvia_lo_que_quedo_pendiente(arbol, plataforma):
    """El PC de la jefa solo corre `--probar --reportar` hasta ser titular: lo que no
    llego un dia sin red se manda al dia siguiente, antes del reporte nuevo."""
    plataforma.config = {"modo": "sin_configurar"}
    plataforma.falla_post = RuntimeError("sin red")
    assert cf.main(["--probar", "--reportar"]) == 0
    (pendiente,) = cf.PENDIENTES_DIR.glob("*.json")
    ayer = json.loads(pendiente.read_text(encoding="utf-8"))["id"]

    plataforma.falla_post = None
    assert cf.main(["--probar", "--reportar"]) == 0

    assert [r["id"] for r in plataforma.reportes][0] == ayer and len(plataforma.reportes) == 2
    assert not list(cf.PENDIENTES_DIR.glob("*.json"))


# --- CLI --guardar-config -----------------------------------------------------------


def test_sin_configuracion_guardada_un_pc_nuevo_se_cree_titular(arbol, plataforma):
    """Por que existe --guardar-config: --probar (lo unico que corria el instalador) no
    guarda nada, y si en la primera corrida del PC nuevo la plataforma no responde, no
    hay de donde saber quien es el titular."""
    plataforma.error = RuntimeError("502 Bad Gateway")

    cfg, origen, _, _ = cf.cargar_configuracion()

    assert (cfg, origen) == (None, "env")
    assert cf.es_titular(cfg, "PC-JEFA") is True


def test_guardar_config_deja_la_configuracion_y_el_pc_nuevo_ya_no_se_cree_titular(arbol, plataforma, capsys):
    plataforma.config = semilla("prueba", pc_titular="PC-ANTERIOR")

    assert cf.main(["--guardar-config"]) == 0

    assert "modo prueba, titular PC-ANTERIOR" in capsys.readouterr().out
    assert json.loads(cf.CACHE.read_text(encoding="utf-8"))["config"]["pc_titular"] == "PC-ANTERIOR"
    # Al dia siguiente, a las 09:30, la plataforma no responde: manda lo guardado.
    plataforma.error = RuntimeError("502 Bad Gateway")
    cfg, origen, _, _ = cf.cargar_configuracion()
    assert origen == "cache"
    assert cf.es_titular(cfg, "PC-JEFA") is False


def test_guardar_config_sin_plataforma_ni_nada_guardado_sale_con_1(arbol, plataforma, capsys):
    plataforma.error = RuntimeError("ConnectError")

    assert cf.main(["--guardar-config"]) == 1

    assert "Este PC no tiene configuracion de fuentes" in capsys.readouterr().out
    assert not cf.CACHE.exists()
