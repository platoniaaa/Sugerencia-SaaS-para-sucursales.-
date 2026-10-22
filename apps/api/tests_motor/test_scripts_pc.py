"""Los scripts que corren el motor en el PC de la jefa, con el PowerShell de Windows.

- `tarea_si_no_corrio_hoy.ps1` (tarea de las 09:30): no calcula dos veces el mismo
  dia ni encima de otra corrida.
- `actualizar_plataforma.ps1` (acceso del Escritorio): programa del ERP y despues
  el motor, solo si el programa bajo todo, y un resumen que dice que paso.

`tarea_diaria.ps1` y el programa del ERP se reemplazan por dobles que anotan que
los llamaron: no se corre el motor ni Flexline.
"""
import datetime as dt
import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[3] / "scripts"
POWERSHELL = shutil.which("powershell")

pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="necesita el PowerShell de Windows")

# Un tarea_diaria.ps1 falso: escribe en el log del dia lo que le pase el test y sale
# con el codigo que le pase. Anota que lo llamaron.
_TAREA_DIARIA_FALSA = r"""
$root = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
$log = "$root\logs\motor_$(Get-Date -Format 'yyyy-MM-dd').log"
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $log -Append -Encoding utf8
Get-Content "$root\salida_falsa.txt" -Encoding UTF8 | Out-File $log -Append -Encoding utf8
New-Item -ItemType File -Force "$root\tarea_diaria_llamada.txt" | Out-Null
exit [int](Get-Content "$root\codigo_falso.txt")
"""


class _Pc:
    def __init__(self, raiz: pathlib.Path):
        self.raiz = raiz
        (raiz / "scripts").mkdir(parents=True)
        for nombre in ("tarea_si_no_corrio_hoy.ps1", "tarea_al_iniciar_sesion.ps1",
                       "actualizar_plataforma.ps1", "salida_motor.ps1", "robot_erp.ps1"):
            shutil.copy2(SCRIPTS / nombre, raiz / "scripts" / nombre)
        (raiz / "scripts" / "tarea_diaria.ps1").write_text(_TAREA_DIARIA_FALSA, encoding="utf-8")
        self.motor("CARGA OFICIAL: 18254 filas.\nRESULTADO: OK", 0)

    def motor(self, salida: str, codigo: int):
        (self.raiz / "salida_falsa.txt").write_text(salida + "\n", encoding="utf-8")
        (self.raiz / "codigo_falso.txt").write_text(str(codigo))

    @property
    def log(self) -> pathlib.Path:
        return self.raiz / "logs" / f"motor_{dt.date.today():%Y-%m-%d}.log"

    @property
    def motor_llamado(self) -> bool:
        return (self.raiz / "tarea_diaria_llamada.txt").exists()

    def candado(self, pid: int) -> str:
        """El candado del motor, con la fecha de ahora: un candado se escribe despues de
        que parte su proceso (con una fecha anterior, parece de un PID reciclado)."""
        desde = _ahora()
        (self.raiz / "apps" / "api" / "data").mkdir(parents=True, exist_ok=True)
        (self.raiz / "apps" / "api" / "data" / "motor.lock").write_text(f"{pid} {desde}", encoding="utf-8")
        return desde

    def correr(self, script: str, *args, entorno: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(self.raiz / "scripts" / script), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
            env=entorno)


def _ahora() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
def pc(tmp_path):
    return _Pc(tmp_path / "repo")


# --- tarea_si_no_corrio_hoy.ps1 ---------------------------------------------------


def test_a_las_0930_corre_si_hoy_no_hubo_corrida(pc):
    r = pc.correr("tarea_si_no_corrio_hoy.ps1")

    assert pc.motor_llamado
    assert r.returncode == 0


def test_si_ella_ya_actualizo_hoy_no_calcula_otra_vez(pc):
    pc.log.parent.mkdir(parents=True)
    pc.log.write_text("=== 2026-10-19 08:40:00 ===\nCARGA OFICIAL: 18254 filas.\nRESULTADO: OK\n",
                      encoding="utf-8-sig")

    pc.correr("tarea_si_no_corrio_hoy.ps1")

    assert not pc.motor_llamado


def test_una_corrida_cortada_sin_resultado_se_vuelve_a_correr(pc):
    """El log del dia existe pero sin RESULTADO: la corrida murio a mitad (se apago
    el PC). Esa no cuenta como hecha."""
    pc.log.parent.mkdir(parents=True)
    pc.log.write_text("=== 2026-10-19 08:40:00 ===\nCrudos: C:\\datos\n", encoding="utf-8-sig")

    pc.correr("tarea_si_no_corrio_hoy.ps1")

    assert pc.motor_llamado


