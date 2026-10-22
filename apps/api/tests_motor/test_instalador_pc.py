"""El instalador del PC nuevo (`scripts/instalar_pc_jefa.ps1`), con `-Simular`.

Corre el script de verdad con el PowerShell de Windows en una carpeta temporal: no
instala programas, no pide claves y no llama a la plataforma (apunta a un puerto de
127.0.0.1 donde no hay nada). El motor se clona desde un "GitHub" armado en la carpeta
del test (un repositorio bare) con lo minimo: un agente_actualizacion.ps1 de mentira,
requirements-motor.txt y un config_fuentes.py falso que anota que lo llamaron. Las librerias del motor son
paquetes vacios con su nombre, y pip no puede salir a internet (PIP_NO_INDEX).

Las corridas completas registran la tarea del agente de Windows con el prefijo "PRUEBA-",
deshabilitada, y el mismo instalador la borra al terminar (como en -Simular a mano).

Lo que cuida:
- Una copia del motor que quedo a medias (se corto la descarga) se aparta y se baja
  de nuevo, sin perder el .env; el codigo se baja en una carpeta al lado y recien al
  final se renombra; git queda con los certificados de Windows (schannel).
- Un entorno de Python sin pip se repara.
- Si no se puede instalar Python, se usa el portable del programa del ERP.
- La configuracion de Fuentes de datos queda guardada al final.
- El resumen dice solo lo que de verdad quedo.
- En el PC de la jefa nada calcula solo: la unica tarea es la del agente, que atiende el
  boton. No hay tarea de las 09:30 ni de al iniciar sesion.
- El programa del ERP ya funciona: el instalador no lo copia, no lo borra ni lo anota.
"""
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import zipfile

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[3] / "scripts"
POWERSHELL = shutil.which("powershell")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(POWERSHELL is None or GIT is None,
                                reason="necesita el PowerShell de Windows y git")

_ENTORNO_GIT = {
    "GIT_AUTHOR_NAME": "Prueba", "GIT_AUTHOR_EMAIL": "prueba@ejemplo.cl",
    "GIT_COMMITTER_NAME": "Prueba", "GIT_COMMITTER_EMAIL": "prueba@ejemplo.cl",
    # Sin la configuracion del PC: el schannel que se revisa es el que deja el instalador.
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}

# El config_fuentes del motor, falso: `--probar --reportar` dice que aviso a la
# plataforma, y `--guardar-config` anota que lo llamaron y falla si se le pide.
_CONFIG_FUENTES_FALSO = """\
import os, pathlib, sys
if "--guardar-config" in sys.argv:
    pathlib.Path(os.environ["INSTALADOR_CONFIG_ANOTA"]).write_text("guardar-config")
    if os.environ.get("INSTALADOR_CONFIG_FALLA"):
        print("Este PC no tiene configuracion de fuentes (ni de la plataforma ni guardada).")
        sys.exit(1)
    print("Configuracion de fuentes en este PC (plataforma): modo prueba, titular PC anterior.")
    sys.exit(0)
if os.environ.get("INSTALADOR_CONFIG_NO_PUBLICA"):
    print("  -> este PC NO publica: no es el titular (PC anterior).")
print("Reporte enviado a la plataforma (tipo probar).")
"""

# Un pip falso que contesta --version e "instala" sin hacer nada.
_PIP_FALSO = """\
import sys
if "--version" in sys.argv:
    print("pip 99.0 (falso)")
sys.exit(0)
"""

_LIBRERIAS = ("polars", "fastexcel", "openpyxl", "httpx", "truststore")


def _git(cwd, *args) -> str:
    r = subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, **_ENTORNO_GIT}, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _venv(destino: pathlib.Path):
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(destino)], check=True, timeout=120)
    for nombre in _LIBRERIAS:
        (destino / "Lib" / "site-packages" / nombre).mkdir(parents=True)
        (destino / "Lib" / "site-packages" / nombre / "__init__.py").write_text("")


