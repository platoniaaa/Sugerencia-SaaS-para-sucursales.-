"""De donde sale cada archivo que lee el motor: la configuracion de las fuentes.

Hasta oct-2026 el motor sabia que archivo leer por dos variables del .env de este
PC (MOTOR_CRUDOS_DIR y MOTOR_STOCK_DIR) y los patrones de `fuentes.FUENTES`. Un
archivo nuevo en la carpeta boto la corrida diaria tres veces, y nadie podia ver
que archivo habia leido el motor ni de que fecha era.

Ahora la configuracion vive en la plataforma (pantalla de admin "Fuentes de
datos") y el motor la pide al partir. Tres modos:

- `sin_configurar`: el motor usa el .env, como siempre, y en cada reporte manda
  `config_efectiva()` -lo que usa hoy- para que un admin la siembre.
- `prueba`: sigue usando el .env, y ademas resuelve con la configuracion de la
  plataforma para COMPARAR. Lo que se publica no cambia.
- `activa`: usa la configuracion de la plataforma.

Regla de oro: el motor NUNCA deja de correr por culpa de este modulo.

- Si la plataforma no responde o manda algo invalido, se usa la configuracion
  guardada en este PC (`data/fuentes_config_cache.json`, no vence) y, si no hay,
  el .env. Solo los errores al TRAER la configuracion activan esa cascada: un
  archivo que no se puede copiar o leer queda como estado de su fuente.
- `MOTOR_FUENTES=env` en el .env apaga todo esto de inmediato: se elige con el
  .env y no se pide la configuracion (ni se mira el PC titular). El reporte al
  panel se sigue mandando, para que se vea que corrio con la del PC.
- Se atrapa `Exception` y nunca `BaseException`: `LlamadaRealDesdeUnTest` tiene
  que atravesar la cascada (ver `correr_motor_real._token`).

Cada corrida arma UN manifiesto: que archivo eligio cada fuente, de que carpeta,
con que fecha y huella. Los elegidos se COPIAN a `data/corrida/<id>/` y todos los
pasos leen la copia: si OneDrive reemplaza el stock a mitad de corrida, el
sugerido y las altas de la lista de precios siguen leyendo el mismo archivo.

    python -m src.motor.config_fuentes --probar             # que elige cada lado
    python -m src.motor.config_fuentes --probar --reportar  # y lo manda al panel
    python -m src.motor.config_fuentes --guardar-config     # la deja guardada en este PC

No usa el registro de Windows ni Microsoft Graph (ver docs/adr/0004).
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import json
import os
import pathlib
import shutil
import socket
import subprocess
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from . import fuentes as _fuentes

DATA_DIR = _fuentes._API_DIR / "data"
# La ultima configuracion que mando la plataforma, sea cual sea su modo.
CACHE = DATA_DIR / "fuentes_config_cache.json"
# Las copias de la corrida en curso. Al partir se borran las anteriores.
CORRIDA_DIR = DATA_DIR / "corrida"
# Reportes que no se pudieron mandar. Se reenvian al partir la corrida siguiente.
PENDIENTES_DIR = DATA_DIR / "reportes_pendientes"
# La corrida que esta corriendo ahora. Si queda de una corrida anterior, esa
# corrida murio sin terminar y se reporta como cortada.
EN_CURSO = DATA_DIR / "corrida_en_curso.json"

RUTA_CONFIG = "/api/admin/fuentes/config"
RUTA_REPORTE = "/api/admin/fuentes/reporte"
CONFIG_TIMEOUT_SEG = 60
CONFIG_ESPERA_SEG = 15
CONFIG_INTENTOS = 2
REPORTE_TIMEOUT_SEG = 60
PENDIENTES_POR_CORRIDA = 10
PENDIENTES_MAX = 100

# Un archivo modificado hace menos de esto puede estar bajando todavia.
RECIENTE_SEG = 180
ESPERA_SEG = 60
TOPE_ESPERA_SEG = 300            # por corrida
TOPE_COPIA_ARCHIVO_SEG = 600     # un archivo solo en la nube se baja al copiarlo
TOPE_COPIA_TOTAL_SEG = 900

# El listado de cada carpeta que viaja en el reporte (para los selectores del panel).
LISTADO_MAX_ARCHIVOS = 500
LISTADO_MAX_NIVELES = 3
CANDIDATOS_MAX = 20

EXTENSIONES = (".xlsx", ".xlsm", ".csv")
_IGNORADOS = {"desktop.ini", "thumbs.db"}

MODOS = ("sin_configurar", "prueba", "activa")
MODOS_FUENTE = ("archivo_exacto", "mas_reciente", "por_descarte")
TIPOS_CARPETA = ("onedrive", "sharepoint")

# Los dos stocks y el seguimiento nacional cambian todos los dias y su tamano casi
# no se mueve: si llegan vacios o con menos del 60 % de las filas de la corrida
# anterior, el archivo se exporto a medias. Ventas y los archivos manuales cambian
# de tamano en forma legitima y quedan fuera.
FUENTES_CON_GUARDA_DE_FILAS = ("stock_bodegas", "stock_bodegas_frontera",
                               "seguimiento_curifor_nacional")
FRACCION_MINIMA_DE_FILAS = 0.6

# Atributos de archivo de Windows que pone OneDrive (Archivos a peticion).
_SOLO_NUBE = 0x400000      # FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
_FIJADO = 0x80000          # FILE_ATTRIBUTE_PINNED: "Mantener siempre en este dispositivo"
_LIBERABLE = 0x100000      # FILE_ATTRIBUTE_UNPINNED

_dormir = time.sleep
_reloj = time.time

MOTIVO_NO_ES_VENTA = "no tiene forma de respaldo de venta (le faltan columnas)"


class ArchivoIlegible(RuntimeError):
    """Un archivo que ni siquiera abre. El texto ya va en palabras del panel: el
    nombre del archivo y la causa, sin la ruta (ver `_causa`)."""


def _causa(e: BaseException) -> str:
    """Por que no se pudo leer un archivo, sin la ruta y sin jerga. El texto de la
    excepcion trae la ruta completa, con el usuario de Windows ("[Errno 13]
    Permission denied: 'C:\\Users\\...'"), y el mensaje de la fuente va al texto
    rojo del panel y a la campanita. El texto crudo queda en `detalle`."""
    if isinstance(e, PermissionError):
        return "está abierto o bloqueado por otro programa"
    if isinstance(e, FileNotFoundError):
        return "ya no está en la carpeta (se movió o se borró mientras corría el motor)"
    if isinstance(e, OSError):
        return "Windows no dejó leerlo (revisa que OneDrive esté sincronizado)"
    return "no se pudo abrir como planilla (puede estar a medio bajar o dañado)"


def _detalle(e: BaseException) -> str:
    """El error crudo, para el log y el detalle de la fuente. Trae la ruta."""
    texto = f"{type(e).__name__}: {e}"
    if e.__cause__ is not None:
        texto += f" ({type(e.__cause__).__name__}: {e.__cause__})"
    return texto


def _mensaje_de(e: BaseException) -> str:
    if isinstance(e, ArchivoIlegible):
        return str(e)
    return f"No se pudieron revisar los archivos de la carpeta: {_causa(e)}."


# --------------------------------------------------------------------- catalogo
# Lo que el motor declara de cada fuente. La plataforma valida contra esto y no
# tiene ninguna clave escrita en su codigo. `efecto_si_falta` se escribio
# mirando el codigo que consume cada archivo (`correr_motor_real.construir_csv`
# y `fuentes_reales.cargar_fuentes_reales`), no de memoria.
#
# `requerida`: sin ella el motor no calcula, asi que no puede quedar opcional ni
# apagada. `obligatoria` es solo el valor con que se siembra: en modo `activa`,
# una obligatoria que falta frena la publicacion.
_CATALOGO: dict[str, dict] = {
    "ventas": dict(
        nombre="Respaldos de venta", uso="lee", requerida=True, obligatoria=True,
        modos=["por_descarte"],
        efecto_si_falta=("Sin los respaldos de venta el motor calcula con una copia "
                         "antigua de las ventas, o no calcula si no la tiene: la "
                         "demanda sale equivocada.")),
    "ventas_frontera": dict(
        nombre="Ventas Frontera", uso="lee",
        efecto_si_falta=("el motor no ve la demanda que solo se vende en Frontera y "
                         "pide de menos lo que se vende en las dos empresas")),
    # Los textos de abajo los lee la jefa en el panel: van con tildes. Los que
    # no son de una fuente requerida completan la frase "El sugerido se publica
    # igual, pero ...", por eso parten en minuscula y sin punto final.
    "stock_bodegas": dict(
        nombre="Stock bodegas Curifor", uso="lee", requerida=True, obligatoria=True,
        frecuencia_max=5, al_vencer_fijo="frena",
        efecto_si_falta="Sin stock el motor no calcula."),
    "stock_bodegas_frontera": dict(
        nombre="Stock bodegas Frontera", uso="lee", requerida=True, obligatoria=True,
        frecuencia_max=5, al_vencer_fijo="frena",
        efecto_si_falta="Sin el stock de Frontera el motor no calcula."),
    "seguimiento_curifor_nacional": dict(
        nombre="Seguimiento de compras nacional", uso="lee", obligatoria=True,
        frecuencia_max=5, al_vencer_fijo="frena",
        efecto_si_falta=("el sugerido no descuenta lo que viene en camino de las "
                         "compras nacionales ni calcula con ellas el plazo de "
                         "entrega: puede pedir de nuevo algo ya comprado")),
    "seguimiento_curifor_importado": dict(
        nombre="Seguimiento de compras importado", uso="lee", obligatoria=True,
        efecto_si_falta=("el sugerido no descuenta lo que viene en camino de las "
                         "importaciones y la lista de productos importados sale de "
                         "una copia antigua (o el motor no calcula si no la tiene)")),
    "seguimiento_frontera": dict(
        nombre="Seguimiento de compras Frontera", uso="lee", obligatoria=True,
        efecto_si_falta=("el sugerido no descuenta lo que viene en camino para "
                         "Frontera ni calcula con esas compras el plazo de entrega")),
    "mix_reemplazos": dict(
        nombre="Mix de reemplazos", uso="lee", obligatoria=True,
        efecto_si_falta=("el motor agrupa los códigos de reemplazo con una copia "
                         "antigua del mix, o no calcula si no la tiene")),
    "catalogo": dict(
        nombre="Lista de precios (maestro de repuestos)", uso="lee", obligatoria=True,
        efecto_si_falta=("el motor usa una copia antigua del catálogo (categorías y "
                         "descripciones), o no calcula si no la tiene")),
    "lista_erp": dict(
        nombre="Exportación de la lista del ERP", uso="lee",
        efecto_si_falta=("los repuestos agotados salen sin costo en el sugerido y la "
                         "lista de precios no recibe esa exportación del ERP")),
    "precios_ford": dict(
        nombre="Lista de precios Ford", uso="lee",
        efecto_si_falta=("el sugerido sale sin el precio Ford para el margen, no se "
                         "actualiza la equivalencia con el portal Ford y se pierden "
                         "los reemplazos que trae esa lista")),
    "precios_gildemeister": dict(
        nombre="Lista de precios Gildemeister", uso="lee",
        efecto_si_falta="el sugerido sale sin el precio Gildemeister para el margen"),
    "vigentes_ford": dict(
        nombre="Vigentes Ford", uso="lee",
        efecto_si_falta=("los reemplazos de Ford salen solo de la lista de precios, "
                         "que no cubre más de la mitad de los códigos que se tienen "
                         "en stock")),
    "lista_new_wings": dict(
        nombre="Salida de Actualizar vigentes (WINGS)", uso="reconoce",
        efecto_si_falta=("Nadie lo lee: se reconoce para que no se confunda con un "
                         "respaldo de venta.")),
    "precios_proveedor": dict(
        nombre="Otras listas de precios de proveedor", uso="reconoce",
        efecto_si_falta=("Nadie las lee: se reconocen para que no se confundan con "
                         "un respaldo de venta.")),
    "dim_sucursal": dict(
        nombre="Tabla de sucursales", uso="reconoce",
        efecto_si_falta=("Nadie la lee (las sucursales están en el código): se "
                         "reconoce para que no se confunda con un respaldo de venta.")),
    "pautas_mantencion": dict(
        nombre="Pautas de mantención", uso="reconoce",
        efecto_si_falta=("El motor no las lee (alimentan la lista InStock, que se "
                         "arma aparte): se reconocen para que no se confundan con un "
                         "respaldo de venta.")),
}

# Carpetas que no se pueden nombrar solo con su ruta. Un acceso directo de
# SharePoint aparece en la raiz de OneDrive con el nombre "<sitio> - <carpeta>";
# la URL del sitio no se puede deducir desde el PC sin leer el registro, asi que
# queda en blanco y la completa un admin en el panel.
_CARPETAS_CONOCIDAS = {
    "Abastecimiento y Logística-Data BI - Datos": {
        "clave": "databi_datos",
        "nombre": "Data BI › Datos (SharePoint del equipo)",
        "params": {"sitio_url": None, "biblioteca": "Documentos compartidos",
                   "ruta": "Data BI/Datos"},
    },
}


def uso_de(clave: str) -> str:
    return _CATALOGO.get(clave, {}).get("uso", "lee")


def claves_que_se_leen() -> list[str]:
    return [c for c in _fuentes.FUENTES if uso_de(c) == "lee"]


def catalogo() -> dict:
    """Lo que la plataforma necesita para validar una configuracion."""
    return {
        clave: {
            "uso": d["uso"],
            "requerida": bool(d.get("requerida", False)),
            "modos": d.get("modos") or ["archivo_exacto", "mas_reciente"],
            "frecuencia_max": d.get("frecuencia_max"),
            "al_vencer_fijo": d.get("al_vencer_fijo"),
            "efecto_si_falta": d["efecto_si_falta"],
        }
        for clave, d in _CATALOGO.items()
    }


# ----------------------------------------------------------------------- tipos
@dataclass(frozen=True)
class Carpeta:
    clave: str
    nombre: str
    tipo: str
    params: dict = field(default_factory=dict)
    rutas_por_pc: dict = field(default_factory=dict)
    activa: bool = True


@dataclass(frozen=True)
class Ubicacion:
    carpeta: str
    subcarpeta: str = ""
    recursiva: bool = True


@dataclass(frozen=True)
class FuenteCfg:
    clave: str
    nombre: str
    uso: str
    ubicaciones: tuple[Ubicacion, ...]
    modo: str
    nombre_archivo: str | None
    incluye: tuple[str, ...]
    excluye: tuple[str, ...]
    extensiones: tuple[str, ...]
    frecuencia_dias: int | None
    al_vencer: str
    obligatoria: bool
    activa: bool
    diferencia_esperada: bool
    hoja: object = None
    fila_encabezado: int | None = None

    def spec(self) -> _fuentes.FuenteSpec:
        """Lo que usa `es_de_alguna_fuente` para reconocer el archivo."""
        if self.modo == "archivo_exacto" and self.nombre_archivo:
            return _fuentes.FuenteSpec([_literal(self.nombre_archivo)])
        return _fuentes.FuenteSpec(list(self.incluye), list(self.excluye))


@dataclass(frozen=True)
class ConfigFuentes:
    modo: str
    version: int | None = None
    hash: str | None = None
    pc_titular: str | None = None
    pcs: dict = field(default_factory=dict)
    catalogo: dict = field(default_factory=dict)
    carpetas: tuple[Carpeta, ...] = ()
    fuentes: tuple[FuenteCfg, ...] = ()
    anterior: dict = field(default_factory=dict)

    def alias(self, pc: str | None) -> str | None:
        if not pc:
            return None
        for nombre, datos in self.pcs.items():
            if nombre.casefold() == pc.casefold() and isinstance(datos, dict):
                return datos.get("alias") or pc
        return pc


@dataclass(frozen=True)
class CarpetaResuelta:
    clave: str
    nombre: str
    ruta: pathlib.Path | None       # None: este PC no la tiene
    metodo: str | None              # env | ruta_por_pc | onedrive | atajo
    probadas: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Archivo:
    ruta: pathlib.Path
    carpeta: str | None             # clave de la carpeta donde esta
    relativa: str                   # ruta dentro de esa carpeta, con "/"
    modificado: float
    tamano: int


@dataclass(frozen=True)
class Eleccion:
    """Lo que eligio una fuente, antes de copiar."""
    clave: str
    nombre: str
    uso: str
    # encontrado | falta | carpeta_no_encontrada | error_lectura | desactivada
    hecho: str
    elegidos: tuple[Archivo, ...] = ()
    candidatos: tuple[Archivo, ...] = ()
    descartados: tuple[tuple[str, str], ...] = ()
    carpetas_buscadas: tuple[str, ...] = ()     # rutas, para el mensaje de "falta"
    carpetas_claves: tuple[str, ...] = ()       # claves de las carpetas de sus ubicaciones
    incluye: tuple[str, ...] = ()
    excluye: tuple[str, ...] = ()
    frecuencia_dias: int | None = None
    al_vencer: str = "frena"
    obligatoria: bool = False
    diferencia_esperada: bool = False
    mensaje: str | None = None      # para el panel: sin la ruta (ver `_causa`)
    detalle: str | None = None      # el error crudo, para el log y el detalle


@dataclass(frozen=True)
class FuenteElegida:
    """Una fuente del manifiesto: lo elegido, la copia que se lee y su huella."""
    eleccion: Eleccion
    hecho: str
    copias: tuple[pathlib.Path, ...] = ()
    sha256: tuple[str | None, ...] = ()
    onedrive: tuple[str | None, ...] = ()
    mensaje: str | None = None
    detalle: str | None = None
    abierto_en_excel: bool = False
    mismo_contenido_que_anterior: bool = False
    prueba: dict | None = None


@dataclass(frozen=True)
class Manifiesto:
    """Todo lo que la corrida va a leer. Inmutable: se arma entero y se fija de
    una vez (`fuentes.fijar_manifiesto`)."""
    corrida_id: str
    origen: str                     # plataforma | cache | env
    modo: str                       # sin_configurar | prueba | activa
    resolucion: str                 # env | plataforma: con que se eligio lo que se lee
    es_titular: bool
    pc: str
    pc_titular: str | None
    alias_titular: str | None
    config_version: int | None
    por_clave: MappingProxyType
    carpetas: tuple = ()            # listado de cada carpeta, para el reporte
    avisos: tuple[str, ...] = ()
    config: ConfigFuentes | None = None
    cache_guardada_en: str | None = None
    onedrive_corriendo: bool | None = None

    def cubre(self, clave: str) -> bool:
        """Si `fuentes.rutas_de` debe contestar desde aca.

        Con la configuracion de la plataforma, toda clave: lo que no esta en el
        manifiesto falta, y NO se vuelve a buscar con el .env. Con el .env, solo
        lo que se pudo resolver: si la resolucion fallo, el paso lo vuelve a
        intentar como siempre y falla en el mismo lugar que hoy."""
        if self.resolucion == "plataforma":
            return True
        f = self.por_clave.get(clave)
        return f is not None and f.eleccion.hecho != "error_lectura"

    def rutas(self, clave: str) -> tuple[pathlib.Path, ...]:
        f = self.por_clave.get(clave)
        return f.copias if f is not None else ()

    def mensaje_sin_archivo(self, clave: str) -> str:
        f = self.por_clave.get(clave)
        if f is None:
            return (f"No se encontró archivo para la fuente '{clave}': no está en la "
                    "configuración de Fuentes de datos.")
        e = f.eleccion
        if e.mensaje:
            return f"No se encontró archivo para la fuente '{clave}': {e.mensaje}"
        return _fuentes.mensaje_sin_archivo(clave, e.carpetas_buscadas, list(e.incluye),
                                            list(e.excluye))

    def ventas(self) -> tuple[list[pathlib.Path], list[str]]:
        """(respaldos de venta a leer, nombres descartados)."""
        f = self.por_clave.get("ventas")
        if f is None:
            return [], []
        return list(f.copias), [n for n, _ in f.eleccion.descartados]

    def plazos(self) -> dict[str, tuple[int, bool]]:
        """{clave: (dias habiles, solo avisa)} de la configuracion de la plataforma."""
        return {
            c: (f.eleccion.frecuencia_dias, f.eleccion.al_vencer == "avisa")
            for c, f in self.por_clave.items()
            if f.eleccion.uso == "lee" and f.eleccion.frecuencia_dias
        }

    def bloqueos(self) -> list[str]:
        """Lo que frena la publicacion en modo `activa`. Vacio en los otros modos."""
        if self.resolucion != "plataforma":
            return []
        return _bloqueos(self.por_clave, self.config)

    def revisar_filas(self, lecturas: dict) -> str | None:
        """Detalle si un archivo con guarda de filas llego vacio o incompleto."""
        if self.resolucion != "plataforma":
            return None
        problemas = []
        anterior = (self.config.anterior if self.config else {}) or {}
        for clave in FUENTES_CON_GUARDA_DE_FILAS:
            f = self.por_clave.get(clave)
            if f is None or not f.copias:
                continue
            leidas = [lecturas.get(str(c)) for c in f.copias]
            if not any(leidas):
                continue
            filas = sum(int((x or {}).get("filas") or 0) for x in leidas)
            antes = (anterior.get(clave) or {}).get("filas")
            nombre = f.eleccion.nombre
            if filas == 0:
                problemas.append(f"{nombre}: llegó con 0 filas"
                                 + (f" (la corrida anterior traía {_miles(antes)})" if antes else "")
                                 + ".")
            elif antes and filas < FRACCION_MINIMA_DE_FILAS * float(antes):
                problemas.append(f"{nombre}: llegó con {_miles(filas)} filas y la corrida "
                                 f"anterior traía {_miles(antes)}.")
        if not problemas:
            return None
        return ("\n".join(f"  - {p}" for p in problemas)
                + "\nNo se publica para no calcular con un archivo exportado a medias. "
                  "Vuelve a correr el programa del ERP y despues el motor.")


def _miles(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def _bloqueos(por_clave, config: ConfigFuentes | None) -> list[str]:
    salida = []
    nombres_carpeta = {c.clave: c.nombre for c in (config.carpetas if config else ())}
    for clave, f in por_clave.items():
        e = f.eleccion
        if e.uso != "lee" or not e.obligatoria:
            continue
        if e.hecho == "carpeta_no_encontrada":
            carpetas = ", ".join(sorted({nombres_carpeta.get(c, c) for c in e.carpetas_claves}))
            salida.append(f"Este PC no tiene la carpeta {carpetas or e.nombre} ({e.nombre})")
        elif e.hecho == "falta":
            salida.append(f"Falta el archivo de {e.nombre}")
        elif e.hecho == "error_lectura" and not f.copias:
            salida.append(f"No se pudo leer el archivo de {e.nombre}: {e.mensaje}")
    salida += sorted(set(_duplicados({c: f.eleccion for c, f in por_clave.items()}).values()))
    return salida


def _duplicados(elecciones: dict[str, Eleccion]) -> dict[str, str]:
    """{clave: motivo} de las fuentes que se LEEN y eligieron el mismo archivo que
    otra: una de las dos esta leyendo lo que no es (paso con las listas de precios
    de proveedor, que el patron del maestro tambien tomaba)."""
    por_ruta: dict[str, list[tuple[str, str, str]]] = {}
    for clave, e in elecciones.items():
        if e.uso != "lee":
            continue
        for a in e.elegidos:
            por_ruta.setdefault(_clave_ruta(a.ruta), []).append((clave, e.nombre, a.ruta.name))
    salida = {}
    for quienes in por_ruta.values():
        if len(quienes) > 1:
            texto = (f"El archivo {quienes[0][2]} lo eligieron dos fuentes: "
                     + " y ".join(n for _, n, _ in quienes)
                     + ". Revisa sus patrones en Fuentes de datos")
            for clave, _, _ in quienes:
                salida[clave] = texto
    return salida


def _clave_ruta(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


# ------------------------------------------------------------------- utilidades
def _hostname() -> str:
    return os.environ.get("COMPUTERNAME") or socket.gethostname()


def _ahora_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _norm(s: str) -> str:
    return _fuentes._norm(s)


def _literal(nombre: str) -> str:
    """El nombre como patron de fnmatch que solo calza consigo mismo."""
    return "".join(f"[{c}]" if c in "*?[" else c for c in nombre)


def _partes(ruta: str | None) -> list[str] | None:
    """Los niveles de una ruta relativa con `/` o `\\`. None si no es valida."""
    if ruta is None:
        return None
    partes = [p for p in str(ruta).replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." or ":" in p for p in partes):
        return None
    return partes


def _relativa(p: pathlib.Path, raiz: pathlib.Path | None) -> str:
    if raiz is not None:
        try:
            return p.relative_to(raiz).as_posix()
        except ValueError:
            pass
    return p.name


def _dentro_de(p, raiz) -> bool:
    a, b = _clave_ruta(p), _clave_ruta(raiz)
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def _onedrive() -> pathlib.Path | None:
    v = os.environ.get("OneDriveCommercial")
    return pathlib.Path(v) if v else None


def _carpeta_org() -> pathlib.Path | None:
    """%USERPROFILE%\\<Org>: donde deja las bibliotecas el boton "Sincronizar" de
    SharePoint. <Org> es lo que sigue a "OneDrive - " en %OneDriveCommercial%.
    No esta probado en este PC: aqui las bibliotecas entran por acceso directo."""
    od, perfil = _onedrive(), os.environ.get("USERPROFILE")
    if od is None or not perfil or not od.name.startswith("OneDrive - "):
        return None
    return pathlib.Path(perfil) / od.name[len("OneDrive - "):]


def _raices_onedrive() -> tuple[pathlib.Path, ...]:
    return tuple(r for r in (_onedrive(), _carpeta_org()) if r is not None)


def _dentro_de_onedrive(p) -> bool:
    """Si `p` queda DENTRO de OneDrive o de %USERPROFILE%\\<Org>, sin ser la raiz:
    §3.2 no permite buscar en todo OneDrive. Con la raiz, la ubicacion recursiva
    de Bases de datos recorria el OneDrive entero de la persona."""
    return any(_dentro_de(p, r) and _clave_ruta(p) != _clave_ruta(r) for r in _raices_onedrive())


def _es_raiz_de_onedrive(p) -> bool:
    return any(_clave_ruta(p) == _clave_ruta(r) for r in _raices_onedrive())


def ruta_portable(p: pathlib.Path | None) -> str | None:
    """La ruta sin el usuario de Windows: %OneDriveCommercial%\\... cuando se puede,
    o %USERPROFILE%\\... para una carpeta local del perfil (la salida de emergencia
    MOTOR_CARPETA_<CLAVE>). Fuera de eso, None: la vista principal del panel muestra
    esta ruta, y la absoluta va solo en `ruta_absoluta`, que se ve en el detalle."""
    if p is None:
        return None
    org = _carpeta_org()
    perfil = os.environ.get("USERPROFILE")
    for raiz, prefijo in ((_onedrive(), "%OneDriveCommercial%"),
                          (org, f"%USERPROFILE%\\{org.name}" if org else None),
                          (pathlib.Path(perfil) if perfil else None, "%USERPROFILE%")):
        if raiz is not None and _dentro_de(p, raiz):
            resto = os.path.relpath(p, raiz)
            return prefijo if resto == "." else f"{prefijo}\\{resto}"
    return None


def sha256(p) -> str:
    """Huella del contenido, leyendo de a 1 MB."""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def estado_onedrive(p) -> str | None:
    """solo_nube | fijado | liberable | local. None fuera de Windows o si no se pudo."""
    try:
        attrs = os.stat(p).st_file_attributes
    except (AttributeError, OSError):
        return None
    if attrs & _SOLO_NUBE:
        return "solo_nube"
    if attrs & _FIJADO:
        return "fijado"
    if attrs & _LIBERABLE:
        return "liberable"
    return "local"


def _onedrive_corriendo() -> bool | None:
    """Si OneDrive.exe esta corriendo. Cerrado, los archivos dejan de llegar."""
    if os.name != "nt":
        return None
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq OneDrive.exe", "/NH"],
                           capture_output=True, text=True, timeout=15)
        return "onedrive.exe" in (r.stdout or "").lower()
    except Exception:  # noqa: BLE001 - es un dato del reporte, no puede romper nada
        return None


_VERSION: dict[str, str | None] = {}


def _version_motor() -> str | None:
    """Commit corto y rama del codigo que corre."""
    if "v" not in _VERSION:
        try:
            def _git(*args):
                r = subprocess.run(["git", "-C", str(_fuentes._REPO_DIR), *args],
                                   capture_output=True, text=True, timeout=10)
                return r.stdout.strip() if r.returncode == 0 else ""
            sha, rama = _git("rev-parse", "--short", "HEAD"), _git("rev-parse", "--abbrev-ref", "HEAD")
            _VERSION["v"] = " ".join(x for x in (sha, rama) if x) or None
        except Exception:  # noqa: BLE001
            _VERSION["v"] = None
    return _VERSION["v"]


def _es_copia_en_conflicto(nombre: str, hostnames) -> str | None:
    """El PC si `nombre` es una copia en conflicto de OneDrive (<nombre>-<PC>.xlsx)."""
    base = pathlib.Path(nombre).stem.casefold()
    for h in hostnames or ():
        if h and base.endswith("-" + h.casefold()):
            return h
    return None


# --------------------------------------------------------------------- listar
def _hasta(raiz: pathlib.Path, niveles: int):
    """Lo que hay en `raiz` y hasta `niveles` subcarpetas mas abajo, SIN entrar mas
    hondo (filtrar despues de `rglob` igual recorria todo)."""
    for actual, dirs, archivos in os.walk(raiz):
        if len(pathlib.Path(actual).relative_to(raiz).parts) >= niveles:
            dirs[:] = []
        for n in archivos:
            yield pathlib.Path(actual) / n


def listar(raiz, *, recursiva: bool = True, extensiones=EXTENSIONES,
           avisos: list[str] | None = None, hostnames=None,
           niveles: int | None = None) -> list[pathlib.Path]:
    """Los archivos de una carpeta que pueden ser una fuente. La UNICA funcion que
    recorre carpetas: la usan la resolucion con el .env, la de la plataforma y el
    listado que va al panel.

    Deja fuera los `~$` (los que deja Excel con el archivo abierto), `desktop.ini`
    y lo que no tenga una extension permitida. Una carpeta que no existe da una
    lista vacia: la biblioteca de SharePoint puede estar desconectada.

    Las copias en conflicto de OneDrive (`Stock bodegas-<PC>.xlsx`) se dejan en la
    lista, igual que siempre, y se anotan en `avisos`: compiten por fecha con el
    archivo bueno y alguien tiene que decidir cual vale.

    Respeta el orden en que las entrega el sistema: el desempate por fecha de
    `fuentes._candidatos` es estable y no puede cambiar de ganador por esto.

    `niveles`: hasta cuantas subcarpetas baja (el listado del panel). Sin el, todas.
    """
    raiz = pathlib.Path(raiz)
    if not raiz.is_dir():
        return []
    exts = tuple(e.lower() for e in extensiones)
    hosts = list(hostnames) if hostnames is not None else [_hostname()]
    salida: list[pathlib.Path] = []
    if not recursiva:
        recorrido = raiz.iterdir()
    elif niveles is not None:
        recorrido = _hasta(raiz, niveles)
    else:
        recorrido = raiz.rglob("*")
    for p in recorrido:
        nombre = p.name
        if nombre.startswith("~$") or nombre.lower() in _IGNORADOS:
            continue
        if p.suffix.lower() not in exts or not p.is_file():
            continue
        if avisos is not None:
            pc = _es_copia_en_conflicto(nombre, hosts)
            if pc:
                aviso = (f"'{_relativa(p, raiz)}' parece una copia en conflicto de OneDrive "
                         f"(termina en -{pc}): compite con el archivo bueno. Revisa cual vale "
                         "y borra la otra.")
                if aviso not in avisos:
                    avisos.append(aviso)
        salida.append(p)
    return salida


def seleccion_de_ventas(raices, fin_mes_cerrado: dt.date, *, extensiones=(".xlsx",),
                        fuentes: dict | None = None) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """(respaldos de venta, descartados) bajo `raices` = [(carpeta, recursiva)].

    Los respaldos se identifican POR DESCARTE: se llaman "2025 (4).xlsx" y no hay
    patron que los reconozca, pero si se sabe que no son stock, ni seguimiento, ni
    el mix, ni las ventas de Frontera. Solo los de los dos anos de la ventana de 12
    meses: cargar 2018-2024 serian minutos de lectura para nada. De esos, se
    descarta lo que no tenga la forma de un respaldo (el reporte de Motorcraft
    por canal del 08-09-2026).
    """
    from . import lectores_excel

    anios = {str(fin_mes_cerrado.year), str(fin_mes_cerrado.year - 1)}
    candidatos = sorted(
        p for raiz, recursiva in raices
        for p in listar(raiz, recursiva=recursiva, extensiones=extensiones)
        if not _fuentes.es_de_alguna_fuente(p.name, excepto="ventas", fuentes=fuentes)
        and any(a in p.name for a in anios)
    )
    ventas = []
    for p in candidatos:
        try:
            if lectores_excel.parece_respaldo_de_venta(p):
                ventas.append(p)
        except Exception as e:  # noqa: BLE001 - se relanza, con el nombre del archivo
            # Un archivo que ni siquiera abre (a medio bajar, o que no es un Excel)
            # tumba la corrida igual que antes, pero el error dice cual es. Sin la
            # ruta: este texto llega al panel y a la campanita.
            raise ArchivoIlegible(f"No se pudo abrir '{p.name}' para ver si es un respaldo de "
                                  f"venta: {_causa(e)}.") from e
    return ventas, [p for p in candidatos if p not in ventas]


# ------------------------------------------------------------------ carpetas
def resolver_carpeta(c: Carpeta, hostname: str | None = None) -> CarpetaResuelta:
    """Donde esta la carpeta en ESTE PC, sin inventar rutas. En orden:

    1. `MOTOR_CARPETA_<CLAVE>` en el .env: la salida de emergencia y la unica
       forma de usar una ruta local cualquiera. Si esta, manda.
    2. La ruta de este PC en el panel (`rutas_por_pc`), solo si queda dentro de
       OneDrive. Si queda fuera se ignora y se avisa.
    3. Tipo onedrive: %OneDriveCommercial%\\<ruta>.
    4. Tipo sharepoint: %OneDriveCommercial%\\<nombre del acceso directo>.
    5. Nada: la carpeta queda como no encontrada.
    """
    host = hostname or _hostname()
    variable = f"MOTOR_CARPETA_{c.clave.upper()}"
    env = _fuentes._carpetas_de(variable)
    if env:
        p = env[0]
        return CarpetaResuelta(c.clave, c.nombre, p if p.is_dir() else None, "env", (str(p),))
    probadas, avisos = [], []
    por_pc = next((v for k, v in (c.rutas_por_pc or {}).items()
                   if isinstance(k, str) and k.casefold() == host.casefold() and v), None)
    if por_pc:
        p = pathlib.Path(str(por_pc))
        if _dentro_de_onedrive(p):
            probadas.append(str(p))
            if p.is_dir():
                return CarpetaResuelta(c.clave, c.nombre, p, "ruta_por_pc", tuple(probadas))
        elif _es_raiz_de_onedrive(p):
            avisos.append(f"La ruta de este PC para '{c.nombre}' es la raíz de OneDrive y se "
                          "ignora: el motor no busca en todo OneDrive. Elige la carpeta de "
                          "adentro donde están los archivos.")
        else:
            avisos.append(f"La ruta de este PC para '{c.nombre}' queda fuera de OneDrive y se "
                          f"ignora. Una ruta local se configura solo en el .env ({variable}).")
    od = _onedrive()
    if od is not None:
        if c.tipo == "onedrive":
            partes = _partes(c.params.get("ruta"))
            if partes:
                p = od.joinpath(*partes)
                probadas.append(str(p))
                if p.is_dir():
                    return CarpetaResuelta(c.clave, c.nombre, p, "onedrive", tuple(probadas), tuple(avisos))
        elif c.tipo == "sharepoint":
            atajo = c.params.get("nombre_atajo")
            if atajo and _partes(atajo) == [atajo]:
                p = od / atajo
                probadas.append(str(p))
                if p.is_dir():
                    return CarpetaResuelta(c.clave, c.nombre, p, "atajo", tuple(probadas), tuple(avisos))
    return CarpetaResuelta(c.clave, c.nombre, None, None, tuple(probadas), tuple(avisos))


def _slug(texto: str) -> str:
    n = _norm(texto)
    return "_".join("".join(ch if ch.isalnum() else " " for ch in n).split()) or "carpeta"


def _carpeta_portable(p: pathlib.Path) -> dict | None:
    """La carpeta de una ruta absoluta del .env, escrita sin el usuario de Windows.
    None si no esta dentro de OneDrive: esa no se puede sembrar."""
    od = _onedrive()
    if od is None or not _dentro_de(p, od) or _clave_ruta(p) == _clave_ruta(od):
        return None
    partes = list(pathlib.Path(p).relative_to(od).parts)
    conocida = _CARPETAS_CONOCIDAS.get(partes[0]) if len(partes) == 1 else None
    if conocida:
        return {"clave": conocida["clave"], "nombre": conocida["nombre"], "tipo": "sharepoint",
                "params": {"nombre_atajo": partes[0], **conocida["params"]},
                "rutas_por_pc": {}, "activa": True}
    if len(partes) == 1 and " - " in partes[0]:
        # Un acceso directo de SharePoint que no conocemos: se siembra igual.
        return {"clave": _slug(partes[0]), "nombre": partes[0], "tipo": "sharepoint",
                "params": {"nombre_atajo": partes[0], "sitio_url": None, "biblioteca": None,
                           "ruta": None},
                "rutas_por_pc": {}, "activa": True}
    return {"clave": _slug(partes[-1]), "nombre": partes[-1], "tipo": "onedrive",
            "params": {"ruta": "/".join(partes)}, "rutas_por_pc": {}, "activa": True}


# ------------------------------------------------------------ config efectiva
def armar_config_efectiva(hostname: str | None = None) -> tuple[dict, list[str]]:
    """(config, avisos): lo que el motor usa HOY, con el formato de la plataforma.

    Es la semilla: un admin la copia al panel con un boton y nadie transcribe
    patrones a mano. Reproduce exacto `fuentes.FUENTES`, las carpetas del .env
    (MOTOR_CRUDOS_DIR para todo, recursiva; MOTOR_STOCK_DIR solo para los stocks,
    sin subcarpetas) y los plazos de `FRESCURA_DIAS` / `FRESCURA_SOLO_AVISA`."""
    from ..jobs import correr_motor_real as job

    host = hostname or _hostname()
    avisos: list[str] = []
    carpetas: list[dict] = []
    clave_de: dict[str, str] = {}
    # Las mismas claves que usa el reporte con el .env (`_raices_env`).
    for clave, d, variable in _raices_env():
        c = _carpeta_portable(d)
        if c is None:
            avisos.append(f"La carpeta de {variable} ({d}) no esta dentro de OneDrive: no se "
                          f"puede sembrar. En ese PC se configura con MOTOR_CARPETA_{clave.upper()} "
                          "en el .env.")
            continue
        c["clave"] = clave
        carpetas.append(c)
        clave_de[_clave_ruta(d)] = clave

    def _ubicaciones(dirs, recursiva):
        return [{"carpeta": clave_de[_clave_ruta(d)], "subcarpeta": "", "recursiva": recursiva}
                for d in dirs if _clave_ruta(d) in clave_de]

    fuentes = []
    for clave, spec in _fuentes.FUENTES.items():
        datos = _CATALOGO.get(clave, {})
        if clave == "ventas":
            # `_archivos_de_ventas` barre solo la primera carpeta de crudos.
            ubic = _ubicaciones(_fuentes.CRUDOS_DIRS[:1], True)
            modo, exts = "por_descarte", [".xlsx"]
        else:
            ubic = _ubicaciones(_fuentes.CRUDOS_DIRS, True)
            if clave in _fuentes.FUENTES_DE_STOCK:
                ubic += _ubicaciones(_fuentes.STOCK_DIRS, False)
            modo, exts = "mas_reciente", list(_fuentes._EXT)
        fuentes.append({
            "clave": clave,
            "nombre": datos.get("nombre", clave),
            "ubicaciones": ubic,
            "modo": modo,
            "nombre_archivo": None,
            "incluye": list(spec.incluye),
            "excluye": list(spec.excluye),
            "extensiones": exts,
            "frecuencia_dias": job.FRESCURA_DIAS.get(clave),
            "al_vencer": "avisa" if clave in job.FRESCURA_SOLO_AVISA else "frena",
            "obligatoria": bool(datos.get("obligatoria", False)),
            "activa": True,
            "diferencia_esperada": False,
            "hoja": spec.hoja,
            "fila_encabezado": spec.header_row or None,
        })
    config = {
        "modo": "prueba",
        "pc_titular": host,
        "pcs": {host: {"alias": host}},
        "catalogo": catalogo(),
        "carpetas": carpetas,
        "fuentes": fuentes,
    }
    return config, avisos


def config_efectiva(hostname: str | None = None) -> dict:
    return armar_config_efectiva(hostname)[0]


# --------------------------------------------------------- leer configuracion
def _texto(x, campo, *, opcional=False) -> str | None:
    v = x.get(campo)
    if v is None and opcional:
        return None
    if not isinstance(v, str) or (not v and not opcional):
        raise ValueError(f"'{campo}' tiene que ser texto")
    return v


def _lista_de_texto(x, campo) -> tuple[str, ...]:
    v = x.get(campo) or []
    if not isinstance(v, list) or not all(isinstance(s, str) for s in v):
        raise ValueError(f"'{campo}' tiene que ser una lista de textos")
    return tuple(v)


def leer_config(d) -> ConfigFuentes:
    """Valida lo que mando la plataforma (o la cache). ValueError si no sirve: la
    cascada pasa a la configuracion guardada o al .env."""
    if not isinstance(d, dict):
        raise ValueError("la configuracion no es un objeto JSON")
    modo = d.get("modo")
    if modo not in MODOS:
        raise ValueError(f"modo desconocido: {modo!r}")
    version = d.get("version")
    if version is not None and (not isinstance(version, int) or isinstance(version, bool)):
        raise ValueError("'version' tiene que ser un entero")
    if modo == "sin_configurar":
        return ConfigFuentes(modo=modo, version=version)
    cat = d.get("catalogo") or {}
    if not isinstance(cat, dict):
        raise ValueError("'catalogo' tiene que ser un objeto")
    carpetas: list[Carpeta] = []
    for x in d.get("carpetas") or []:
        if not isinstance(x, dict):
            raise ValueError("cada carpeta tiene que ser un objeto")
        tipo = x.get("tipo")
        if tipo not in TIPOS_CARPETA:
            raise ValueError(f"tipo de carpeta desconocido: {tipo!r}")
        params, por_pc = x.get("params") or {}, x.get("rutas_por_pc") or {}
        if not isinstance(params, dict) or not isinstance(por_pc, dict):
            raise ValueError("'params' y 'rutas_por_pc' tienen que ser objetos")
        clave = _texto(x, "clave")
        carpetas.append(Carpeta(clave=clave, nombre=x.get("nombre") or clave, tipo=tipo,
                                params=dict(params), rutas_por_pc=dict(por_pc),
                                activa=bool(x.get("activa", True))))
    claves_carpeta = [c.clave for c in carpetas]
    if len(set(claves_carpeta)) != len(claves_carpeta):
        raise ValueError("hay dos carpetas con la misma clave")
    fuentes: list[FuenteCfg] = []
    for x in d.get("fuentes") or []:
        if not isinstance(x, dict):
            raise ValueError("cada fuente tiene que ser un objeto")
        clave = _texto(x, "clave")
        ubic = []
        for u in x.get("ubicaciones") or []:
            if not isinstance(u, dict) or u.get("carpeta") not in claves_carpeta:
                raise ValueError(f"{clave}: una ubicacion apunta a una carpeta que no existe")
            sub = u.get("subcarpeta") or ""
            if not isinstance(sub, str) or sub.startswith(("/", "\\")) or _partes(sub) is None:
                raise ValueError(f"{clave}: subcarpeta invalida {sub!r}")
            ubic.append(Ubicacion(carpeta=u["carpeta"], subcarpeta=sub,
                                  recursiva=bool(u.get("recursiva", True))))
        modo_f = x.get("modo")
        if modo_f not in MODOS_FUENTE:
            raise ValueError(f"{clave}: modo desconocido {modo_f!r}")
        nombre_archivo = _texto(x, "nombre_archivo", opcional=True)
        incluye, excluye = _lista_de_texto(x, "incluye"), _lista_de_texto(x, "excluye")
        if modo_f == "archivo_exacto" and not nombre_archivo:
            raise ValueError(f"{clave}: 'archivo_exacto' necesita el nombre del archivo")
        if modo_f == "mas_reciente" and not incluye:
            raise ValueError(f"{clave}: 'mas_reciente' necesita al menos un patron")
        for patron in incluye + excluye + ((nombre_archivo,) if nombre_archivo else ()):
            if any(s in patron for s in ("/", "\\", "..")) or (len(patron) > 1 and patron[1] == ":"):
                raise ValueError(f"{clave}: patron invalido {patron!r}")
        exts = tuple(e.lower() if e.startswith(".") else "." + e.lower()
                     for e in _lista_de_texto(x, "extensiones")) or EXTENSIONES
        frec = x.get("frecuencia_dias")
        if frec is not None and (not isinstance(frec, int) or isinstance(frec, bool)
                                 or not 1 <= frec <= 365):
            raise ValueError(f"{clave}: 'frecuencia_dias' va de 1 a 365")
        al_vencer = x.get("al_vencer") or "frena"
        if al_vencer not in ("frena", "avisa"):
            raise ValueError(f"{clave}: 'al_vencer' es frena o avisa")
        uso = (cat.get(clave) or {}).get("uso") if isinstance(cat.get(clave), dict) else None
        fuentes.append(FuenteCfg(
            clave=clave, nombre=x.get("nombre") or clave, uso=uso or uso_de(clave),
            ubicaciones=tuple(ubic), modo=modo_f, nombre_archivo=nombre_archivo,
            incluye=incluye, excluye=excluye, extensiones=exts, frecuencia_dias=frec,
            al_vencer=al_vencer, obligatoria=bool(x.get("obligatoria", False)),
            activa=bool(x.get("activa", True)),
            diferencia_esperada=bool(x.get("diferencia_esperada", False)),
            hoja=x.get("hoja"), fila_encabezado=x.get("fila_encabezado"),
        ))
    claves = [f.clave for f in fuentes]
    if len(set(claves)) != len(claves):
        raise ValueError("hay dos fuentes con la misma clave")
    pcs, anterior = d.get("pcs") or {}, d.get("anterior") or {}
    if not isinstance(pcs, dict) or not isinstance(anterior, dict):
        raise ValueError("'pcs' y 'anterior' tienen que ser objetos")
    return ConfigFuentes(
        modo=modo, version=version, hash=d.get("hash"),
        pc_titular=_texto(d, "pc_titular", opcional=True), pcs=dict(pcs), catalogo=dict(cat),
        carpetas=tuple(carpetas), fuentes=tuple(fuentes), anterior=dict(anterior),
    )


# ------------------------------------------------------------------- cascada
def _kill_switch() -> bool:
    return (_fuentes._valor_env("MOTOR_FUENTES") or "").strip().lower() == "env"


class _SinPlataforma(Exception):
    """No hay credenciales de la plataforma en este PC."""


class _SinEndpoint(Exception):
    """La plataforma todavia no tiene el endpoint de fuentes (404)."""


def obtener_config_fuentes() -> dict | None:
    """GET de la configuracion, con el mismo login de la corrida. None si este PC
    no tiene credenciales. Un reintento a los 15 s (Render tarda en despertar); si
    vuelve a fallar, lanza y la cascada sigue con la configuracion guardada."""
    import httpx

    from ..jobs import correr_motor_real as job

    base, email, password = job._credenciales()
    if not email or not password:
        return None
    ultimo: Exception | None = None
    for intento in range(1, CONFIG_INTENTOS + 1):
        try:
            with httpx.Client(timeout=CONFIG_TIMEOUT_SEG) as c:
                token = job._token(c, base, email, password, renovar=intento > 1)
                r = c.get(f"{base}{RUTA_CONFIG}", headers={"Authorization": f"Bearer {token}"})
                r.raise_for_status()
                return r.json()
        except Exception as e:  # noqa: BLE001 - la cascada decide que hacer
            ultimo = e
            if intento < CONFIG_INTENTOS:
                print(f"  (la plataforma no entrego la configuracion de fuentes: {e}; "
                      f"reintentando en {CONFIG_ESPERA_SEG}s)")
                _dormir(CONFIG_ESPERA_SEG)
    raise ultimo  # type: ignore[misc]


def _leer_cache(avisos: list[str]) -> tuple[ConfigFuentes, str | None] | None:
    if not CACHE.exists():
        return None
    try:
        datos = json.loads(CACHE.read_text(encoding="utf-8"))
        return leer_config(datos["config"]), datos.get("guardada_en")
    except Exception as e:  # noqa: BLE001
        avisos.append(f"La configuracion guardada en este PC no se pudo leer ({e}).")
        return None


def _guardar_cache(crudo: dict, avisos: list[str]) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"guardada_en": _ahora_iso(), "config": crudo},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, CACHE)
    except Exception as e:  # noqa: BLE001
        avisos.append(f"No se pudo guardar la configuracion en este PC ({e}).")


def cargar_configuracion(*, guardar_cache: bool = True):
    """(config | None, origen, avisos, cache_guardada_en). La cascada:

    1. `MOTOR_FUENTES=env` -> el .env, sin preguntarle nada a la plataforma.
    2. La plataforma responde -> esa, y se guarda en este PC. Salvo que diga
       `sin_configurar` y lo guardado diga prueba/activa (se movio o se vacio la
       base): ahi manda lo guardado, y no se pisa.
    3. No responde o manda algo invalido -> lo guardado, por viejo que sea.
    4. Nada guardado -> el .env, que es lo de siempre.
    """
    avisos: list[str] = []
    if _kill_switch():
        return None, "env", ["MOTOR_FUENTES=env en este PC: se usa el .env y no se le pide "
                             "la configuración a la plataforma."], None
    cfg, crudo = None, None
    try:
        crudo = obtener_config_fuentes()
        if crudo is None:
            avisos.append("Este PC no tiene credenciales de la plataforma.")
        else:
            cfg = leer_config(crudo)
    except Exception as e:  # noqa: BLE001 - nunca deja al motor sin correr
        avisos.append(f"La plataforma no entrego la configuracion de fuentes "
                      f"({type(e).__name__}: {e}).")
        cfg = None
    if cfg is not None:
        if cfg.modo == "sin_configurar":
            guardada = _leer_cache(avisos)
            if guardada and guardada[0].modo in ("prueba", "activa"):
                avisos.append(f"La plataforma dice 'sin configurar', pero la configuracion "
                              f"guardada en este PC dice '{guardada[0].modo}': se usa la guardada.")
                return guardada[0], "cache", avisos, guardada[1]
        if guardar_cache:
            _guardar_cache(crudo, avisos)
        return cfg, "plataforma", avisos, None
    guardada = _leer_cache(avisos)
    if guardada:
        avisos.append(f"Se usa la configuracion guardada en este PC el {guardada[1]}.")
        return guardada[0], "cache", avisos, guardada[1]
    return None, "env", avisos, None


def es_titular(cfg: ConfigFuentes | None, hostname: str) -> bool:
    if cfg is None or cfg.modo == "sin_configurar" or not cfg.pc_titular:
        return True
    return cfg.pc_titular.casefold() == hostname.casefold()


# ----------------------------------------------------------------- resolucion
def _archivo(p: pathlib.Path, carpeta: str | None, raiz: pathlib.Path | None) -> Archivo:
    st = p.stat()
    return Archivo(ruta=p, carpeta=carpeta, relativa=_relativa(p, raiz),
                   modificado=st.st_mtime, tamano=st.st_size)


def _raiz_de(p, raices) -> tuple[str | None, pathlib.Path | None]:
    """(clave, raiz) de la carpeta que contiene `p`, la mas especifica."""
    mejor = (None, None)
    for clave, raiz in raices:
        if raiz is not None and _dentro_de(p, raiz):
            if mejor[1] is None or len(str(raiz)) > len(str(mejor[1])):
                mejor = (clave, raiz)
    return mejor


def _anio_fin(hoy: dt.date) -> dt.date:
    return hoy.replace(day=1)


def _descartados_por_patron(archivos, clave, spec, specs) -> list[tuple[str, str]]:
    """Archivos que calzan con un patron de la fuente pero que una exclusion deja
    fuera, y que no son de ninguna otra fuente: lo nuevo que alguien dejo en la
    carpeta y que el motor no esta leyendo."""
    salida = []
    for p in archivos:
        n = _norm(p.name)
        if not any(fnmatch.fnmatch(n, _norm(x)) for x in spec.incluye):
            continue
        excl = next((x for x in spec.excluye if fnmatch.fnmatch(n, _norm(x))), None)
        if excl is None:
            continue
        if any(_fuentes._matchea(p.name, s) for c, s in specs.items() if c != clave):
            continue
        item = (p.name, f"lo excluye el patrón '{excl}'")
        if item not in salida:
            salida.append(item)
    return salida


def _raices_env() -> list[tuple[str, pathlib.Path, str]]:
    """(clave, carpeta, variable) de las carpetas del .env, con la clave que les da
    la semilla, para que el reporte nombre igual las dos resoluciones."""
    salida, vistas = [], set()
    for variable, dirs in (("MOTOR_CRUDOS_DIR", _fuentes.CRUDOS_DIRS),
                           ("MOTOR_STOCK_DIR", _fuentes.STOCK_DIRS)):
        for d in dirs:
            if _clave_ruta(d) in vistas:
                continue
            vistas.add(_clave_ruta(d))
            c = _carpeta_portable(d)
            clave = c["clave"] if c else _slug(d.name)
            while any(x[0] == clave for x in salida):
                clave += "_2"
            salida.append((clave, d, variable))
    return salida


def resolver_env(hoy: dt.date | None = None, carpeta_ventas=None) -> dict[str, Eleccion]:
    """Lo que el motor elige HOY con el .env, con las MISMAS funciones de siempre
    (`fuentes._candidatos` y la seleccion de ventas): no hay una segunda copia de
    la logica que se pueda desalinear."""
    hoy = hoy or dt.date.today()
    raices = [(c, d) for c, d, _ in _raices_env()]
    carpeta_ventas = pathlib.Path(carpeta_ventas) if carpeta_ventas else _fuentes.CRUDOS_DIR
    specs = dict(_fuentes.FUENTES)
    crudos, de_stock = _fuentes.archivos_crudos(), _fuentes.archivos_de_stock()
    salida: dict[str, Eleccion] = {}
    for clave, spec in _fuentes.FUENTES.items():
        datos = _CATALOGO.get(clave, {})
        base = dict(clave=clave, nombre=datos.get("nombre", clave), uso=uso_de(clave),
                    incluye=tuple(spec.incluye), excluye=tuple(spec.excluye),
                    obligatoria=bool(datos.get("obligatoria", False)))
        base.update(_plazo_env(clave))
        try:
            if clave == "ventas":
                carpetas = [carpeta_ventas]
                ventas, descartados = seleccion_de_ventas([(carpeta_ventas, True)], _anio_fin(hoy))
                elegidos = tuple(_archivo(p, *_raiz_de(p, raices)) for p in ventas)
                desc = tuple((p.name, MOTIVO_NO_ES_VENTA) for p in descartados)
                candidatos = elegidos
            else:
                carpetas = _fuentes._carpetas_de_la_fuente(clave)
                cands = _fuentes._candidatos(clave)
                candidatos = tuple(_archivo(p, *_raiz_de(p, raices)) for p in cands)
                elegidos = candidatos[:1]
                todos = crudos + (de_stock if clave in _fuentes.FUENTES_DE_STOCK else [])
                desc = tuple(_descartados_por_patron(todos, clave, spec, specs))
        except Exception as e:  # noqa: BLE001 - queda como estado de la fuente
            salida[clave] = Eleccion(hecho="error_lectura", mensaje=_mensaje_de(e),
                                     detalle=_detalle(e), carpetas_buscadas=(), **base)
            continue
        if elegidos:
            hecho = "encontrado"
        elif not any(pathlib.Path(c).is_dir() for c in carpetas):
            hecho = "carpeta_no_encontrada"
        else:
            hecho = "falta"
        salida[clave] = Eleccion(hecho=hecho, elegidos=elegidos, candidatos=candidatos,
                                 descartados=desc,
                                 carpetas_buscadas=tuple(str(c) for c in carpetas), **base)
    return salida


def _plazo_env(clave: str) -> dict:
    from ..jobs import correr_motor_real as job

    return {"frecuencia_dias": job.FRESCURA_DIAS.get(clave),
            "al_vencer": "avisa" if clave in job.FRESCURA_SOLO_AVISA else "frena"}


def resolver_config(cfg: ConfigFuentes, hoy: dt.date | None = None,
                    hostname: str | None = None) -> tuple[dict[str, Eleccion], dict[str, CarpetaResuelta]]:
    """Lo que se elegiria con la configuracion de la plataforma, en este PC."""
    hoy = hoy or dt.date.today()
    host = hostname or _hostname()
    resueltas = {c.clave: resolver_carpeta(c, host) for c in cfg.carpetas if c.activa}
    raices = [(c, r.ruta) for c, r in resueltas.items()]
    # Los patrones de TODAS las fuentes, tambien las desactivadas: una fuente que
    # no se lee sigue siendo duena de sus archivos. Sin esto, desactivar el mix
    # dejaba "BASE NUEVO MIX 2026_1.xlsx" como candidato a respaldo de venta.
    specs = {f.clave: f.spec() for f in cfg.fuentes if f.modo != "por_descarte"}
    listados: dict[tuple, list[pathlib.Path]] = {}

    def _listar(raiz, recursiva, exts):
        k = (_clave_ruta(raiz), recursiva, exts)
        if k not in listados:
            listados[k] = listar(raiz, recursiva=recursiva, extensiones=exts)
        return listados[k]

    salida: dict[str, Eleccion] = {}
    for f in cfg.fuentes:
        base = dict(clave=f.clave, nombre=f.nombre, uso=f.uso, incluye=f.incluye,
                    excluye=f.excluye, frecuencia_dias=f.frecuencia_dias,
                    al_vencer=f.al_vencer, obligatoria=f.obligatoria,
                    diferencia_esperada=f.diferencia_esperada)
        if not f.activa:
            # No se lee, asi que no falta: no frena ni en activa (`_bloqueos`) ni
            # "frenaria" en prueba. El panel la muestra gris.
            salida[f.clave] = Eleccion(hecho="desactivada", mensaje="Desactivada en Fuentes de datos.",
                                       **base)
            continue
        raices_f, buscadas, claves_buscadas = [], [], []
        for u in f.ubicaciones:
            r = resueltas.get(u.carpeta)
            claves_buscadas.append(u.carpeta)
            if r is None or r.ruta is None:
                buscadas.append(f"{u.carpeta} (no esta en este PC)")
                continue
            raiz = r.ruta.joinpath(*(_partes(u.subcarpeta) or []))
            buscadas.append(str(raiz))
            if raiz.is_dir():
                raices_f.append((raiz, u.recursiva))
        try:
            if f.modo == "por_descarte":
                ventas, descartados = seleccion_de_ventas(
                    raices_f, _anio_fin(hoy), extensiones=f.extensiones, fuentes=specs)
                elegidos = tuple(_archivo(p, *_raiz_de(p, raices)) for p in ventas)
                candidatos = elegidos
                desc = tuple((p.name, MOTIVO_NO_ES_VENTA) for p in descartados)
            else:
                archivos = [p for raiz, rec in raices_f for p in _listar(raiz, rec, f.extensiones)]
                if f.modo == "archivo_exacto":
                    objetivo = _norm(f.nombre_archivo or "")
                    calzan = [p for p in archivos if _norm(p.name) == objetivo]
                else:
                    spec = f.spec()
                    calzan = [p for p in archivos if _fuentes._matchea(p.name, spec)]
                # Entre varias copias manda la FECHA, no la carpeta (igual que hoy).
                calzan = sorted(calzan, key=lambda p: p.stat().st_mtime, reverse=True)
                candidatos = tuple(_archivo(p, *_raiz_de(p, raices)) for p in calzan)
                elegidos = candidatos[:1]
                desc = (tuple(_descartados_por_patron(archivos, f.clave, f.spec(), specs))
                        if f.modo == "mas_reciente" else ())
        except Exception as e:  # noqa: BLE001 - queda como estado de la fuente
            salida[f.clave] = Eleccion(hecho="error_lectura", mensaje=_mensaje_de(e),
                                       detalle=_detalle(e), carpetas_buscadas=tuple(buscadas),
                                       **base)
            continue
        if elegidos:
            hecho = "encontrado"
        elif not raices_f:
            hecho = "carpeta_no_encontrada"
        else:
            hecho = "falta"
        salida[f.clave] = Eleccion(hecho=hecho, elegidos=elegidos, candidatos=candidatos,
                                   descartados=desc, carpetas_buscadas=tuple(buscadas),
                                   carpetas_claves=tuple(claves_buscadas), **base)
    # Lo que el motor lee y la configuracion no trae: falta, y no se busca con el .env.
    for clave in claves_que_se_leen():
        if clave not in salida:
            datos = _CATALOGO.get(clave, {})
            salida[clave] = Eleccion(clave=clave, nombre=datos.get("nombre", clave), uso="lee",
                                     hecho="falta", obligatoria=False,
                                     mensaje="No está en la configuración de Fuentes de datos.")
    return salida, resueltas


# ------------------------------------------------------------ copia y huella
@dataclass
class _Presupuesto:
    espera: float = TOPE_ESPERA_SEG
    copia: float = TOPE_COPIA_TOTAL_SEG


def _esperar_estable(p: pathlib.Path, pres: _Presupuesto) -> bool:
    """False si el archivo se sigue moviendo y se acabo el tiempo de espera.

    Un archivo modificado hace menos de 3 minutos puede estar bajando de
    OneDrive: se espera un minuto y se vuelve a medir. Tope de 5 minutos por
    corrida, para no comerse la hora que le da la tarea programada."""
    try:
        st = p.stat()
    except OSError:
        return True  # que lo diga la copia
    cambio = False
    while _reloj() - st.st_mtime < RECIENTE_SEG:
        if pres.espera <= 0:
            # Sin tiempo para esperar: solo es inestable si se le vio moverse.
            return not cambio
        pausa = min(ESPERA_SEG, pres.espera)
        print(f"  {p.name} cambio hace menos de {RECIENTE_SEG // 60} minutos: se espera "
              f"{int(pausa)}s por si OneDrive lo esta bajando.")
        _dormir(pausa)
        pres.espera -= pausa
        nuevo = p.stat()
        if (nuevo.st_size, nuevo.st_mtime_ns) == (st.st_size, st.st_mtime_ns):
            return True
        st, cambio = nuevo, True
    return True


def _con_tope(nombre: str, funcion, pres: _Presupuesto) -> tuple[bool, object]:
    """(termino, resultado) de leer un ORIGINAL en un hilo, con tope de 10 minutos
    por archivo y 15 en total. Un archivo solo en la nube se baja al leerlo, y
    OneDrive puede quedarse pegado: sin tope, la corrida quedaba colgada hasta que
    la tarea la cortaba a la hora, sin publicar. Un error se relanza aca."""
    tope = min(TOPE_COPIA_ARCHIVO_SEG, pres.copia)
    if tope <= 0:
        return False, None
    resultado: dict = {}

    def _hilo():
        try:
            resultado["ok"] = funcion()
        except Exception as e:  # noqa: BLE001 - se relanza en el hilo principal
            resultado["error"] = e

    inicio = _reloj()
    hilo = threading.Thread(target=_hilo, name=nombre, daemon=True)
    hilo.start()
    hilo.join(tope)
    pres.copia -= _reloj() - inicio
    if hilo.is_alive():
        return False, None
    if "error" in resultado:
        raise resultado["error"]
    return True, resultado.get("ok")


def _copiar(origen: pathlib.Path, destino: pathlib.Path, pres: _Presupuesto) -> bool:
    """Copia con `copy2` (conserva nombre, fecha y tamano: la huella del feed del
    ERP no cambia). False si no termino a tiempo (ver `_con_tope`)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    termino, _ = _con_tope(f"copia {origen.name}", lambda: shutil.copy2(origen, destino), pres)
    return termino


def _sha256_del_original(p: pathlib.Path, pres: _Presupuesto, *, bajar: bool) -> str | None:
    """La huella de un archivo que NO se copio. None si no se pudo medir sin colgar
    la corrida: solo esta en la nube y no se quiere bajar (`bajar=False`, en
    `--probar` y en la oficial de un PC que no es el titular, que no copian nada),
    o no termino de leerse a tiempo."""
    if not bajar and estado_onedrive(p) == "solo_nube":
        return None
    termino, huella = _con_tope(f"huella {p.name}", lambda: sha256(p), pres)
    return huella if termino else None


def _abierto_en_excel(p: pathlib.Path) -> bool:
    """Excel deja `~$<nombre>` junto al archivo abierto; con nombres largos
    reemplaza los dos primeros caracteres."""
    return any((p.parent / n).exists() for n in {"~$" + p.name, "~$" + p.name[2:]})


def _posterior(a: float, b) -> bool:
    """¿La fecha `a` (mtime) es posterior a `b` (la ISO de la corrida anterior)?

    Al segundo: el reporte manda las fechas sin fraccion (`_iso`), asi que el mismo
    archivo sin tocar volvia como "mas nuevo" por los milisegundos, y el panel decia
    "la fecha cambio, pero el contenido es identico" de un stock que nadie movio."""
    try:
        return (dt.datetime.fromtimestamp(a).astimezone().replace(microsecond=0)
                > dt.datetime.fromisoformat(str(b)))
    except (TypeError, ValueError):
        return False


def _materializar(e: Eleccion, corrida_id: str, *, copiar: bool, hashear: bool,
                  anterior: dict, pres: _Presupuesto) -> FuenteElegida:
    """Copia y mide lo elegido. Un error aqui queda en la fuente: nunca sube."""
    if not e.elegidos:
        return FuenteElegida(eleccion=e, hecho=e.hecho, mensaje=e.mensaje, detalle=e.detalle)
    if e.uso != "lee":
        # Nadie la lee: ni se copia ni se mide.
        return FuenteElegida(eleccion=e, hecho=e.hecho, copias=tuple(a.ruta for a in e.elegidos),
                             sha256=tuple(None for _ in e.elegidos),
                             onedrive=tuple(estado_onedrive(a.ruta) for a in e.elegidos))
    hecho, mensaje, detalle = e.hecho, e.mensaje, e.detalle
    copias, huellas, nube = [], [], []
    usados: set[str] = set()
    for a in e.elegidos:
        nube.append(estado_onedrive(a.ruta))
        if not _esperar_estable(a.ruta, pres):
            hecho, mensaje = "inestable", "El archivo seguía cambiando: OneDrive no terminó de bajarlo."
        leer = a.ruta
        if copiar:
            destino = CORRIDA_DIR / corrida_id / e.clave / a.ruta.name
            n = 2
            while str(destino).casefold() in usados:
                destino = CORRIDA_DIR / corrida_id / e.clave / str(n) / a.ruta.name
                n += 1
            usados.add(str(destino).casefold())
            try:
                antes = a.ruta.stat()
                if _copiar(a.ruta, destino, pres):
                    leer = destino
                    despues = a.ruta.stat()
                    if (antes.st_size, antes.st_mtime_ns) != (despues.st_size, despues.st_mtime_ns):
                        hecho, mensaje = "inestable", "El archivo cambió mientras se copiaba."
                else:
                    hecho, mensaje = "inestable", "OneDrive no terminó de bajar el archivo."
            except Exception as ex:  # noqa: BLE001 - permiso, nube: estado de la fuente
                hecho, mensaje = "error_lectura", f"No se pudo copiar {a.ruta.name}: {_causa(ex)}."
                detalle = _detalle(ex)
        copias.append(leer)
        huella = None
        if hashear and (leer != a.ruta or not copiar):
            try:
                # La copia es local. Sin copiar (`--probar`, un PC que no es el
                # titular) se mide el original: con tope y sin bajarlo de la nube.
                huella = (sha256(leer) if leer != a.ruta
                          else _sha256_del_original(leer, pres, bajar=False))
            except Exception as ex:  # noqa: BLE001
                hecho, mensaje = "error_lectura", f"No se pudo leer {a.ruta.name}: {_causa(ex)}."
                detalle = _detalle(ex)
        huellas.append(huella)
    ant = anterior.get(e.clave) or {}
    mismo = bool(
        len(e.elegidos) == 1 and huellas[0] and ant.get("sha256") == huellas[0]
        and _posterior(e.elegidos[0].modificado, ant.get("modificado_en"))
    )
    return FuenteElegida(
        eleccion=e, hecho=hecho, copias=tuple(copias), sha256=tuple(huellas),
        onedrive=tuple(nube), mensaje=mensaje, detalle=detalle if hecho == "error_lectura" else None,
        abierto_en_excel=any(_abierto_en_excel(a.ruta) for a in e.elegidos),
        mismo_contenido_que_anterior=mismo,
    )


def _limpiar_corridas(excepto: str) -> None:
    """Solo queda la copia de la ultima corrida: son cientos de MB."""
    if not CORRIDA_DIR.is_dir():
        return
    for d in CORRIDA_DIR.iterdir():
        if d.name != excepto:
            shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------- prueba
def _misma_eleccion(env: Eleccion, plat: Eleccion, pres: _Presupuesto, *, bajar: bool) -> bool:
    """Misma ruta, o mismo contenido. El contenido se compara leyendo los ORIGINALES
    (la plataforma no copia en prueba): primero el tamano, que no lee nada, y la
    huella solo si los tamanos calzan, con el tope de `_con_tope`. Lo que no se pudo
    medir a tiempo, o que solo esta en la nube cuando no se baja, da "difiere"."""
    a = sorted(_clave_ruta(x.ruta) for x in env.elegidos)
    b = sorted(_clave_ruta(x.ruta) for x in plat.elegidos)
    if a == b:
        return True
    if len(a) != len(b):
        return False
    if sorted(x.tamano for x in env.elegidos) != sorted(x.tamano for x in plat.elegidos):
        return False
    try:
        huellas = []
        for lado in (env.elegidos, plat.elegidos):
            de_este_lado = [_sha256_del_original(x.ruta, pres, bajar=bajar) for x in lado]
            if None in de_este_lado:
                return False
            huellas.append(sorted(de_este_lado))
        return huellas[0] == huellas[1]
    except OSError:
        return False


def _edad(a: Archivo, hoy: dt.date) -> int:
    from ..jobs import correr_motor_real as job

    return job.dias_habiles(dt.date.fromtimestamp(a.modificado), hoy)


def _mas_nuevo(archivos) -> Archivo | None:
    """El archivo con que se mide el plazo de una fuente: el mas nuevo. Ventas trae
    dos respaldos y el del ano pasado ya no se toca; medido con el primero (el
    orden es por nombre) la corrida frenaba todos los dias, mientras el panel
    -que mide el mas nuevo- decia "Al día"."""
    return max(archivos, key=lambda a: a.modificado) if archivos else None


def comparar(env: dict[str, Eleccion], plat: dict[str, Eleccion], hoy: dt.date, *,
             pres: _Presupuesto | None = None, bajar: bool = False) -> dict[str, dict]:
    """Por fuente: coincide | difiere | difiere_esperado | falta, el archivo que
    tomaria la plataforma y, si corresponde, por que en `activa` esto frenaria.

    `bajar`: si se puede leer un archivo que solo esta en la nube para ver si es
    el mismo (solo la corrida que copia); `pres`, el tope de tiempo de esas
    lecturas."""
    pres = pres if pres is not None else _Presupuesto()
    dups = _duplicados(plat)
    salida = {}
    for clave, e in env.items():
        p = plat.get(clave)
        if p is None or not p.elegidos:
            resultado = "falta"
        elif _misma_eleccion(e, p, pres, bajar=bajar):
            resultado = "coincide"
        else:
            resultado = "difiere_esperado" if p.diferencia_esperada else "difiere"
        frenaria = None
        # Una desactivada no se lee: en activa no frena por ella.
        if p is not None and p.uso == "lee" and p.hecho != "desactivada":
            if p.obligatoria and p.hecho == "carpeta_no_encontrada":
                frenaria = f"Este PC no tiene la carpeta de {p.nombre}"
            elif p.obligatoria and not p.elegidos:
                frenaria = f"Falta el archivo de {p.nombre}"
            elif p.elegidos and p.frecuencia_dias and p.al_vencer == "frena":
                nuevo = _mas_nuevo(p.elegidos)
                edad = _edad(nuevo, hoy)
                if edad > p.frecuencia_dias:
                    # Lo lee la jefa en el panel ("En modo activa, esto frenaria (...)").
                    frenaria = (f"{nuevo.ruta.name} tiene {edad} días hábiles y se "
                                f"espera cada {p.frecuencia_dias}")
            if frenaria is None and clave in dups:
                frenaria = dups[clave]
        salida[clave] = {
            "resultado": resultado,
            "archivo": _archivo_json(p.elegidos[0]) if p is not None and p.elegidos else None,
            "archivos": [_archivo_json(a) for a in (p.elegidos if p is not None else ())],
            "hecho": p.hecho if p is not None else "falta",
            "frenaria": frenaria,
        }
    return salida


# ------------------------------------------------------------------ reporte
def _archivo_json(a: Archivo, **extra) -> dict:
    return {"carpeta": a.carpeta, "ruta_relativa": a.relativa, "modificado_en": _iso(a.modificado),
            "tamano": a.tamano, **extra}


def _listado(clave, nombre, raiz, metodo, probadas, avisos, por_ruta, hostnames, origen) -> dict:
    """El listado de una carpeta para el panel: hasta 500 archivos y 3 niveles."""
    archivos, truncado = [], False
    if raiz is not None and raiz.is_dir():
        for p in listar(raiz, recursiva=True, extensiones=EXTENSIONES, avisos=avisos,
                        hostnames=hostnames, niveles=LISTADO_MAX_NIVELES):
            rel = p.relative_to(raiz)
            if len(archivos) >= LISTADO_MAX_ARCHIVOS:
                truncado = True
                break
            try:
                st = p.stat()
            except OSError:
                continue
            fuente, elegido = por_ruta.get(_clave_ruta(p), (_fuente_por_nombre(p.name), False))
            archivos.append({"ruta_relativa": rel.as_posix(), "tamano": st.st_size,
                             "modificado_en": _iso(st.st_mtime), "onedrive": estado_onedrive(p),
                             "fuente": fuente, "elegido": elegido})
    return {"clave": clave, "nombre": nombre, "existe": bool(raiz is not None and raiz.is_dir()),
            "metodo": metodo, "origen": origen, "ruta_portable": ruta_portable(raiz),
            "ruta_absoluta": str(raiz) if raiz is not None else None,
            "probadas": list(probadas), "archivos": archivos, "truncado": truncado}


def _fuente_por_nombre(nombre: str) -> str | None:
    for clave, spec in _fuentes.FUENTES.items():
        if clave != "ventas" and _fuentes._matchea(nombre, spec):
            return clave
    return None


def _listado_de_carpetas(elecciones, resueltas, avisos, hostnames) -> list[dict]:
    # Un archivo que eligen una fuente que se lee y otra que solo se reconoce
    # (hoy "Lista de precio ford.xlsx": precios_ford y precios_proveedor) se marca
    # con la que lo lee: el panel tiene que decir quien lo usa de verdad.
    lee_primero = sorted(elecciones.items(), key=lambda kv: kv[1].uso != "lee")
    por_ruta: dict[str, tuple[str, bool]] = {}
    for clave, e in lee_primero:
        for a in e.candidatos:
            por_ruta.setdefault(_clave_ruta(a.ruta), (clave, False))
    for clave, e in reversed(lee_primero):
        for a in e.elegidos:
            por_ruta[_clave_ruta(a.ruta)] = (clave, True)
    salida, vistas = [], set()
    for r in (resueltas or {}).values():
        salida.append(_listado(r.clave, r.nombre, r.ruta, r.metodo, r.probadas, avisos,
                               por_ruta, hostnames, "configuracion"))
        avisos.extend(a for a in r.avisos if a not in avisos)
        if r.ruta is not None:
            vistas.add(_clave_ruta(r.ruta))
    configuradas = {l["clave"] for l in salida}
    for clave, d, variable in _raices_env():
        # La carpeta del .env que coincide por clave con una configurada pero esta
        # en otra ruta (un ensayo que la movio, un PC sin %OneDriveCommercial%) no
        # va: la plataforma guarda los listados por clave y se quedaba con este,
        # asi que los selectores y la vista previa mostraban la carpeta del .env.
        if _clave_ruta(d) in vistas or clave in configuradas:
            continue
        c = _carpeta_portable(d)
        salida.append(_listado(clave, c["nombre"] if c else d.name, d, "env", (str(d),), avisos,
                               por_ruta, hostnames, variable))
    return salida


def estado_de_fuente(f: FuenteElegida, lecturas: dict, hoy: dt.date, extra: dict | None = None) -> dict:
    e = f.eleccion
    leidas = [lecturas.get(str(c)) for c in f.copias]
    leidas = [x for x in leidas if x]
    edad = _edad(_mas_nuevo(e.elegidos), hoy) if e.elegidos else None
    return {
        "nombre": e.nombre,
        "uso": e.uso,
        "hecho": f.hecho,
        "archivos": [
            _archivo_json(a, sha256=f.sha256[i] if i < len(f.sha256) else None,
                          onedrive=f.onedrive[i] if i < len(f.onedrive) else None)
            for i, a in enumerate(e.elegidos)
        ],
        "candidatos": [_archivo_json(a) for a in e.candidatos[:CANDIDATOS_MAX]],
        "carpetas_con_candidatos": sorted({a.carpeta for a in e.candidatos if a.carpeta}),
        "descartados": [{"nombre": n, "motivo": m} for n, m in e.descartados],
        "filas": sum(int(x.get("filas") or 0) for x in leidas) if leidas else None,
        "hoja_leida": leidas[0].get("hoja") if leidas else None,
        "fila_encabezado": leidas[0].get("fila_encabezado") if leidas else None,
        "edad_dias_habiles": edad,
        "mismo_contenido_que_anterior": f.mismo_contenido_que_anterior,
        "abierto_en_excel": f.abierto_en_excel,
        "prueba": f.prueba,
        "extra": extra or {},
        "mensaje": f.mensaje,
        # El error crudo, con la ruta: solo para el detalle de la fuente.
        "detalle": f.detalle,
        "frecuencia_dias": e.frecuencia_dias,
        "al_vencer": e.al_vencer,
        "obligatoria": e.obligatoria,
    }


def payload_de_reporte(corrida: dict, fase: str) -> dict:
    """Lo que se manda a POST /api/admin/fuentes/reporte. El inicio y el fin de una
    corrida tienen el mismo `id` y caen en la misma fila."""
    from . import lectores_excel

    m: Manifiesto | None = corrida.get("manifiesto")
    hoy = dt.date.today()
    fuentes = {}
    if m is not None:
        for clave, f in m.por_clave.items():
            extra = dict(corrida.get("ventas") or {}) if clave == "ventas" else {}
            try:
                fuentes[clave] = estado_de_fuente(f, lectores_excel.LECTURAS, hoy, extra)
            except Exception as e:  # noqa: BLE001 - una fuente rara no tumba el reporte
                fuentes[clave] = {"hecho": "error_lectura",
                                  "mensaje": "No se pudo armar el estado de esta fuente.",
                                  "detalle": _detalle(e)}
    avisos = list(m.avisos if m is not None else ()) + list(corrida.get("avisos") or [])
    return {
        "id": corrida["id"],
        "fase": fase,
        "pc": corrida.get("pc"),
        "tipo": corrida.get("tipo"),
        "titular": corrida.get("titular"),
        "publico": bool(corrida.get("publico")),
        "iniciada_en": corrida.get("iniciada_en"),
        "terminada_en": corrida.get("terminada_en"),
        "resultado": corrida.get("resultado"),
        "motivo": corrida.get("motivo"),
        "config_origen": corrida.get("config_origen") or (m.origen if m else "env"),
        "config_version": corrida.get("config_version"),
        "version_motor": corrida.get("version_motor"),
        "reporte": {
            "fuentes": fuentes,
            "carpetas": list(m.carpetas) if m is not None else [],
            "avisos": avisos,
            "modo": m.modo if m is not None else None,
            "resolucion": m.resolucion if m is not None else "env",
            "onedrive_corriendo": m.onedrive_corriendo if m is not None else None,
            "cache_guardada_en": m.cache_guardada_en if m is not None else None,
        },
        "config_efectiva": corrida.get("config_efectiva"),
    }


def _post_reporte(payload: dict) -> None:
    import httpx

    from ..jobs import correr_motor_real as job

    base, email, password = job._credenciales()
    if not email or not password:
        raise _SinPlataforma()
    with httpx.Client(timeout=REPORTE_TIMEOUT_SEG) as c:
        for renovar in (False, True):
            token = job._token(c, base, email, password, renovar=renovar)
            r = c.post(f"{base}{RUTA_REPORTE}", headers={"Authorization": f"Bearer {token}"},
                       json=payload)
            if r.status_code == 401 and not renovar:
                continue
            if r.status_code == 404:
                raise _SinEndpoint()
            r.raise_for_status()
            return


def _guardar_pendiente(payload: dict) -> None:
    try:
        PENDIENTES_DIR.mkdir(parents=True, exist_ok=True)
        if payload.get("fase") == "fin":
            # El fin trae todo lo del inicio: el inicio pendiente ya no hace falta.
            for viejo in PENDIENTES_DIR.glob(f"*-{payload['id']}-inicio.json"):
                viejo.unlink(missing_ok=True)
        marca = dt.datetime.now().strftime("%Y%m%d%H%M%S%f")
        destino = PENDIENTES_DIR / f"{marca}-{payload['id']}-{payload.get('fase')}.json"
        destino.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        sobran = sorted(PENDIENTES_DIR.glob("*.json"))[:-PENDIENTES_MAX]
        for viejo in sobran:
            viejo.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        print(f"  (tampoco se pudo guardar el reporte para reenviarlo: {e})")


def enviar_reporte(payload: dict) -> bool:
    """Manda el reporte. Nunca lanza `Exception`: si falla, queda pendiente y se
    reenvia en la corrida siguiente. No pasa por `_FALLOS`: el reporte no es parte
    de la publicacion y no puede dejar una carga como incompleta."""
    try:
        _post_reporte(payload)
        return True
    except _SinPlataforma:
        return False
    except _SinEndpoint:
        print("  (la plataforma todavia no recibe reportes de fuentes; no se guarda)")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"  (no se pudo mandar el reporte de fuentes: {e}; queda para la corrida siguiente)")
        _guardar_pendiente(payload)
        return False


