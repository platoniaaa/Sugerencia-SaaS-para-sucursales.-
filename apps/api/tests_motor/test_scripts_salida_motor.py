"""Lo que leen de la salida del motor los scripts que lo corren sin nadie mirando:
`scripts/agente_actualizacion.ps1` (el boton "Actualizar ahora") y
`scripts/tarea_vigentes_ford.ps1`. Las dos funciones viven en
`scripts/salida_motor.ps1` y se prueban con el PowerShell de Windows, el mismo que
usan las tareas programadas.

El caso que cuidan: en un PC que no es el titular, el motor no calcula ni publica y
sale con 0 a proposito. El agente tomaba ese 0 como "OK" y la tarjeta de la web
quedaba en verde sin que se hubiera publicado nada.
"""
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[3] / "scripts"
POWERSHELL = shutil.which("powershell")

pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="necesita el PowerShell de Windows")

NO_TITULAR = [
    "Crudos: C:\\datos\\Bases de datos",
    "  fuentes de datos: se lee con el .env de este PC (configuracion de la plataforma, modo prueba).",
    "NO SE PUBLICA: este PC no es el titular (PC de la jefa)",
]
PUBLICO = [
    "Crudos: C:\\datos\\Bases de datos",
    "CSV generado: C:\\datos\\sugerido_motor.csv",
    "CARGA OFICIAL: 17102 filas.",
]


def _llamar(tmp_path, funcion, lineas):
    """Lo que devuelve `funcion` con esa salida del motor, como texto ('<nulo>' si
    devuelve $null). Corre con $ErrorActionPreference = "Stop", como el agente."""
    entrada = tmp_path / "salida.json"
    entrada.write_text(json.dumps(lineas), encoding="utf-8")
    comando = (
        "$ErrorActionPreference = 'Stop'; "
        f". '{SCRIPTS / 'salida_motor.ps1'}'; "
        f"$salida = Get-Content -Raw -Encoding UTF8 '{entrada}' | ConvertFrom-Json; "
        f"$r = {funcion} $salida; "
        "if ($null -eq $r) { '<nulo>' } else { $r }"
    )
    r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", comando], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_un_pc_que_no_es_el_titular_se_reconoce(tmp_path):
    assert _llamar(tmp_path, "Titular-SiNoPublico", NO_TITULAR) == "PC de la jefa"
    assert _llamar(tmp_path, "Titular-SiNoPublico", PUBLICO) == "<nulo>"


VENCIDOS = [
    "  DESACTUALIZADO: Stock bodegas.xlsx: 3 dias habiles (se espera al dia cada 2)",
    "ERROR: No se carga a produccion con archivos desactualizados.",
    "Archivos vencidos:",
    "  - Stock bodegas.xlsx: 3 dias habiles (se espera al dia cada 2)",
    "  - Seguimiento nacional.xlsx: 4 dias habiles (se espera al dia cada 2)",
    "",
    "Actualizalos en la carpeta de datos, o corre con --ignorar-frescura si sabes que asi corresponde.",
]


def test_los_archivos_que_frenaron_la_carga_se_listan(tmp_path):
    """Los lee el agente para decirle a quien aprieta el boton que bajar. Solo cuenta el
    bloque que sigue al ERROR: la linea DESACTUALIZADO tambien sale para los archivos
    que solo avisan, y esos no son el motivo de una falla cualquiera."""
    assert _llamar(tmp_path, "Archivos-Frenados", VENCIDOS).splitlines() == [
        "Stock bodegas.xlsx: 3 dias habiles (se espera al dia cada 2)",
        "Seguimiento nacional.xlsx: 4 dias habiles (se espera al dia cada 2)"]
    con_fuentes = [l.replace("Archivos vencidos:", "Problemas:") for l in VENCIDOS]
    assert _llamar(tmp_path, "Archivos-Frenados", con_fuentes).splitlines()[0].startswith("Stock bodegas.xlsx")
    solo_avisa = PUBLICO + ["  DESACTUALIZADO: lista_erp.xlsx: 9 dias habiles (se espera al dia cada 7) - no frena la carga"]
    assert _llamar(tmp_path, "Archivos-Frenados", solo_avisa) == "<nulo>"
    assert _llamar(tmp_path, "Archivos-Frenados", NO_TITULAR) == "<nulo>"