def _rueda(carpeta: pathlib.Path, nombre: str):
    """Una rueda vacia con el nombre de una libreria del motor: con PIP_NO_INDEX y
    PIP_FIND_LINKS apuntando aca, un pip de verdad "instala" las librerias sin internet."""
    info = f"{nombre}-0.0.1.dist-info"
    archivos = {
        f"{nombre}/__init__.py": "",
        f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {nombre}\nVersion: 0.0.1\n",
        f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: prueba\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    archivos[f"{info}/RECORD"] = "".join(f"{a},,\n" for a in archivos) + f"{info}/RECORD,,\n"
    with zipfile.ZipFile(carpeta / f"{nombre}-0.0.1-py3-none-any.whl", "w") as z:
        for ruta, texto in archivos.items():
            z.writestr(ruta, texto)


@pytest.fixture(scope="module")
def origen(tmp_path_factory):
    """El "GitHub" del motor (rama principal, y otra sin requirements-motor.txt para que
    el instalador frene apenas termina el paso 2) y dos entornos de Python: uno sin pip
    y otro con el pip falso. Se arma una vez."""
    base = tmp_path_factory.mktemp("origen-instalador")
    github, publica = base / "github.git", base / "publica"
    _git(base, "init", "-q", "--bare", "-b", "principal", str(github))
    _git(base, "clone", "-q", str(github), str(publica))
    _git(publica, "checkout", "-q", "-b", "principal")
    (publica / "scripts").mkdir()
    (publica / "scripts" / "agente_actualizacion.ps1").write_text("# agente de prueba\n")
    api = publica / "apps" / "api"
    (api / "src" / "motor").mkdir(parents=True)
    (api / "requirements-motor.txt").write_text("".join(f"{n}\n" for n in _LIBRERIAS))
    (api / "src" / "__init__.py").write_text("")
    (api / "src" / "motor" / "__init__.py").write_text("")
    (api / "src" / "motor" / "config_fuentes.py").write_text(_CONFIG_FUENTES_FALSO)
    (publica / ".gitignore").write_text("logs/\n.env\napps/api/.venv/\napps/api/data/\n")
    _git(publica, "add", ".")
    _git(publica, "commit", "-q", "-m", "motor")
    _git(publica, "push", "-q", "-u", "origin", "principal")
    _git(publica, "checkout", "-q", "-b", "sin-requisitos")
    _git(publica, "rm", "-q", "apps/api/requirements-motor.txt")
    _git(publica, "commit", "-q", "-m", "sin requirements")
    _git(publica, "push", "-q", "-u", "origin", "sin-requisitos")

    (base / "ruedas").mkdir()
    for nombre in _LIBRERIAS:
        _rueda(base / "ruedas", nombre)

    _venv(base / "venv-sin-pip")
    shutil.copytree(base / "venv-sin-pip", base / "venv-pip-falso")
    pip = base / "venv-pip-falso" / "Lib" / "site-packages" / "pip"
    pip.mkdir()
    (pip / "__init__.py").write_text("")
    (pip / "__main__.py").write_text(_PIP_FALSO)
    return base


def _puerto_cerrado() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()
    return puerto


def _entorno(tmp_path, origen, **extra) -> dict:
    return {**os.environ, **_ENTORNO_GIT, "PIP_NO_INDEX": "1", "PIP_FIND_LINKS": str(origen / "ruedas"),
            "INSTALADOR_CONFIG_ANOTA": str(tmp_path / "config_fuentes_llamado.txt"), **extra}


def _sin_python(tmp_path, origen, **extra) -> dict:
    """Un PC donde no hay Python y winget no puede instalarlo: ni en el PATH, ni en
    las carpetas de siempre."""
    vacia = tmp_path / "sin-python"
    vacia.mkdir()
    windows = os.environ["SystemRoot"]
    # El git de la carpeta cmd: el de mingw64\bin, solo en el PATH, se cae al clonar.
    git = pathlib.Path(GIT)
    git_cmd = next((str(p / "cmd") for p in git.parents if (p / "cmd" / "git.exe").exists()), str(git.parent))
    return _entorno(tmp_path, origen, LOCALAPPDATA=str(vacia), ProgramFiles=str(vacia),
                    PATH=os.pathsep.join([git_cmd, windows + "\\System32",
                                          windows + "\\System32\\WindowsPowerShell\\v1.0", windows]),
                    **extra)


def _instalar(sim, origen, *args, rama="principal", entorno) -> subprocess.CompletedProcess:
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(SCRIPTS / "instalar_pc_jefa.ps1"), "-Simular", "-CarpetaSimulacion", str(sim),
         "-Origen", str(origen / "github.git"), "-Rama", rama,
         "-ApiUrl", f"http://127.0.0.1:{_puerto_cerrado()}", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, env=entorno)


