"""El agente del PC del motor (`scripts/agente_actualizacion.ps1`), de punta a punta.

Corre el script de verdad con el PowerShell de Windows (el mismo de la tarea
programada) contra una plataforma falsa en 127.0.0.1 y un repositorio de Git armado
en la carpeta temporal del test, con su propio "GitHub" (un repositorio bare). No
toca la plataforma de verdad, ni GitHub, ni el repo del motor.

Lo que cuida:
- "Actualizar motor" (tipo `actualizar_motor`): avanza la rama solo si se puede
  avanzar rapido, se niega con una corrida en curso o con cambios a mano, reinstala
  las librerias si cambiaron y vuelve atras si no se pudieron instalar. Nunca corre
  el motor.
- "Actualizar ahora" (tipo `recalcular`, y sin tipo para la plataforma de antes).
- Que lo que llega a la tarjeta de la web sea UTF-8 valido: PowerShell 5.1 mandaba
  el cuerpo en ISO-8859-1 y la plataforma lo rechazaba apenas habia una tilde.
- Que un aviso del motor en stderr no corte la corrida (con "Stop", PowerShell 5.1
  lo convertia en excepcion y esa linea llegaba sola a la tarjeta).

Cada corrida del agente lanza PowerShell y unas diez llamadas a git: en un PC con
antivirus son 10 a 20 segundos. Por eso los casos van agrupados y el repositorio y el
entorno de Python se arman una sola vez y se copian.
"""
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[3] / "scripts"
POWERSHELL = shutil.which("powershell")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(POWERSHELL is None or GIT is None,
                                reason="necesita el PowerShell de Windows y git")

SECRETO = "secreto-de-prueba"


# --- La plataforma falsa ----------------------------------------------------------


class _Plataforma:
    """Lo minimo del buzon: /pendiente entrega lo encolado y /terminar lo anota."""

    def __init__(self):
        self.cola: list[dict] = []
        self.reportes: list[dict] = []
        # /terminar responde 503 estas veces antes de recibir (Render reiniciandose).
        self.terminar_caida = 0
        self.intentos_terminar = 0
        plataforma = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, codigo, obj):
                b = json.dumps(obj).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if self.headers.get("X-Agente-Secret") != SECRETO:
                    return self._json(403, {"detail": "No autorizado"})
                if self.path.startswith("/api/actualizacion/pendiente"):
                    if not plataforma.cola:
                        return self._json(200, {"hay": False})
                    return self._json(200, {"hay": True, **plataforma.cola.pop(0)})
                return self._json(404, {"detail": "Not Found"})

            def do_POST(self):
                crudo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.headers.get("X-Agente-Secret") != SECRETO:
                    return self._json(403, {"detail": "No autorizado"})
                plataforma.intentos_terminar += 1
                if plataforma.terminar_caida > 0:
                    plataforma.terminar_caida -= 1
                    return self._json(503, {"detail": "Service Unavailable"})
                try:
                    datos = json.loads(crudo.decode("utf-8"))  # como FastAPI: UTF-8 o nada
                except (UnicodeDecodeError, ValueError):
                    plataforma.reportes.append({"invalido": crudo.hex()})
                    return self._json(422, {"detail": "There was an error parsing the body"})
                if str(datos.get("id", "")).startswith("borrada-"):
                    return self._json(404, {"detail": "Solicitud no encontrada"})
                plataforma.reportes.append(datos)
                return self._json(200, {"id": datos.get("id"), "estado": "ok"})

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def pedir(self, tipo: str | None) -> str:
        s = {"id": str(uuid.uuid4()), "solicitado_por": "admin@ejemplo.cl"}
        if tipo is not None:
            s["tipo"] = tipo
        self.cola.append(s)
        return s["id"]

    def reporte(self, id_solicitud) -> dict:
        assert self.reportes, "el agente no reporto nada"
        r = self.reportes[-1]
        assert "invalido" not in r, f"el cuerpo no era UTF-8 valido: {r}"
        assert r["id"] == id_solicitud
        return r