def reenviar_pendientes(maximo: int = PENDIENTES_POR_CORRIDA) -> int:
    """Reenvia los reportes que quedaron sin mandar, del mas viejo al mas nuevo.
    Se corta en el primero que falla: la plataforma sigue sin responder."""
    enviados = 0
    try:
        archivos = sorted(PENDIENTES_DIR.glob("*.json"))[:maximo] if PENDIENTES_DIR.is_dir() else []
    except OSError:
        return 0
    for a in archivos:
        try:
            payload = json.loads(a.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - uno roto no se puede mandar nunca
            a.unlink(missing_ok=True)
            continue
        try:
            _post_reporte(payload)
        except Exception:  # noqa: BLE001
            break
        a.unlink(missing_ok=True)
        enviados += 1
    if enviados:
        print(f"  reportes de fuentes pendientes reenviados: {enviados}.")
    return enviados


# ------------------------------------------------------------------ corridas
def nueva_corrida(oficial: bool, tipo: str | None = None) -> dict:
    """La corrida que empieza. Escribe `data/corrida_en_curso.json`; si ya habia
    uno, la corrida anterior murio sin terminar y queda pendiente como cortada."""
    corrida = {
        "id": str(uuid.uuid4()),
        "pc": _hostname(),
        "tipo": tipo or ("oficial" if oficial else "comparacion"),
        "iniciada_en": _ahora_iso(),
        "terminada_en": None,
        "resultado": "en_curso",
        "motivo": None,
        "titular": None,
        "publico": False,
        "config_origen": None,
        "config_version": None,
        "version_motor": None,
        "avisos": [],
        "manifiesto": None,
        "config_efectiva": None,
    }
    try:
        corrida["version_motor"] = _version_motor()
        cfg, avisos = armar_config_efectiva(corrida["pc"])
        corrida["config_efectiva"] = cfg
        corrida["avisos"] += avisos
    except Exception as e:  # noqa: BLE001
        corrida["avisos"].append(f"No se pudo armar la configuracion efectiva ({e}).")
    if corrida["tipo"] != "probar":
        _apartar_huerfana()
        escribir_en_curso(corrida)
    return corrida


def escribir_en_curso(corrida: dict) -> None:
    try:
        EN_CURSO.parent.mkdir(parents=True, exist_ok=True)
        EN_CURSO.write_text(json.dumps({"pid": os.getpid(),
                                        "payload": payload_de_reporte(corrida, "inicio")},
                                       ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"  (no se pudo anotar la corrida en curso: {e})")


def _apartar_huerfana() -> None:
    """Una corrida anterior que no borro su archivo murio a mitad (PC apagado,
    tarea detenida): se deja pendiente como `cortada`.

    Se mira solo que el PID no sea el propio, y no si sigue vivo: el motor ya
    tomo el candado, asi que ningun otro motor puede estar corriendo, y Windows
    reusa los PID (uno vivo puede ser de otro programa)."""
    try:
        if not EN_CURSO.exists():
            return
        datos = json.loads(EN_CURSO.read_text(encoding="utf-8"))
        if int(datos.get("pid") or 0) == os.getpid():
            return
        payload = dict(datos["payload"])
        payload.update(fase="fin", resultado="cortada", terminada_en=None,
                       motivo="La corrida se cortó antes de terminar: el PC se apagó o la "
                              "tarea se detuvo.")
        _guardar_pendiente(payload)
        EN_CURSO.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        print(f"  (no se pudo revisar la corrida anterior: {e})")
        try:
            EN_CURSO.unlink(missing_ok=True)
        except OSError:
            pass


def borrar_corrida_en_curso() -> None:
    try:
        EN_CURSO.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------- preparar
def preparar_fuentes(corrida: dict, *, copiar: bool | None = None, hoy: dt.date | None = None,
                     carpeta_ventas=None, guardar_cache: bool = True,
                     reportar: bool = True) -> Manifiesto:
    """Cascada, manifiesto, copia y reporte de inicio. Devuelve el manifiesto SIN
    fijarlo: lo fija quien llama, de una vez, si la corrida sigue."""
    from . import lectores_excel

    hoy = hoy or dt.date.today()
    lectores_excel.LECTURAS.clear()
    cfg, origen, avisos, cache_en = cargar_configuracion(guardar_cache=guardar_cache)
    host = corrida.get("pc") or _hostname()
    titular = es_titular(cfg, host)
    modo = cfg.modo if cfg is not None else "sin_configurar"
    resolucion = "plataforma" if modo == "activa" else "env"
    hostnames = [host] + [h for h in ((cfg.pcs if cfg else {}) or {}) if h != host]

    resueltas: dict[str, CarpetaResuelta] = {}
    if resolucion == "plataforma":
        elecciones, resueltas = resolver_config(cfg, hoy, host)
    else:
        elecciones = resolver_env(hoy, carpeta_ventas)
    plat = None
    if cfg is not None and modo == "prueba":
        plat, resueltas = resolver_config(cfg, hoy, host)

    if copiar is None:
        copiar = corrida.get("tipo") != "probar" and (titular or corrida.get("tipo") != "oficial")
    if copiar:
        _limpiar_corridas(corrida["id"])
    pres = _Presupuesto()
    anterior = (cfg.anterior if cfg is not None else {}) or {}
    por_clave = {
        clave: _materializar(e, corrida["id"], copiar=copiar, hashear=True, anterior=anterior, pres=pres)
        for clave, e in elecciones.items()
    }
    if plat is not None:
        # Despues de copiar: lo que se lee tiene prioridad sobre el tope de tiempo, y
        # la comparacion (que lee originales) usa lo que quede. Sin copiar, no baja
        # nada de la nube solo para comparar.
        prueba = comparar(elecciones, plat, hoy, pres=pres, bajar=copiar)
        por_clave = {c: replace(f, prueba=prueba[c]) if c in prueba else f
                     for c, f in por_clave.items()}

    avisos_listado: list[str] = []
    carpetas = _listado_de_carpetas(elecciones, resueltas, avisos_listado, hostnames)
    m = Manifiesto(
        corrida_id=corrida["id"], origen=origen, modo=modo, resolucion=resolucion,
        es_titular=titular, pc=host, pc_titular=cfg.pc_titular if cfg is not None else None,
        alias_titular=cfg.alias(cfg.pc_titular) if cfg is not None else None,
        config_version=cfg.version if cfg is not None else None,
        por_clave=MappingProxyType(por_clave), carpetas=tuple(carpetas),
        avisos=tuple(avisos + avisos_listado), config=cfg, cache_guardada_en=cache_en,
        onedrive_corriendo=_onedrive_corriendo(),
    )
    corrida.update(manifiesto=m, titular=titular, config_origen=origen,
                   config_version=m.config_version)
    _imprimir_resumen(m, copiar)
    if reportar:
        if corrida.get("tipo") != "probar":
            escribir_en_curso(corrida)
        enviar_reporte(payload_de_reporte(corrida, "inicio"))
    return m


def _imprimir_resumen(m: Manifiesto, copiar: bool) -> None:
    if m.origen == "env":
        conf = "sin configuracion de la plataforma"
    else:
        conf = (("configuracion de la plataforma" if m.origen == "plataforma"
                 else "configuracion guardada en este PC")
                + f", modo {m.modo.replace('_', ' ')}"
                + (f", version {m.config_version}" if m.config_version else ""))
    lee = "la configuracion de la plataforma" if m.resolucion == "plataforma" else "el .env de este PC"
    print(f"  fuentes de datos: se lee con {lee} ({conf}).")
    for a in m.avisos:
        print(f"    aviso: {a}")
    if copiar:
        n = sum(len(f.copias) for f in m.por_clave.values() if f.eleccion.uso == "lee")
        print(f"  {n} archivo(s) copiados para esta corrida.")
    for clave, f in m.por_clave.items():
        if f.hecho in ("inestable", "error_lectura") and f.eleccion.uso == "lee":
            print(f"    {clave}: {f.mensaje}")
            if f.detalle:
                print(f"      ({f.detalle})")
        if f.prueba and f.prueba.get("frenaria"):
            print(f"    EN ACTIVA FRENARIA: {f.prueba['frenaria']}")
    if m.modo == "prueba":
        lee = [f for f in m.por_clave.values() if f.eleccion.uso == "lee" and f.prueba]
        iguales = sum(1 for f in lee if f.prueba["resultado"] in ("coincide", "difiere_esperado"))
        print(f"  prueba: {iguales} de {len(lee)} fuentes dan lo mismo con la configuracion de la plataforma.")


# ---------------------------------------------------------------------- CLI
def _corto(e: Eleccion | None) -> str:
    if e is None:
        return "(no esta)"
    if not e.elegidos:
        return f"({e.hecho.replace('_', ' ')})"
    a = e.elegidos[0]
    fecha = dt.datetime.fromtimestamp(a.modificado).strftime("%d-%m %H:%M")
    mas = f" +{len(e.elegidos) - 1}" if len(e.elegidos) > 1 else ""
    return f"{a.ruta.name} {fecha}{mas} ({a.carpeta})"


def probar(reportar: bool = False) -> int:
    """Imprime lado a lado lo que elige el .env y lo que elegiria la plataforma
    (o la semilla, si la plataforma no tiene configuracion). No calcula, no
    publica, no copia y no guarda nada en este PC."""
    corrida = nueva_corrida(oficial=False, tipo="probar")
    m = preparar_fuentes(corrida, copiar=False, guardar_cache=False, reportar=False)
    hoy = dt.date.today()
    env = {c: f.eleccion for c, f in m.por_clave.items()} if m.resolucion == "env" else resolver_env(hoy)
    if m.config is not None and m.modo != "sin_configurar":
        otra, _ = resolver_config(m.config, hoy, m.pc)
        titulo = "plataforma"
    else:
        otra, _ = resolver_config(leer_config(corrida["config_efectiva"] or config_efectiva(m.pc)), hoy, m.pc)
        titulo = "semilla"
    cmp = comparar(env, otra, hoy, bajar=False)
    print(f"\nEste PC: {m.pc}. Titular: {m.alias_titular or m.pc_titular or '(sin titular)'}"
          f"{'' if m.es_titular else '  -> este PC NO publica'}.")
    print(f"Configuracion: {m.origen}, modo {m.modo}. Se compara el .env con la {titulo}.\n")
    ancho = max(len(c) for c in env) + 2
    print(f"{'Fuente':<{ancho}}{'.env elige':<58}{titulo + ' elige':<58}resultado")
    for clave in env:
        print(f"{clave:<{ancho}}{_corto(env[clave])[:56]:<58}{_corto(otra.get(clave))[:56]:<58}"
              f"{cmp[clave]['resultado']}")
    ventas = env.get("ventas")
    print(f"\n  respaldos de venta: {[a.ruta.name for a in ventas.elegidos] if ventas and ventas.elegidos else '(ninguno)'}")
    lee = claves_que_se_leen()
    iguales = sum(1 for c in lee if cmp.get(c, {}).get("resultado") in ("coincide", "difiere_esperado"))
    print(f"{iguales} de {len(lee)} fuentes que se leen dan lo mismo.")
    for c in lee:
        if cmp.get(c, {}).get("frenaria"):
            print(f"  en activa frenaria: {cmp[c]['frenaria']}")
    if reportar:
        # Un PC que solo prueba (el de la jefa antes de ser titular) nunca corre
        # `_correr`: si no reenviara aca, un dia sin red quedaba sin llegar al panel.
        reenviar_pendientes()
        corrida.update(resultado="ok", terminada_en=_ahora_iso())
        if enviar_reporte(payload_de_reporte(corrida, "fin")):
            print("Reporte enviado a la plataforma (tipo probar).")
    return 0


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Fuentes de datos del motor.")
    ap.add_argument("--probar", action="store_true",
                    help="Muestra que archivo elige cada fuente con el .env y con la plataforma. "
                         "No calcula ni publica.")
    ap.add_argument("--reportar", action="store_true",
                    help="Con --probar: manda el resultado al panel de Fuentes de datos.")
    ap.add_argument("--guardar-config", action="store_true",
                    help="Trae la configuracion de la plataforma y la deja guardada en este PC. "
                         "Sale con 1 si este PC queda sin ninguna (ni de la plataforma ni guardada).")
    args = ap.parse_args(argv)
    if args.guardar_config:
        return guardar_config()
    if not args.probar:
        ap.print_help()
        return 2
    return probar(reportar=args.reportar)


def guardar_config() -> int:
    """La usa el instalador del PC nuevo (scripts/instalar_pc_jefa.ps1) despues de
    `--probar`, que no guarda nada. Sin configuracion guardada, si en su primera
    corrida la plataforma no respondia, `es_titular(None)` daba True: el PC nuevo se
    creia titular y publicaba a la misma hora que el de verdad, con sus archivos."""
    cfg, origen, avisos, _ = cargar_configuracion(guardar_cache=True)
    for a in avisos:
        print(f"  {a}")
    if cfg is None:
        print("Este PC no tiene configuracion de fuentes (ni de la plataforma ni guardada).")
        return 1
    print(f"Configuracion de fuentes en este PC ({origen}): modo {cfg.modo}, "
          f"titular {cfg.alias(cfg.pc_titular) or '(sin titular)'}.")
    return 0


if __name__ == "__main__":
    # Se pasa por el modulo importado y no por __main__: asi hay una sola copia
    # del estado del modulo aunque el job lo importe por su nombre.
    from src.motor import config_fuentes as _yo

    raise SystemExit(_yo.main())