def _destino(sim) -> pathlib.Path:
    return sim / "perfil" / "dev" / "Sugerencia-SaaS-para-sucursales"


def _clonado(tmp_path, origen, venv: str) -> pathlib.Path:
    """Un PC donde el motor ya se habia instalado (se vuelve a correr el instalador)."""
    sim = tmp_path / "sim"
    destino = _destino(sim)
    _git(tmp_path, "clone", "-q", "-b", "principal", str(origen / "github.git"), str(destino))
    shutil.copytree(origen / venv, destino / "apps" / "api" / ".venv")
    return sim


def _resumen(salida: str) -> tuple[list[str], list[str]]:
    """Las lineas de "Quedó listo" y las de "Falta" del resumen final."""
    resumen = salida.split(" Resumen", 1)[1]
    listo = resumen.split("Quedó listo:", 1)[1].split("Falta:", 1)[0].split("Qué hacer ahora:", 1)[0]
    falta = resumen.split("Falta:", 1)[1].split("Qué hacer ahora:", 1)[0] if "Falta:" in resumen else ""
    limpiar = lambda texto: [l.strip() for l in texto.splitlines() if l.strip()]
    return limpiar(listo), limpiar(falta)


# --- Paso 2: el codigo ------------------------------------------------------------


def test_una_copia_cortada_a_mitad_se_aparta_y_se_baja_de_nuevo(tmp_path, origen):
    """Se cerro la ventana mientras decia "Bajando el código": quedo un .git sin la
    version. Antes el instalador decia "Ya está", despues "hay archivos cambiados a
    mano" (git status respondio 'bad object HEAD') y se caia con un error rojo al
    revisar los scripts, en cada reintento."""
    sim = tmp_path / "sim"
    destino = _destino(sim)
    _git(tmp_path, "init", "-q", "-b", "principal", str(destino))
    (destino / ".git" / "refs" / "heads" / "principal").write_text("0123456789abcdef0123456789abcdef01234567\n")
    (destino / "README.md").write_text("a medias\n")
    (destino / ".env").write_bytes(b"PLATAFORMA_EMAIL=motor@ejemplo.cl\n")

    r = _instalar(sim, origen, rama="sin-requisitos", entorno=_entorno(tmp_path, origen))

    assert "no sirve (no tiene una versión completa)" in r.stdout, r.stdout + r.stderr
    assert "cambiados a mano" not in r.stdout
    # Paso el paso 2 y frena en el 3 porque esa rama de prueba no trae requirements.
    assert "no trae requirements-motor.txt" in r.stdout
    assert _git(destino, "rev-parse", "--abbrev-ref", "HEAD") == "sin-requisitos"
    assert (destino / "scripts" / "agente_actualizacion.ps1").exists()
    apartadas = list(destino.parent.glob("Sugerencia-SaaS-para-sucursales-danada-*"))
    assert len(apartadas) == 1 and (apartadas[0] / "README.md").exists()
    assert (destino / ".env").read_text() == "PLATAFORMA_EMAIL=motor@ejemplo.cl\n", "no se pierden las claves"
    assert not list(destino.parent.glob("*.bajando")), "la carpeta temporal del clon se renombra"
    assert _git(destino, "config", "--local", "http.sslBackend") == "schannel"


def _python_portable(carpeta: pathlib.Path):
    """Un python\\python.exe como el del kit del programa del ERP: el lanzador de un
    entorno, puesto al lado de su pyvenv.cfg. Trae venv y ensurepip."""
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(carpeta)], check=True, timeout=120)
    shutil.copy2(carpeta / "Scripts" / "python.exe", carpeta / "python.exe")


def test_si_no_se_puede_instalar_python_usa_el_del_programa_del_erp(tmp_path, origen):
    """En un PC que bloquea instaladores winget no puede instalar Python, pero el kit
    del programa del ERP trae uno portable que sirve. Antes el instalador frenaba con
    "No hay Python en este PC"."""
    sim = tmp_path / "sim"
    kit = sim / "perfil" / "Escritorio" / "INSTALAR_EN_PC_JEFA" / "automatizacion"
    _python_portable(kit / "python")
    r = _instalar(sim, origen, rama="sin-requisitos", entorno=_sin_python(tmp_path, origen))

    assert "No hay Python en este PC" not in r.stdout, r.stdout + r.stderr
    assert "se usa el que trae el programa del ERP" in r.stdout
    assert f"Python 3.{sys.version_info.minor}: {kit / 'python' / 'python.exe'}" in r.stdout
    assert "Código listo (rama sin-requisitos" in r.stdout