@pytest.fixture(scope="module")
def _servidor():
    p = _Plataforma()
    yield p
    p.servidor.shutdown()


@pytest.fixture
def plataforma(_servidor):
    _servidor.cola.clear()
    _servidor.reportes.clear()
    _servidor.terminar_caida = 0
    _servidor.intentos_terminar = 0
    return _servidor


# --- El PC con el motor clonado ---------------------------------------------------

_ENTORNO_GIT = {
    "GIT_AUTHOR_NAME": "Prueba", "GIT_AUTHOR_EMAIL": "prueba@ejemplo.cl",
    "GIT_COMMITTER_NAME": "Prueba", "GIT_COMMITTER_EMAIL": "prueba@ejemplo.cl",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(cwd, *args) -> str:
    r = subprocess.run([GIT, *args], cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, **_ENTORNO_GIT}, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


# Un pip falso: anota con que lo llamaron y falla si el agente le pasa PIP_FALSO_FALLA
# (el agente hereda el entorno del test). El de verdad tarda 40 s en instalarse aca.
# Anota tambien el candado del agente tal como esta mientras reinstala.
_PIP_FALSO = """\
import os, sys, pathlib
pathlib.Path(os.environ["PIP_FALSO_ANOTA"]).write_text(" ".join(sys.argv[1:]))
if os.environ.get("PIP_FALSO_CANDADO"):
    candado = pathlib.Path(os.environ["PIP_FALSO_CANDADO"])
    pathlib.Path(os.environ["PIP_FALSO_ANOTA"] + ".candado").write_text(
        candado.read_text() if candado.exists() else "(sin candado)")
if os.environ.get("PIP_FALSO_FALLA"):
    print("ERROR: No matching distribution found for polars==9.9.9")
    sys.exit(1)
print("Successfully installed httpx-0.28.2")
"""


@pytest.fixture(scope="module")
def _plantilla(tmp_path_factory):
    """El "GitHub" (bare), el clon desde donde se publican versiones y el clon del
    PC, mas un entorno de Python sin pip (con el pip falso). Se arma una vez."""
    base = tmp_path_factory.mktemp("plantilla")
    origen, otro, pc = base / "github.git", base / "publica", base / "pc"
    _git(base, "init", "--bare", "-b", "principal", str(origen))
    _git(base, "clone", str(origen), str(otro))
    _git(otro, "checkout", "-b", "principal")
    (otro / "scripts").mkdir()
    for nombre in ("agente_actualizacion.ps1", "salida_motor.ps1"):
        shutil.copy2(SCRIPTS / nombre, otro / "scripts" / nombre)
    (otro / "apps" / "api").mkdir(parents=True)
    (otro / "apps" / "api" / "requirements-motor.txt").write_text("httpx==0.28.1\n")
    (otro / "LEEME.txt").write_text("version 1\n")
    (otro / ".gitignore").write_text("logs/\n.env\n.agente.lock\napps/api/.venv/\napps/api/data/\n")
    _git(otro, "add", ".")
    _git(otro, "commit", "-m", "version 1")
    _git(otro, "push", "-u", "origin", "principal")
    _git(base, "clone", "-b", "principal", str(origen), str(pc))

    venv = base / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, timeout=120)
    (venv / "Lib" / "site-packages" / "pip").mkdir()
    (venv / "Lib" / "site-packages" / "pip" / "__init__.py").write_text("")
    (venv / "Lib" / "site-packages" / "pip" / "__main__.py").write_text(_PIP_FALSO)
    return base