def test_las_lineas_de_stdout_en_medio_del_bloque_no_cortan_la_lista(tmp_path):
    """Python vacia stdout recien al salir y PowerShell lee las dos corrientes por
    separado: una linea de stdout puede caer entre los archivos de stderr (pasaba en 4 de
    cada 60 corridas reales) y la lista salia incompleta."""
    mezclada = [VENCIDOS[0], VENCIDOS[1], VENCIDOS[2], VENCIDOS[3],
                "  incidencia dejada en la plataforma (los admin ven la campanita).",
                VENCIDOS[4], "", VENCIDOS[6]]
    assert _llamar(tmp_path, "Archivos-Frenados", mezclada).splitlines() == [
        "Stock bodegas.xlsx: 3 dias habiles (se espera al dia cada 2)",
        "Seguimiento nacional.xlsx: 4 dias habiles (se espera al dia cada 2)"]


def test_las_filas_sin_la_linea_de_carga_no_revientan(tmp_path):
    """Antes: `.Matches.Groups[1]` sobre un resultado nulo, que con "Stop" lanzaba
    "No se puede indizar en una matriz nula" y ese texto llegaba a la tarjeta."""
    assert _llamar(tmp_path, "Filas-Publicadas", PUBLICO) == "17102"
    assert _llamar(tmp_path, "Filas-Publicadas", NO_TITULAR) == "<nulo>"


def _en_curso(raiz, funcion="Corrida-EnCurso", antes="") -> str:
    comando = (
        "$ErrorActionPreference = 'Stop'; "
        f". '{SCRIPTS / 'salida_motor.ps1'}'; {antes}"
        f"$r = {funcion} '{raiz}'; "
        "if ($null -eq $r) { '<nulo>' } else { $r }"
    )
    r = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", comando], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _corrida_en_curso(raiz) -> str:
    return _en_curso(raiz)


def _ahora(minutos=0) -> str:
    """La fecha como la anotan los candados. Un candado se escribe despues de que parte
    su proceso: la fecha de hoy y no una fija (con una fija anterior al arranque del
    proceso, el candado parece de un PID reciclado)."""
    return (dt.datetime.now() + dt.timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S")


def _candado(raiz, pid, desde=None) -> str:
    desde = desde or _ahora()
    (raiz / "apps" / "api" / "data").mkdir(parents=True, exist_ok=True)
    (raiz / "apps" / "api" / "data" / "motor.lock").write_text(f"{pid} {desde}", encoding="utf-8")
    return desde


def _powershell_vivo(segundos=60) -> subprocess.Popen:
    return subprocess.Popen([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
                             f"Start-Sleep -Seconds {segundos}"])


def test_corrida_en_curso_mira_que_el_proceso_del_candado_siga_vivo(tmp_path):
    """La usan el agente, la tarea de las 09:30 y el acceso "Actualizar plataforma"
    para no lanzar un segundo motor (no caben dos en memoria) ni actualizar el
    codigo con uno corriendo. Un candado de un proceso muerto no frena: el motor lo
    pisa al arrancar."""
    import os
    import sys

    assert _corrida_en_curso(tmp_path) == "<nulo>", "sin candado"

    desde = _candado(tmp_path, os.getpid())  # este test corre en Python, como el motor
    assert _corrida_en_curso(tmp_path) == desde

    muerto = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                            capture_output=True, text=True, check=True)
    _candado(tmp_path, int(muerto.stdout))
    assert _corrida_en_curso(tmp_path) == "<nulo>", "proceso que ya termino"

    # Windows recicla los PID: si el numero ahora es de otro programa, no es el motor.
    otro = subprocess.Popen(["cmd", "/c", "ping -n 30 127.0.0.1 >nul"])
    try:
        _candado(tmp_path, otro.pid)
        assert _corrida_en_curso(tmp_path) == "<nulo>"
    finally:
        otro.kill()