def test_con_una_corrida_en_curso_no_lanza_otra(pc):
    pc.candado(os.getpid())  # el PID de este test: un Python vivo, como el motor

    pc.correr("tarea_si_no_corrio_hoy.ps1")

    assert not pc.motor_llamado


def test_un_candado_de_un_proceso_muerto_no_frena(pc):
    muerto = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                            capture_output=True, text=True, check=True)
    pc.candado(int(muerto.stdout))

    pc.correr("tarea_si_no_corrio_hoy.ps1")

    assert pc.motor_llamado


def _ventana_del_acceso(pc, segundos: int, escribe_resultado: bool = False) -> subprocess.Popen:
    """Una ventana de PowerShell viva con el candado del acceso "Actualizar
    plataforma", que termina sola a los `segundos` (si se pide, dejando la linea
    RESULTADO en el log, como cuando el acceso publico)."""
    fin = ""
    if escribe_resultado:
        fin = (f"; New-Item -ItemType Directory -Force '{pc.log.parent}' | Out-Null"
               f"; 'RESULTADO: OK' | Out-File '{pc.log}' -Append -Encoding utf8")
    ventana = subprocess.Popen([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
                                f"Start-Sleep -Seconds {segundos}{fin}"])
    (pc.raiz / ".actualizar_plataforma.lock").write_text(f"{ventana.pid} {_ahora()}", encoding="ascii")
    return ventana


def _actualizando_motor(pc, segundos: int) -> subprocess.Popen:
    """Un agente vivo atendiendo un "Actualizar motor": su candado lleva el tipo."""
    agente = subprocess.Popen([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
                               f"Start-Sleep -Seconds {segundos}"])
    (pc.raiz / ".agente.lock").write_text(f"{agente.pid} {_ahora()} actualizar_motor", encoding="ascii")
    return agente


def test_a_las_0930_espera_al_acceso_y_no_repite_si_el_publico(pc):
    """Ella aprieta "Actualizar plataforma" a las 09:25: a las 09:30 el programa del
    ERP sigue bajando. Lanzar el motor ahi leeria archivos a medio bajar."""
    ventana = _ventana_del_acceso(pc, 8, escribe_resultado=True)
    try:
        pc.correr("tarea_si_no_corrio_hoy.ps1", "-EsperaSeg", "1", "-EsperaMaxMin", "2")
    finally:
        ventana.kill()

    assert not pc.motor_llamado


def test_si_el_acceso_termina_sin_publicar_la_tarea_calcula(pc):
    """El programa del ERP fallo y el acceso no calculo: la tarea de las 09:30
    calcula con lo que haya, como si el acceso no hubiera existido."""
    ventana = _ventana_del_acceso(pc, 6)
    try:
        pc.correr("tarea_si_no_corrio_hoy.ps1", "-EsperaSeg", "1", "-EsperaMaxMin", "2")
    finally:
        ventana.kill()

    assert pc.motor_llamado


def test_si_la_corrida_de_la_manana_fallo_a_las_0930_se_vuelve_a_intentar(pc):
    """El acceso de las 08:40 bajo todo, pero la carga dio 502 (Render se reinicio, como
    el 29-09, el 30-09 y el 02-10). Antes la tarea de las 09:30 veia la linea RESULTADO,
    salia con 0 y el dia quedaba sin sugerido nuevo."""
    pc.log.parent.mkdir(parents=True)
    pc.log.write_text("=== 2026-10-19 08:40:00 ===\nERROR: la plataforma respondio 502\n"
                      "RESULTADO: FALLO (codigo 1)\n", encoding="utf-8-sig")

    pc.correr("tarea_si_no_corrio_hoy.ps1")

    assert pc.motor_llamado


def test_si_despues_de_una_falla_salio_bien_no_se_repite(pc):
    """Decide la ultima linea RESULTADO del dia (la del agente tambien cuenta)."""
    pc.log.parent.mkdir(parents=True)
    pc.log.write_text("=== 2026-10-19 08:40:00 ===\nRESULTADO: FALLO (codigo 1)\n"
                      "=== 2026-10-19 09:02:00 (agente: Actualizar ahora) ===\n"
                      "CARGA OFICIAL: 18254 filas.\nRESULTADO: OK (agente)\n", encoding="utf-8-sig")

    pc.correr("tarea_si_no_corrio_hoy.ps1")

    assert not pc.motor_llamado