# --- Corridas completas -----------------------------------------------------------


def test_un_entorno_sin_pip_se_repara_y_la_configuracion_queda_guardada(tmp_path, origen):
    """`python -m venv` tarda unos 15 s porque instala pip: si se cerraba la ventana en
    ese rato, cada reintento frenaba con "Casi siempre es la conexión ... No module named
    pip". Y al final, la configuracion de Fuentes de datos queda guardada: sin ella, si la
    plataforma no respondia en su primera corrida, el PC nuevo se creia titular."""
    sim = _clonado(tmp_path, origen, "venv-sin-pip")
    destino = _destino(sim)

    r = _instalar(sim, origen, entorno=_entorno(tmp_path, origen))

    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    assert "le falta pip" in r.stdout
    assert "No module named pip" not in r.stdout
    pip = subprocess.run([destino / "apps" / "api" / ".venv" / "Scripts" / "python.exe", "-m", "pip", "--version"],
                         capture_output=True, text=True)
    assert pip.returncode == 0, pip.stderr
    assert (tmp_path / "config_fuentes_llamado.txt").read_text() == "guardar-config"
    assert "Configuración de Fuentes de datos guardada en este PC" in r.stdout
    # Una copia que ya estaba (la clonó otro instalador) queda igual con schannel.
    assert _git(destino, "config", "--local", "http.sslBackend") == "schannel"


def test_el_resumen_dice_solo_lo_que_quedo(tmp_path, origen):
    """Si la configuracion de Fuentes de datos no se pudo traer, va en "Falta". Y el
    resumen no promete nada del programa del ERP ni de un acceso del Escritorio: el
    instalador ya no los toca."""
    sim = _clonado(tmp_path, origen, "venv-pip-falso")

    r = _instalar(sim, origen, entorno=_entorno(tmp_path, origen, INSTALADOR_CONFIG_FALLA="1"))

    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    listo, falta = _resumen(r.stdout)
    assert any(l.startswith("- El motor en ") for l in listo), listo
    assert any(l.startswith("- La tarea del agente") for l in listo), listo
    assert not any("Actualizar plataforma" in l for l in listo), listo
    assert not any("programa del ERP" in l for l in falta), falta
    assert any("guarde la configuración de Fuentes de datos" in l for l in falta), falta
    assert "Actualizar plataforma" not in r.stdout
    assert "[6/6] Prueba final" in r.stdout


def test_el_resumen_pide_dejar_el_pc_como_titular_solo_si_no_lo_es(tmp_path, origen):
    """El pedido de "deje este PC como titular" sale solo cuando el motor dice que no
    publica. Al reinstalar en el PC que ya lo es, estaba de mas."""
    sim = _clonado(tmp_path, origen, "venv-pip-falso")
    r = _instalar(sim, origen, entorno=_entorno(tmp_path, origen, INSTALADOR_CONFIG_NO_PUBLICA="1"))
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    listo, _ = _resumen(r.stdout)
    assert any("todavía no es el titular" in l for l in listo), listo
    assert "Pídele a un admin que" in r.stdout


def test_si_el_motor_no_dice_que_no_publica_el_resumen_no_pide_dejarlo_titular(tmp_path, origen):
    sim = _clonado(tmp_path, origen, "venv-pip-falso")
    r = _instalar(sim, origen, entorno=_entorno(tmp_path, origen))
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    listo, _ = _resumen(r.stdout)
    assert not any("todavía no es el titular" in l for l in listo), listo
    assert "Pídele a un admin que" not in r.stdout
    assert "si este PC es el titular" in r.stdout


def test_el_instalador_solo_registra_la_tarea_del_agente():
    """Prueba estatica: si alguien vuelve a poner una tarea que calcule sola, el texto
    del script la delata aunque la simulacion no la ejerza."""
    texto = (SCRIPTS / "instalar_pc_jefa.ps1").read_text(encoding="utf-8-sig")
    assert texto.count("Register-ScheduledTask") == 1
    for viejo in ("tarea_diaria", "tarea_si_no_corrio_hoy", "tarea_al_iniciar_sesion", "CreateShortcut",
                  "ROBOT_ERP_DIR", "New-ScheduledTaskTrigger -Daily"):
        assert viejo not in texto, viejo