def test_un_candado_viejo_con_el_pid_reciclado_no_cuenta(tmp_path):
    """La ventana del acceso se cerro con la X (o se apago el PC) y su candado quedo.
    Windows recicla los PID: si el numero queda en otro PowerShell vivo -el agente
    lanza uno cada minuto, y la tarea de las 09:30 corre en otro- la tarea esperaba 60
    minutos y salia sin calcular. El proceso tiene que haber partido antes de la fecha
    del candado, y quien pregunta nunca es quien lo dejo."""
    lock = tmp_path / ".actualizar_plataforma.lock"

    # El mismo proceso que pregunta (el caso de la tarea de las 09:30).
    propio = f"Set-Content '{lock}' \"$PID {_ahora(-60)}\" -Encoding ascii; "
    assert _en_curso(tmp_path, "Actualizacion-EnCurso", propio) == "<nulo>"

    ventana = _powershell_vivo()
    try:
        lock.write_text(f"{ventana.pid} {_ahora(-60)}", encoding="ascii")
        assert _en_curso(tmp_path, "Actualizacion-EnCurso") == "<nulo>", "partio despues del candado"

        ahora = _ahora()
        lock.write_text(f"{ventana.pid} {ahora}", encoding="ascii")
        assert _en_curso(tmp_path, "Actualizacion-EnCurso") == ahora, "es la ventana que lo dejo"
    finally:
        ventana.kill()

    # Lo mismo con el candado del motor: un Python que partio despues no es esa corrida.
    otro = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        _candado(tmp_path, otro.pid, _ahora(-60))
        assert _corrida_en_curso(tmp_path) == "<nulo>"
    finally:
        otro.kill()


def test_actualizacion_del_motor_en_curso_mira_el_candado_del_agente(tmp_path):
    """La tarea de las 09:30 y el acceso no lanzan el motor mientras el agente hace git
    merge y pip install de un "Actualizar motor"."""
    lock = tmp_path / ".agente.lock"
    assert _en_curso(tmp_path, "ActualizacionMotor-EnCurso") == "<nulo>", "sin candado"

    agente = _powershell_vivo()
    try:
        ahora = _ahora()
        lock.write_text(f"{agente.pid} {ahora} actualizar_motor", encoding="ascii")
        assert _en_curso(tmp_path, "ActualizacionMotor-EnCurso") == ahora

        # Un recalculo no cuenta: ese ya deja el candado del motor.
        lock.write_text(f"{agente.pid} {ahora} recalcular", encoding="ascii")
        assert _en_curso(tmp_path, "ActualizacionMotor-EnCurso") == "<nulo>"
    finally:
        agente.kill()

    muerto = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                            capture_output=True, text=True, check=True)
    lock.write_text(f"{int(muerto.stdout)} {_ahora()} actualizar_motor", encoding="ascii")
    assert _en_curso(tmp_path, "ActualizacionMotor-EnCurso") == "<nulo>", "el agente se corto"

    lock.write_text("", encoding="ascii")  # el de un agente anterior, sin PID
    assert _en_curso(tmp_path, "ActualizacionMotor-EnCurso") == "<nulo>"


def test_los_dos_scripts_miran_si_el_pc_es_el_titular():
    for nombre in ("agente_actualizacion.ps1", "tarea_vigentes_ford.ps1"):
        texto = (SCRIPTS / nombre).read_text(encoding="utf-8-sig")
        assert '. "$PSScriptRoot\\salida_motor.ps1"' in texto, nombre
        assert "Titular-SiNoPublico" in texto, nombre
    agente = (SCRIPTS / "agente_actualizacion.ps1").read_text(encoding="utf-8")
    assert ".Matches.Groups[1]" not in agente