def test_a_las_0930_espera_a_que_termine_una_actualizacion_del_motor(pc):
    """Un admin aprieta "Actualizar motor" a las 09:29 y el agente esta en pip install:
    un motor lanzado encima importaria librerias a medio reinstalar."""
    agente = _actualizando_motor(pc, 6)
    try:
        partio = time.monotonic()
        pc.correr("tarea_si_no_corrio_hoy.ps1", "-EsperaSeg", "1", "-EsperaMaxMin", "2")
        espero = time.monotonic() - partio
    finally:
        agente.kill()

    assert pc.motor_llamado
    assert espero >= 4, f"lanzo el motor sin esperar ({espero:.1f} s)"


def test_al_iniciar_sesion_antes_de_las_0930_no_corre(pc):
    """Antes de las 09:30 la corrida es de la tarea diaria (y del programa del ERP)."""
    pc.correr("tarea_al_iniciar_sesion.ps1", "-Ahora", "2026-10-19 08:40")

    assert not pc.motor_llamado


def test_al_iniciar_sesion_despues_de_las_0930_recupera_el_dia(pc):
    """El PC se reinicio a la 01:00 y nadie entro antes de las 09:30 (evento 332)."""
    pc.correr("tarea_al_iniciar_sesion.ps1", "-Ahora", "2026-10-19 10:15")

    assert pc.motor_llamado


def test_al_iniciar_sesion_no_repite_ni_se_queda_pegado_en_un_candado_viejo(pc):
    pc.log.parent.mkdir(parents=True)
    pc.log.write_text("=== 2026-10-19 09:30:04 ===\nRESULTADO: OK\n", encoding="utf-8-sig")
    pc.correr("tarea_al_iniciar_sesion.ps1", "-Ahora", "2026-10-19 10:15")
    assert not pc.motor_llamado, "hoy ya hubo corrida"

    pc.log.unlink()
    muerto = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                            capture_output=True, text=True, check=True)
    pc.candado(int(muerto.stdout))
    pc.correr("tarea_al_iniciar_sesion.ps1", "-Ahora", "2026-10-19 10:15")
    assert pc.motor_llamado, "un candado de una corrida cortada no deja el dia sin recuperar"


def test_devuelve_el_codigo_de_la_corrida(pc):
    """La tarea de Windows muestra el resultado: un fallo no puede quedar en 0."""
    pc.motor("ERROR: el stock esta vencido\nRESULTADO: FALLO (codigo 1)", 1)

    assert pc.correr("tarea_si_no_corrio_hoy.ps1").returncode == 1


# --- actualizar_plataforma.ps1 ----------------------------------------------------

# El programa del ERP falso, con el aviso de "no toques el PC" del de verdad. Un
# pywinauto vacio al lado basta para que se lo reconozca como instalado.
_ROBOT_FALSO = """\
import os, sys
print("\\u00a7PC\\u00a7|0|Descargando de Flexline - NO uses el mouse/teclado")
print("  OK stock_curifor")
if sys.argv[1:4] != ["descargar", "--tablas",
                     "stock_frontera,seguimiento_frontera,seguimiento_importado,seguimiento_nacional,stock_curifor"]:
    print("argumentos inesperados:", sys.argv[1:])
    sys.exit(2)
if open("codigo_robot.txt").read().strip() != "0":
    print("  FALLO seguimiento_frontera")
    sys.exit(1)
if os.path.exists("copia_falla.txt"):
    # Lo que escribe el de verdad (flexline_flows.py, _copiar_copias_locales) cuando el
    # archivo de destino esta abierto en Excel. Igual sale con 0: solo mira las descargas.
    print("2026-10-19 09:05:41,028 [ERROR] Copia local FALLO stock_frontera.xlsx -> "
          "C:\\\\OneDrive\\\\Bases de datos\\\\stock: [WinError 32] El proceso no tiene acceso al "
          "archivo porque esta siendo utilizado por otro proceso")
"""


def _robot(pc, codigo: int) -> pathlib.Path:
    robot = pc.raiz.parent / "automatizacion"
    robot.mkdir()
    (robot / "panel.bat").write_text("@echo off\n")
    (robot / "flexline_flows.py").write_text(_ROBOT_FALSO, encoding="utf-8")
    (robot / "pywinauto.py").write_text("")
    (robot / "codigo_robot.txt").write_text(str(codigo))
    (pc.raiz / ".env").write_bytes(f"ROBOT_ERP_DIR={robot}\n".encode("utf-8"))
    return robot