def test_no_deja_ninguna_tarea_que_calcule_sola(tmp_path, origen):
    """En el PC de la jefa el sugerido se calcula cuando alguien aprieta el boton. La
    unica tarea es el agente (pregunta a la plataforma cada minuto): sin el disparador
    diario de las 09:30 y sin la tarea de al iniciar sesion que recupera la corrida."""
    sim = _clonado(tmp_path, origen, "venv-pip-falso")

    r = _instalar(sim, origen, entorno=_entorno(tmp_path, origen))

    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    xmls = sorted(p.name for p in (sim / "tareas").glob("*.xml"))
    assert xmls == ["Sugerido Curifor - Agente.xml"], xmls
    xml = (sim / "tareas" / xmls[0]).read_text(encoding="utf-8-sig")
    assert "agente_actualizacion.ps1" in xml
    assert "<LogonTrigger>" in xml and "<TimeTrigger>" in xml
    assert "<CalendarTrigger>" not in xml, "no hay disparador diario"
    assert "tarea_si_no_corrio_hoy" not in xml and "tarea_diaria" not in xml
    assert not (sim / "perfil" / "Escritorio" / "Actualizar plataforma.lnk").exists()
    assert "[5/6] Tarea de Windows (el agente)" in r.stdout
    assert "Tareas de prueba borradas" in r.stdout


def test_no_toca_el_programa_del_erp_aunque_este_en_onedrive(tmp_path, origen):
    """El programa del ERP de la jefa ya funciona. Aunque el kit este en un Escritorio que
    OneDrive respalda, el instalador no lo copia, no lo borra ni lo anota en el .env."""
    sim = _clonado(tmp_path, origen, "venv-pip-falso")
    kit = sim / "perfil" / "OneDrive - Curifor S.A" / "Escritorio" / "INSTALAR_EN_PC_JEFA" / "automatizacion"
    kit.mkdir(parents=True)
    (kit / "panel.bat").write_text("@echo off")
    (kit / "flexline_flows.py").write_text("print('no se corre')")
    (kit / ".env").write_text("CLAVE_DE_PRUEBA=ficticia")
    zip_kit = kit.parent / "automatizacion.zip"
    zip_kit.write_text("zip de prueba")

    r = _instalar(sim, origen, entorno=_entorno(tmp_path, origen))

    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    assert (kit / "flexline_flows.py").exists() and (kit / "panel.bat").exists()
    assert (kit / ".env").read_text() == "CLAVE_DE_PRUEBA=ficticia"
    assert zip_kit.exists()
    assert not (sim / "perfil" / "automatizacion").exists(), "no se copia a otra carpeta"
    assert "ROBOT_ERP_DIR" not in (_destino(sim) / ".env").read_text(encoding="utf-8")
    assert "dentro de OneDrive" not in r.stdout


def test_si_el_motor_usa_el_python_del_kit_en_onedrive_el_kit_queda_donde_esta(tmp_path, origen):
    """El PC bloquea instaladores y el kit del programa del ERP esta en un Escritorio que
    OneDrive respalda: el entorno del motor se arma con el Python del kit y esa carpeta no
    se mueve ni se borra (antes se copiaba afuera y se rearmaba el entorno)."""
    sim = tmp_path / "sim"
    kit = sim / "perfil" / "OneDrive - Curifor S.A" / "Escritorio" / "INSTALAR_EN_PC_JEFA" / "automatizacion"
    _python_portable(kit / "python")

    r = _instalar(sim, origen, entorno=_sin_python(tmp_path, origen))

    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    assert "se usa el que trae el programa del ERP" in r.stdout
    assert "se arma de nuevo su entorno" not in r.stdout
    assert (kit / "python" / "python.exe").exists()
    # El entorno queda atado a esa carpeta: el resumen lo dice en "Falta".
    _, falta = _resumen(r.stdout)
    assert any("no muevas ni borres esa carpeta" in l for l in falta), falta
    venv_py = _destino(sim) / "apps" / "api" / ".venv" / "Scripts" / "python.exe"
    prueba = subprocess.run([venv_py, "-c", "import polars, fastexcel, openpyxl, httpx, truststore; print('ok')"],
                            capture_output=True, text=True)
    assert prueba.stdout.strip() == "ok", prueba.stderr