class _Pc:
    def __init__(self, plantilla: pathlib.Path, destino: pathlib.Path, url: str):
        shutil.copytree(plantilla, destino, dirs_exist_ok=True, ignore=shutil.ignore_patterns("venv"))
        for clon in ("pc", "publica"):  # el remoto apuntaba al "GitHub" de la plantilla
            cfg = destino / clon / ".git" / "config"
            nuevo = (destino / "github.git").as_posix()
            cfg.write_text(re.sub(r"(?m)^(\s*url = ).*github\.git\s*$",
                                  lambda m: m.group(1) + nuevo, cfg.read_text()))
        self.plantilla = plantilla
        self.raiz = destino / "pc"
        self.otro = destino / "publica"
        self.entorno = {**os.environ, **_ENTORNO_GIT,
                        "PIP_FALSO_ANOTA": str(destino / "pip_llamado.txt")}
        self.pip_llamado = destino / "pip_llamado.txt"
        # .env sin BOM, como lo escribe instalar_pc_jefa.ps1, con una tilde en una ruta.
        (self.raiz / ".env").write_bytes(
            f"PLATAFORMA_API_URL={url}\nAGENTE_SECRET={SECRETO}\n"
            "MOTOR_STOCK_DIR=C:\\OneDrive\\Abastecimiento y Logística-Data BI - Datos\n".encode("utf-8"))

    def sha(self, donde=None) -> str:
        return _git(donde or self.raiz, "rev-parse", "--short", "HEAD")

    def publicar(self, archivo: str, contenido: str, mensaje: str) -> str:
        """Una version nueva en GitHub, hecha desde otro clon."""
        ruta = self.otro / archivo
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido)
        _git(self.otro, "add", archivo)
        _git(self.otro, "commit", "-m", mensaje)
        _git(self.otro, "push", "origin", "principal")
        return self.sha(self.otro)

    def venv(self, motor: str | None = None):
        """El entorno de Python de la plantilla y, si se pide, un motor falso."""
        shutil.copytree(self.plantilla / "venv", self.raiz / "apps" / "api" / ".venv")
        if motor is not None:
            jobs = self.raiz / "apps" / "api" / "src" / "jobs"
            jobs.mkdir(parents=True)
            (self.raiz / "apps" / "api" / "src" / "__init__.py").write_text("")
            (jobs / "__init__.py").write_text("")
            (jobs / "correr_motor_real.py").write_text(motor, encoding="utf-8")

    def candado_del_motor(self, pid: int) -> str:
        """Con la fecha de ahora: un candado se escribe despues de que parte su proceso
        (con una fecha anterior, parece de un PID reciclado)."""
        desde = _ahora()
        data = self.raiz / "apps" / "api" / "data"
        data.mkdir(parents=True, exist_ok=True)
        (data / "motor.lock").write_text(f"{pid} {desde}", encoding="utf-8")
        return desde

    def agente(self, *args, **entorno) -> subprocess.CompletedProcess:
        r = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(self.raiz / "scripts" / "agente_actualizacion.ps1"), "-Verboso", *args],
            capture_output=True, text=True, timeout=180, env={**self.entorno, **entorno})
        assert r.returncode == 0, r.stdout + r.stderr
        return r

    def log(self) -> str:
        return next((self.raiz / "logs").glob("agente_*.log")).read_text(encoding="utf-8-sig")

    @property
    def log_motor(self) -> pathlib.Path:
        return self.raiz / "logs" / f"motor_{dt.date.today():%Y-%m-%d}.log"