def test_el_acceso_corre_el_programa_del_erp_y_despues_el_motor(pc):
    _robot(pc, 0)

    r = pc.correr("actualizar_plataforma.ps1", "-SinPausa")

    assert r.returncode == 0, r.stdout + r.stderr
    assert ">>> NO TOQUES EL PC: Descargando de Flexline" in r.stdout
    assert "Tablas del ERP listas" in r.stdout
    assert pc.motor_llamado
    assert "Se publicaron 18254 filas: los compradores ya ven los datos nuevos." in r.stdout


def test_si_el_programa_del_erp_falla_no_se_calcula(pc):
    """Mejor el sugerido de ayer completo que uno nuevo con un seguimiento viejo: la
    tarea de las 09:30 igual calcula con lo que haya."""
    _robot(pc, 1)

    r = pc.correr("actualizar_plataforma.ps1", "-SinPausa")

    assert r.returncode == 1
    assert "no bajó todas las tablas" in r.stdout
    assert "FALLO seguimiento_frontera" in r.stdout
    assert not pc.motor_llamado


def test_si_el_programa_no_pudo_dejar_la_copia_en_bases_de_datos_no_se_calcula(pc):
    """Ella tiene stock_frontera.xlsx abierto en Excel: el programa baja bien, la copia
    a 'Bases de datos' falla y aun asi sale con 0. El motor leia la copia de ayer, que
    pasa la guarda de frescura, publicaba y la ventana decia LISTO."""
    robot = _robot(pc, 0)
    (robot / "copia_falla.txt").write_text("1")

    r = pc.correr("actualizar_plataforma.ps1", "-SinPausa")

    assert r.returncode == 1
    assert "Tablas del ERP listas" not in r.stdout
    assert "no pudo dejar la copia en 'Bases de datos'" in r.stdout
    assert "Copia local FALLO stock_frontera.xlsx" in r.stdout
    assert "cierra los Excel de la carpeta 'Bases de datos'" in r.stdout
    assert not pc.motor_llamado


def test_sin_la_carpeta_del_programa_explica_que_hacer(pc):
    (pc.raiz / ".env").write_bytes(b"ROBOT_ERP_DIR=C:\\no\\existe\n")

    r = pc.correr("actualizar_plataforma.ps1", "-SinPausa")

    assert r.returncode == 1
    assert "No encuentro el programa del ERP" in r.stdout
    assert "INSTALAR PLATAFORMA" in r.stdout
    assert not pc.motor_llamado


def test_si_el_motor_falla_lo_dice_con_el_motivo(pc):
    pc.motor("  DESACTUALIZADO: stock_bodegas (4 dias habiles)\n"
             "ERROR: hay archivos desactualizados; no se publica.\nRESULTADO: FALLO (codigo 1)", 1)

    r = pc.correr("actualizar_plataforma.ps1", "-SinRobot", "-SinPausa")

    assert r.returncode == 1
    assert "El sugerido NO se actualizó" in r.stdout
    assert "DESACTUALIZADO: stock_bodegas (4 dias habiles)" in r.stdout
    assert "ERROR: hay archivos desactualizados; no se publica." in r.stdout
    # Dice si la tarea de las 09:30 lo va a reintentar (depende de la hora del test).
    assert ("A las 09:30 se vuelve a intentar solo" in r.stdout
            or "La tarea de las 09:30 ya pasó, así que hoy no se vuelve a intentar sola." in r.stdout)


def test_el_acceso_deja_el_log_que_mira_la_tarea_de_las_0930(pc):
    """Si ella actualizo a las 08:40, a las 09:30 no se calcula de nuevo."""
    pc.correr("actualizar_plataforma.ps1", "-SinRobot", "-SinPausa")
    (pc.raiz / "tarea_diaria_llamada.txt").unlink()

    pc.correr("tarea_si_no_corrio_hoy.ps1")

    assert not pc.motor_llamado


def test_dos_ventanas_del_acceso_no_trabajan_a_la_vez(pc):
    ventana = _ventana_del_acceso(pc, 60)
    try:
        r = pc.correr("actualizar_plataforma.ps1", "-SinRobot", "-SinPausa")
    finally:
        ventana.kill()

    assert r.returncode == 1
    assert "Ya hay otra ventana de 'Actualizar plataforma' trabajando" in r.stdout
    assert not pc.motor_llamado