def _ahora(minutos: int = 0) -> str:
    return (dt.datetime.now() + dt.timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
def pc(tmp_path, plataforma, _plantilla):
    return _Pc(_plantilla, tmp_path / "caso", plataforma.url)


# --- Actualizar motor -------------------------------------------------------------


def test_actualizar_motor_avanza_y_la_segunda_vez_dice_que_esta_al_dia(pc, plataforma):
    antes = pc.sha()
    pc.publicar("LEEME.txt", "version 2\n", "version 2")
    nueva = pc.publicar("LEEME.txt", "version 3\n", "version 3")
    # Lo que no esta versionado (notas, logs, el .env) no cuenta como cambio a mano.
    (pc.raiz / "notas_sueltas.txt").write_text("archivo sin versionar\n")
    sid = plataforma.pedir("actualizar_motor")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is True
    assert r["mensaje"] == f"Motor actualizado de {antes} a {nueva} (2 cambios)."
    assert r["version"] == f"{nueva} principal"
    assert pc.sha() == nueva
    assert (pc.raiz / "LEEME.txt").read_text() == "version 3\n"
    assert not pc.pip_llamado.exists(), "sin cambios de librerias no se toca pip"

    sid = plataforma.pedir("actualizar_motor")
    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is True
    assert r["mensaje"] == f"El motor ya estaba al día ({nueva})."


def test_con_una_corrida_en_curso_no_se_actualiza(pc, plataforma):
    """El candado lo deja el motor con su PID. Este test corre en Python: su PID es
    el de un proceso Python vivo, igual que una corrida de verdad."""
    antes = pc.sha()
    pc.publicar("LEEME.txt", "version 2\n", "version 2")
    desde = pc.candado_del_motor(os.getpid())
    sid = plataforma.pedir("actualizar_motor")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert "está calculando" in r["mensaje"] and desde in r["mensaje"]
    assert pc.sha() == antes


def test_con_cambios_hechos_a_mano_no_se_actualiza(pc, plataforma):
    antes = pc.sha()
    pc.publicar("LEEME.txt", "version 2\n", "version 2")
    (pc.raiz / "LEEME.txt").write_text("editado a mano\n")
    sid = plataforma.pedir("actualizar_motor")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert "cambios hechos a mano (LEEME.txt)" in r["mensaje"]
    assert pc.sha() == antes
    assert (pc.raiz / "LEEME.txt").read_text() == "editado a mano\n"


def test_si_la_rama_se_separo_de_github_no_se_fuerza(pc, plataforma):
    pc.publicar("LEEME.txt", "version 2 en GitHub\n", "version 2")
    (pc.raiz / "LEEME.txt").write_text("version 2 en el PC\n")
    _git(pc.raiz, "commit", "-am", "commit hecho en el PC")
    local = pc.sha()
    sid = plataforma.pedir("actualizar_motor")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert "no puede avanzar sola" in r["mensaje"]
    assert pc.sha() == local


def test_un_archivo_sin_versionar_que_la_version_nueva_trae_se_explica(pc, plataforma):
    """Es el caso del PC del dueño: tarea_al_iniciar_sesion.ps1 existe sin versionar y
    la rama nueva lo trae."""
    antes = pc.sha()
    pc.publicar("scripts/tarea_al_iniciar_sesion.ps1", "# version de GitHub\n", "tarea nueva")
    (pc.raiz / "scripts" / "tarea_al_iniciar_sesion.ps1").write_text("# copia local\n")
    sid = plataforma.pedir("actualizar_motor")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert "(scripts/tarea_al_iniciar_sesion.ps1)" in r["mensaje"]
    assert "moverlos o borrarlos" in r["mensaje"]
    assert pc.sha() == antes


def test_si_cambiaron_las_librerias_se_reinstalan(pc, plataforma):
    pc.venv()
    nueva = pc.publicar("apps/api/requirements-motor.txt", "httpx==0.28.2\n", "sube httpx")
    sid = plataforma.pedir("actualizar_motor")

    pc.agente(PIP_FALSO_CANDADO=str(pc.raiz / ".agente.lock"))

    r = plataforma.reporte(sid)
    assert r["ok"] is True, r
    assert r["mensaje"].endswith("(1 cambios). Se instalaron las librerías nuevas.")
    assert pc.sha() == nueva
    llamado = pc.pip_llamado.read_text()
    assert llamado.startswith("install ") and llamado.endswith("requirements-motor.txt")
    # Mientras reinstala, su candado dice quien es y que hace: la tarea de las 09:30 y
    # el acceso "Actualizar plataforma" esperan (ActualizacionMotor-EnCurso).
    candado = pathlib.Path(str(pc.pip_llamado) + ".candado").read_text().strip()
    assert re.fullmatch(r"\d+ \d{4}-\d\d-\d\d \d\d:\d\d:\d\d actualizar_motor", candado), candado
    assert not (pc.raiz / ".agente.lock").exists(), "lo suelta al terminar"


def test_actualizar_motor_baja_de_github_con_los_certificados_de_windows(pc, plataforma, tmp_path):
    """La red de la empresa revisa las conexiones seguras con un certificado que Windows
    conoce y el ca-bundle de OpenSSL no: con un Git que use OpenSSL, el fetch fallaba con
    'SSL certificate problem' y el mensaje pedia revisar internet."""
    pc.publicar("LEEME.txt", "version 2\n", "version 2")
    traza = tmp_path / "git_trace2.txt"
    sid = plataforma.pedir("actualizar_motor")

    pc.agente(GIT_TRACE2=str(traza))

    assert plataforma.reporte(sid)["ok"] is True
    inicios = [l for l in traza.read_text(encoding="utf-8", errors="replace").splitlines()
               if " start " in l and " fetch " in l]
    assert inicios and all("-c http.sslBackend=schannel" in l for l in inicios), inicios


def test_si_las_librerias_no_se_instalan_vuelve_a_la_version_anterior(pc, plataforma):
    """Codigo nuevo con librerias viejas puede romper la corrida del dia siguiente."""
    pc.venv()
    antes = pc.sha()
    nueva = pc.publicar("apps/api/requirements-motor.txt", "polars==9.9.9\n", "polars imposible")
    sid = plataforma.pedir("actualizar_motor")

    pc.agente(PIP_FALSO_FALLA="1")

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert f"la versión {nueva} necesita librerías nuevas" in r["mensaje"]
    assert "No matching distribution found for polars==9.9.9" in r["mensaje"]
    assert f"quedó en la versión anterior ({antes})" in r["mensaje"]
    assert pc.sha() == antes
    assert (pc.raiz / "apps" / "api" / "requirements-motor.txt").read_text() == "httpx==0.28.1\n"


# --- Actualizar ahora -------------------------------------------------------------

MOTOR_FALSO = """\
import os, sys
sys.stderr.write("UserWarning: Workbook contains no default style\\n")
sys.stderr.flush()
print("MOTOR_STOCK_DIR=" + os.environ.get("MOTOR_STOCK_DIR", "(sin valor)"))
print("CARGA OFICIAL: 18254 filas.")
"""


def test_actualizar_ahora_sin_tipo_corre_el_motor_aunque_avise_por_stderr(pc, plataforma):
    """Sin tipo: la plataforma de antes del boton "Actualizar motor"."""
    pc.venv(motor=MOTOR_FALSO)
    sid = plataforma.pedir(None)

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is True, r
    assert r["mensaje"] == "Se publicaron 18254 filas."
    assert r["version"] == f"{pc.sha()} principal"
    log = pc.log()
    assert "UserWarning: Workbook contains no default style" in log
    # El .env sin BOM se leyo como UTF-8: el motor recibe la ruta con su tilde.
    assert "MOTOR_STOCK_DIR=C:\\OneDrive\\Abastecimiento y Logística-Data BI - Datos" in log
    # Cuenta como la corrida del dia: la tarea de las 09:30 (tarea_si_no_corrio_hoy.ps1)
    # mira la ultima linea RESULTADO de este log y no calcula otra vez lo mismo.
    motor = pc.log_motor.read_text(encoding="utf-8-sig").splitlines()
    assert "CARGA OFICIAL: 18254 filas." in motor
    assert motor[-1] == "RESULTADO: OK (agente)"


def test_el_error_del_motor_llega_con_sus_tildes(pc, plataforma):
    pc.venv(motor="import sys\nprint('ERROR: No se encontró archivo para la fuente stock_bodegas')\n"
                  "sys.exit(1)\n")
    sid = plataforma.pedir("recalcular")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert r["mensaje"] == "ERROR: No se encontró archivo para la fuente stock_bodegas"
    # Una corrida que fallo tambien queda: la tarea de las 09:30 la reintenta.
    motor = pc.log_motor.read_text(encoding="utf-8-sig").splitlines()
    assert "ERROR: No se encontró archivo para la fuente stock_bodegas" in motor
    assert motor[-1] == "RESULTADO: FALLO (codigo 1, agente)"


def _motor_frenado(archivos, bloque="Archivos vencidos"):
    """Un motor falso que frena como el de verdad: ERROR por stderr y, debajo, el bloque
    con un archivo por linea."""
    texto = "\n".join([
        "ERROR: No se carga a produccion con archivos desactualizados.",
        f"{bloque}:", *[f"  - {a}" for a in archivos], "",
        "Actualizalos en la carpeta de datos, o corre con --ignorar-frescura si sabes que asi corresponde."]) + "\n"
    return f"import sys\nsys.stderr.write({texto!r})\nsys.exit(1)\n"


def test_si_faltan_archivos_o_estan_viejos_dice_cuales_y_que_hacer(pc, plataforma):
    """Con el boton como unica forma de actualizar, "ERROR: No se carga a produccion con
    archivos desactualizados." no le decia a quien lo aprieta ni cuales ni que hacer."""
    viejos = ["Stock bodegas.xlsx: 3 dias habiles (se espera al dia cada 2)",
              "Seguimiento nacional.xlsx: 4 dias habiles (se espera al dia cada 2)"]
    pc.venv(motor=_motor_frenado(viejos))
    sid = plataforma.pedir("recalcular")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert r["mensaje"] == (
        f"No se publicó nada: faltan archivos o están desactualizados ({viejos[0]}; {viejos[1]}). "
        "Baja las tablas del ERP con su programa y vuelve a apretar el botón.")
    # Sigue quedando en el log del dia como una corrida que fallo.
    assert pc.log_motor.read_text(encoding="utf-8-sig").splitlines()[-1] == "RESULTADO: FALLO (codigo 1, agente)"


def test_con_muchos_archivos_frenados_nombra_tres_y_cuenta_el_resto(pc, plataforma):
    """Con Fuentes de datos activa el bloque se llama "Problemas:" y puede traer muchos."""
    pc.venv(motor=_motor_frenado([f"fuente_{n}: sin archivo" for n in range(1, 6)], bloque="Problemas"))
    sid = plataforma.pedir("recalcular")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert r["mensaje"] == (
        "No se publicó nada: faltan archivos o están desactualizados "
        "(fuente_1: sin archivo; fuente_2: sin archivo; fuente_3: sin archivo; y 2 más). "
        "Revisa los archivos en Fuentes de datos (o avisa a un admin) y vuelve a apretar el botón.")


def test_los_archivos_largos_se_acortan_pero_el_y_n_mas_se_conserva(pc, plataforma):
    """Antes el recorte venia despues de sumar el "y N más" y se lo comia."""
    viejos = [f"seguimiento_de_compras_importado_{n}_con_un_nombre_larguisimo.xlsx: {n + 3} dias habiles "
              f"(se espera al dia cada 2)" for n in range(1, 5)]
    pc.venv(motor=_motor_frenado(viejos))
    sid = plataforma.pedir("recalcular")

    pc.agente()

    r = plataforma.reporte(sid)
    cortos = [v if len(v) <= 90 else v[:89] + "…" for v in viejos[:3]]
    assert r["mensaje"] == (
        f"No se publicó nada: faltan archivos o están desactualizados ({'; '.join(cortos)}; y 1 más). "
        "Baja las tablas del ERP con su programa y vuelve a apretar el botón.")


def test_un_archivo_viejo_que_solo_avisa_no_se_confunde_con_el_motivo(pc, plataforma):
    """El motor imprime DESACTUALIZADO tambien para los archivos que solo avisan. Si la
    carga falla por otra cosa, el mensaje es el de esa falla y no "baja las tablas"."""
    pc.venv(motor="import sys\n"
                  "print('  DESACTUALIZADO: lista_erp.xlsx: 9 dias habiles (se espera al dia cada 7) - no frena la carga')\n"
                  "print('ERROR: La plataforma rechazo la carga (HTTP 502)', file=sys.stderr)\n"
                  "sys.exit(1)\n")
    sid = plataforma.pedir("recalcular")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert r["mensaje"] == "ERROR: La plataforma rechazo la carga (HTTP 502)"


def test_en_un_pc_que_no_es_el_titular_no_pide_volver_a_apretar(pc, plataforma):
    """El PC nuevo ya tiene el agente, pero el titular sigue siendo el anterior: es el
    unico agente, asi que volver a apretar daria siempre lo mismo."""
    pc.venv(motor="print('NO SE PUBLICA: este PC no es el titular (Notebook anterior)')\n")
    sid = plataforma.pedir("recalcular")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert r["mensaje"] == (
        f"No se publicó nada: este pedido lo tomó {os.environ['COMPUTERNAME']}, que no es el PC "
        "titular (el titular es Notebook anterior). Mientras sea así, 'Actualizar ahora' no puede "
        "publicar: cambia el titular en Fuentes de datos o avísale a un admin.")
    assert not pc.log_motor.exists(), "no calculo: no cuenta como la corrida del dia"


def test_con_otra_corrida_en_curso_no_se_lanza_una_segunda(pc, plataforma):
    desde = pc.candado_del_motor(os.getpid())
    sid = plataforma.pedir("recalcular")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert r["mensaje"].startswith(
        f"No se lanzó otra corrida: el motor ya está calculando en este PC (desde {desde})")
    assert not pc.log_motor.exists()


# --- Reporte a la plataforma --------------------------------------------------------


def test_si_la_plataforma_se_reinicia_al_final_el_reporte_se_reintenta(pc, plataforma):
    """El motor publico y Render se reinicia justo despues de la carga pesada (502/503
    el 29-09, el 30-09 y el 02-10). Con un solo intento la tarjeta quedaba girando hasta
    el plazo y despues decia error aunque se habia publicado."""
    pc.venv(motor=MOTOR_FALSO)
    plataforma.terminar_caida = 2
    sid = plataforma.pedir("recalcular")

    pc.agente("-EsperaReporteSeg", "0")

    assert plataforma.intentos_terminar == 3
    assert plataforma.reporte(sid)["mensaje"] == "Se publicaron 18254 filas."
    assert not (pc.raiz / "logs" / ".reporte_pendiente.json").exists()


def test_si_no_se_pudo_reportar_se_manda_en_la_pasada_siguiente(pc, plataforma):
    pc.venv(motor=MOTOR_FALSO)
    plataforma.terminar_caida = 4
    sid = plataforma.pedir("recalcular")

    pc.agente("-EsperaReporteSeg", "0")

    assert plataforma.intentos_terminar == 4 and plataforma.reportes == []
    pendiente = pc.raiz / "logs" / ".reporte_pendiente.json"
    assert json.loads(pendiente.read_text(encoding="utf-8"))["id"] == sid

    pc.agente("-EsperaReporteSeg", "0")  # la plataforma ya responde; no hay nada nuevo

    r = plataforma.reporte(sid)
    assert (r["ok"], r["mensaje"]) == (True, "Se publicaron 18254 filas.")
    assert not pendiente.exists()

    # Uno que la plataforma ya no tiene (404) no se reenvia para siempre.
    pendiente.write_text(json.dumps({"id": "borrada-1", "ok": True, "mensaje": "x"}), encoding="utf-8")
    pc.agente()
    assert not pendiente.exists()
    assert "rechazo el reporte pendiente (HTTP 404)" in pc.log()


# --- Candado del agente -------------------------------------------------------------


def test_un_candado_de_un_agente_que_se_corto_no_deja_al_pc_sordo(pc, plataforma):
    """Se cerro la sesion (o se reinicio el PC) en medio de un "Actualizar motor". Antes
    el candado se respetaba 75 minutos solo por su hora: el PC ignoraba todos los botones
    y la web decia que estaba apagado."""
    muerto = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                            capture_output=True, text=True, check=True)
    (pc.raiz / ".agente.lock").write_text(f"{int(muerto.stdout)} {_ahora(-2)} actualizar_motor",
                                          encoding="ascii")
    sid = plataforma.pedir("actualizar_motor")

    pc.agente()

    assert plataforma.reporte(sid)["mensaje"].startswith("El motor ya estaba al día")


def test_con_otro_agente_trabajando_no_toma_la_solicitud(pc, plataforma):
    otro = subprocess.Popen([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", "Start-Sleep -Seconds 120"])
    try:
        (pc.raiz / ".agente.lock").write_text(f"{otro.pid} {_ahora()} recalcular", encoding="ascii")
        plataforma.pedir("recalcular")
        pc.agente()
    finally:
        otro.kill()

    assert plataforma.reportes == [] and len(plataforma.cola) == 1
    assert "Ya hay una corrida en curso" in pc.log()

    # El de un agente anterior (sin PID) se respeta por la hora, como antes.
    (pc.raiz / ".agente.lock").write_text("", encoding="ascii")
    pc.agente()
    assert plataforma.reportes == [] and len(plataforma.cola) == 1


def test_mientras_el_acceso_baja_las_tablas_no_se_recalcula_ni_se_actualiza(pc, plataforma):
    """El acceso "Actualizar plataforma" publica apenas termine el programa del ERP:
    un motor ahora leeria archivos a medio bajar, y cambiar el codigo a mitad
    tampoco."""
    ventana = subprocess.Popen([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command",
                                "Start-Sleep -Seconds 120"])
    try:
        (pc.raiz / ".actualizar_plataforma.lock").write_text(f"{ventana.pid} {_ahora()}", encoding="ascii")
        antes = pc.sha()
        pc.publicar("LEEME.txt", "version 2\n", "version 2")
        sid = plataforma.pedir("recalcular")
        pc.agente()
        r = plataforma.reporte(sid)
        assert r["ok"] is False
        assert "se están bajando las tablas del ERP" in r["mensaje"]

        sid = plataforma.pedir("actualizar_motor")
        pc.agente()
        r = plataforma.reporte(sid)
        assert r["ok"] is False
        assert "se están actualizando los datos" in r["mensaje"]
        assert pc.sha() == antes
    finally:
        ventana.kill()


def test_sin_solicitudes_no_hace_nada_y_un_tipo_desconocido_no_se_adivina(pc, plataforma):
    pc.agente()
    assert plataforma.reportes == []

    antes = pc.sha()
    pc.publicar("LEEME.txt", "version 2\n", "version 2")
    sid = plataforma.pedir("borrar_todo")

    pc.agente()

    r = plataforma.reporte(sid)
    assert r["ok"] is False
    assert "tipo 'borrar_todo'" in r["mensaje"]
    assert pc.sha() == antes


def test_el_script_va_en_utf8_con_bom():
    """Sin BOM, PowerShell 5.1 lo lee como Windows-1252 y los mensajes con tilde
    llegan rotos a la tarjeta."""
    assert (SCRIPTS / "agente_actualizacion.ps1").read_bytes().startswith(b"\xef\xbb\xbf")