def test_el_acceso_suelta_su_candado_al_terminar(pc):
    """Si quedara, la tarea de las 09:30 esperaria a una ventana que ya no trabaja."""
    pc.correr("actualizar_plataforma.ps1", "-SinRobot", "-SinPausa")

    assert pc.motor_llamado
    assert not (pc.raiz / ".actualizar_plataforma.lock").exists()


def test_el_acceso_no_lanza_un_segundo_motor(pc):
    desde = pc.candado(os.getpid())

    r = pc.correr("actualizar_plataforma.ps1", "-SinRobot", "-SinPausa")

    assert r.returncode == 1
    assert f"El motor ya está calculando en este PC (desde {desde})" in r.stdout
    assert not pc.motor_llamado


def test_el_acceso_no_corre_mientras_se_instala_una_version_nueva_del_motor(pc):
    agente = _actualizando_motor(pc, 60)
    try:
        r = pc.correr("actualizar_plataforma.ps1", "-SinRobot", "-SinPausa")
    finally:
        agente.kill()

    assert r.returncode == 1
    assert "se está instalando una versión nueva del motor" in r.stdout
    assert not pc.motor_llamado
    assert not (pc.raiz / ".actualizar_plataforma.lock").exists()


# El motor falso para correr el tarea_diaria.ps1 de verdad: escribe sin acomodar la
# codificacion, como el motor real.
_MOTOR_CON_TILDES = """\
import sys
print("  DESACTUALIZADO: stock_bodegas (lleg\\u00f3 vac\\u00edo)")
print("ERROR: Un archivo lleg\\u00f3 vac\\u00edo o incompleto (respaldo del a\\u00f1o)")
sys.exit(1)
"""


def test_el_acceso_y_el_log_muestran_las_tildes_del_motor(pc):
    """Sin PYTHONIOENCODING, Python escribia en Windows-1252 y PowerShell lo leia en la
    pagina de la consola: la ventana y el log decian 'lleg¾ vacÝo' y 'a±o'."""
    shutil.copy2(SCRIPTS / "tarea_diaria.ps1", pc.raiz / "scripts" / "tarea_diaria.ps1")
    api = pc.raiz / "apps" / "api"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(api / ".venv")],
                   check=True, timeout=120)
    (api / "src" / "jobs").mkdir(parents=True)
    (api / "src" / "__init__.py").write_text("")
    (api / "src" / "jobs" / "__init__.py").write_text("")
    (api / "src" / "jobs" / "correr_motor_real.py").write_text(_MOTOR_CON_TILDES, encoding="utf-8")
    # Como la tarea de Windows: sin las variables con que corren estas pruebas.
    entorno = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}

    r = pc.correr("actualizar_plataforma.ps1", "-SinRobot", "-SinPausa", entorno=entorno)

    assert r.returncode == 1
    assert "ERROR: Un archivo llegó vacío o incompleto (respaldo del año)" in r.stdout
    log = pc.log.read_text(encoding="utf-8-sig")
    assert "DESACTUALIZADO: stock_bodegas (llegó vacío)" in log
    assert "RESULTADO: FALLO (codigo 1)" in log


# --- Codificacion de los scripts --------------------------------------------------


def test_el_instalador_de_doble_clic_es_ascii_con_crlf():
    """cmd.exe lee el .cmd en la pagina de codigos de la consola (las tildes salen
    rotas) y con saltos de linea Unix puede saltarse lineas o etiquetas. Se manda
    suelto por correo, asi que tiene que estar bien sin pasar por git."""
    datos = (SCRIPTS.parent / "INSTALAR PLATAFORMA.cmd").read_bytes()
    assert datos.isascii()
    assert datos.count(b"\n") == datos.count(b"\r\n") > 0
    texto = datos.decode("ascii")
    assert "scripts\\instalar_pc_jefa.ps1" in texto
    assert ("raw.githubusercontent.com/platoniaaa/Sugerencia-SaaS-para-sucursales.-/"
            "arreglar-job-diario/scripts/instalar_pc_jefa.ps1") in texto


@pytest.mark.parametrize("ruta", sorted(SCRIPTS.glob("*.ps1")), ids=lambda p: p.name)
def test_cada_script_es_ascii_o_utf8_con_bom(ruta):
    """Windows PowerShell 5.1 lee como Windows-1252 un .ps1 en UTF-8 sin BOM: una
    tilde en un mensaje llega rota a la pantalla (o a la tarjeta de la web)."""
    datos = ruta.read_bytes()
    assert datos.startswith(b"\xef\xbb\xbf") or datos.isascii(), (
        f"{ruta.name} tiene caracteres fuera de ASCII y no tiene BOM")
