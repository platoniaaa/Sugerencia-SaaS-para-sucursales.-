"""Origen de los datos crudos del motor.

v1 (actual): lee archivos Excel/CSV desde una o varias carpetas locales
(`apps/api/data/crudos/` por defecto, configurable con MOTOR_CRUDOS_DIR, que
admite varias separadas por `;`): la biblioteca de SharePoint sincronizada y lo
que se genera en el propio PC. Aparte, MOTOR_STOCK_DIR nombra carpetas que se
leen SOLO para el stock (ver `archivos_de_stock`).

v2 (Fase 6, al final): misma interfaz `cargar(<fuente>)` pero descargando desde
SharePoint vía Microsoft Graph API. Nada aguas abajo cambia.

Cada fuente declara los patrones de nombre que la identifican (con exclusiones,
para no confundir Curifor con Frontera/Importado) y en qué fila están los
encabezados reales: varias planillas traen un título en la primera fila y los
nombres de columna en la segunda.
"""
from __future__ import annotations

import fnmatch
import os
import pathlib
import unicodedata
from dataclasses import dataclass, field

import polars as pl

_API_DIR = pathlib.Path(__file__).resolve().parents[2]
_REPO_DIR = _API_DIR.parents[1]


def _valor_env(variable: str) -> str | None:
    """El valor de una variable: del entorno o del .env del repo. None si no esta.

    El .env se lee a mano (sin dependencias) porque el motor corre tambien fuera
    de la API, donde no hay pydantic-settings cargando la configuracion.

    `utf-8-sig` y no `utf-8`: el .env de este PC parte con BOM, y con `utf-8` la
    primera linea llega como "\\ufeffVARIABLE=..." y no calza con nada. Hoy no
    falla solo porque la primera variable esta en la linea 4.

    La clave se compara sin espacios, igual que `correr_motor_real._leer_env`: un
    "MOTOR_FUENTES = env" escrito a mano en una emergencia no se leia, y la tarea
    de las 09:30 seguia obedeciendo a la plataforma.
    """
    valor = os.environ.get(variable)
    if valor is None:
        env = _REPO_DIR / ".env"
        if env.exists():
            for linea in env.read_text(encoding="utf-8-sig").splitlines():
                linea = linea.strip()
                if "=" in linea and linea.split("=", 1)[0].strip() == variable:
                    # La ruta puede traer espacios y no estar entrecomillada.
                    valor = linea.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return valor


def _carpetas_de(variable: str) -> list[pathlib.Path]:
    """Las carpetas de una variable, separadas por `;`: del entorno o del .env del repo.

    Una variable PRESENTE pero vacia cuenta como "ninguna carpeta" y no cae al
    .env: asi los tests se aislan de la configuracion de este PC.
    """
    valor = _valor_env(variable)
    return [pathlib.Path(p.strip().strip('"').strip("'"))
            for p in (valor or "").split(";") if p.strip()]


def _crudos_dirs() -> list[pathlib.Path]:
    """Carpetas de datos crudos: variable de entorno, .env del repo, o el default.

    Admite VARIAS separadas por `;`, porque los crudos dejaron de estar todos en
    el mismo lugar: las ventas las mantiene otra persona en la biblioteca de
    SharePoint "Respaldos BBDD" -donde se actualizan solas, sin que nadie las
    baje a mano-, mientras los vigentes de FORD los genera el extractor en este
    PC. Con una sola carpeta configurable habia que elegir cual de las dos se
    pierde. El separador es `;` y no `:` porque en Windows la ruta ya trae uno
    en la letra de unidad.
    """
    return _carpetas_de("MOTOR_CRUDOS_DIR") or [_API_DIR / "data" / "crudos"]


CRUDOS_DIRS = _crudos_dirs()
# La primera es la "principal": la que se nombra en los mensajes de una linea y
# la que usa el job para barrer los respaldos de venta.
CRUDOS_DIR = CRUDOS_DIRS[0]

# Carpetas que se leen SOLO para estas dos fuentes. Ver `archivos_de_stock`.
STOCK_DIRS = _carpetas_de("MOTOR_STOCK_DIR")
FUENTES_DE_STOCK = ("stock_bodegas", "stock_bodegas_frontera")

_EXT = (".xlsx", ".xlsm", ".csv")


@dataclass(frozen=True)
class FuenteSpec:
    incluye: list[str]                 # matchea si cumple CUALQUIER patrón
    excluye: list[str] = field(default_factory=list)  # descarta si cumple alguno
    header_row: int = 0                # fila 0-based de los nombres de columna
    hoja: str | int | None = None


# Los patrones se comparan sobre el nombre normalizado (minúsculas, sin tildes).
FUENTES: dict[str, FuenteSpec] = {
    # Ventas transaccionales (RespaldosBBDD). Header directo. Puede venir partido
    # por año; el motor concatena todos los que matcheen (ver cargar_ventas).
    "ventas": FuenteSpec(["*venta*"], excluye=["*presupuesto*", "*post*venta*", "*produccion*"]),
    # Ventas Frontera (E07): 'Informe Gestion Produccion REP ST GAR D&P'. Va aparte
    # porque tiene otro esquema y otros filtros que las de Curifor.
    "ventas_frontera": FuenteSpec(
        ["*vta*frontera*", "*venta*frontera*", "*frontera*vta*", "*frontera*venta*"],
        excluye=["*stock*", "*seguimiento*"],
    ),
    # Stock por bodega Curifor y Frontera (Abastecimiento-DataBI). Header directo.
    "stock_bodegas": FuenteSpec(["*stock*bodega*"], excluye=["*frontera*"]),
    "stock_bodegas_frontera": FuenteSpec(["*stock*frontera*", "*stock*bodegas*frontera*"]),
    # Seguimiento de compras: título en fila 0, encabezados en fila 1.
    "seguimiento_curifor_nacional": FuenteSpec(
        ["*seguimiento*"], excluye=["*importado*", "*frontera*"], header_row=1
    ),
    "seguimiento_curifor_importado": FuenteSpec(["*seguimiento*importado*"], header_row=1),
    "seguimiento_frontera": FuenteSpec(
        ["*frontera*seguimiento*", "*seguimiento*frontera*"], header_row=1
    ),
    # Fuentes menores.
    "mix_reemplazos": FuenteSpec(["*mix*", "*reemplaz*"], excluye=["*~*"], header_row=1),
    # Listado maestro de repuestos: de aqui sale la Categoria que excluye COLISION
    # y CAMPANAS del sugerido. Ha cambiado de forma dos veces:
    #   hasta jul-2026  export CSV de Flexline, "lista rep (lista precios).csv"
    #   desde jul-2026  hoja "Lista sin duplicados" de "LISTA DE PRECIOS.xlsx"
    #
    # El patron del maestro es EXACTO a proposito. Antes decia "*lista*precio*" y
    # tambien matcheaba las listas de PROVEEDOR ("Lista de precio ford al
    # 28.07.2026.xlsx") que, siendo mas nuevas, ganaban el desempate por fecha: el
    # motor leia una lista de precios como maestro y el job diario se caia. Taparlo
    # excluyendo proveedor por proveedor es una lista negra que hay que mantener y
    # que falla con el proximo proveedor; un nombre exacto no.
    "catalogo": FuenteSpec(
        ["*maestro*", "*listado*maestro*", "*lista*rep*",
         "lista de precios.*", "lista de precios curifor.*"],
        excluye=["*stock*", "*venta*", "*seguimiento*"],
        hoja="Lista sin duplicados",
    ),
    # El export crudo del ERP (una hoja: Producto, Descripcion, Stock, Costo,
    # Precio Venta, Tipo...). Abastecimiento lo exporta a mano, semanal, y lo deja
    # como `lista_erp.xlsx`. Alimenta la LISTA DE PRECIOS de la plataforma: crea
    # los repuestos nuevos con stock y refresca el precio ERP. No toca el sugerido.
    # El nombre es exacto a proposito, igual que el del maestro: "*lista*" solo
    # matchearia las listas de proveedor y el propio libro LISTA DE PRECIOS.xlsx.
    "lista_erp": FuenteSpec(
        ["lista_erp.*", "lista erp.*", "listaerp.*"],
        excluye=["*proveedor*", "*ford*", "*gildemeister*"],
        hoja=0,
    ),
    # Listas de precios de proveedor. NO alimentan el sugerido: dan el precio de
    # venta para calcular el margen y priorizar que comprar.
    # Tienen que estar declaradas aunque nada las lea todavia: `es_de_alguna_fuente`
    # identifica los respaldos de venta POR DESCARTE, y estos archivos traen el ano
    # en el nombre, asi que sin una fuente propia se leerian como ventas.
    "precios_ford": FuenteSpec(
        ["*precio*ford*", "*ford*precio*"], excluye=["*gildemeister*"], hoja="Precios"
    ),
    "precios_gildemeister": FuenteSpec(
        ["*precio*gildemeister*", "*gildemeister*precio*"], excluye=["*ford*"], hoja="Precios"
    ),
    # Vigentes de los codigos FORD que Curifor tiene (stock + pautas), consultados
    # en el portal por el extractor de WINGS. Mismo formato que la lista de precios
    # -hoja "Precios", 23 columnas- porque lo produce el MISMO extractor, solo que
    # sobre otra lista de entrada.
    #
    # ESTO SI MUEVE EL SUGERIDO: trae los reemplazos de los codigos que la lista de
    # precios no cubre, que son mas de la mitad de los que Curifor stockea.
    #
    # El nombre NO puede llevar "precio" ni "reemplazos": con "precio" cae en
    # `precios_ford` y, siendo mas nuevo, desplaza a la lista de 39.622 que alimenta
    # la equivalencia de SKU del portal; con "reemplazos" cae en `mix_reemplazos` y
    # rompe el mix. Por eso el patron es "vigentes*".
    "vigentes_ford": FuenteSpec(["*vigentes*ford*"], hoja="Precios"),
    # Salida de "Actualizar vigentes" del proyecto WINGS ("lista_new*.xlsx"). NADIE
    # la lee: quedo superada por la corrida del extractor sobre la lista de Curifor,
    # que trae la cadena completa y la direccion inversa. Se declara igual, y ese es
    # el punto: sin una fuente propia cae por descarte en los respaldos de venta
    # -`es_de_alguna_fuente` la da por desconocida- y el motor revienta leyendola
    # como si fuera un Excel de ventas. Paso el 22-08-2026 al cambiar el patron de
    # arriba, y es la misma falla que las pautas de mantencion volvieron a provocar
    # el 30-07-2026.
    "lista_new_wings": FuenteSpec(["lista_new*"]),
    # Cajon para CUALQUIER otra lista de precios de proveedor. Nadie la lee: existe
    # solo para que un proveedor nuevo ("Lista de precio bosch al 30.08.2026.xlsx")
    # quede reconocido y no caiga por descarte en los respaldos de venta.
    "precios_proveedor": FuenteSpec(
        ["*lista*de*precio*"],
        excluye=["lista de precios.*", "lista de precios curifor.*",
                 "*maestro*", "*lista*rep*", "*stock*", "*seguimiento*"],
        hoja="Precios",
    ),
    "dim_sucursal": FuenteSpec(
        ["*sucursal*", "*dim*local*"], excluye=["*seguimiento*", "*stock*", "*venta*"]
    ),
    # Pautas de mantencion por marca. Nadie las lee desde el motor (alimentan la
    # lista InStock, que se arma aparte), pero tienen que estar declaradas: se
    # llaman "Pauta de mantencion Baic Enero 2026.xlsx" y, sin una fuente propia,
    # `es_de_alguna_fuente` no las reconocia y caian por descarte en los respaldos
    # de venta. El 30-07-2026 eso volteo el job diario entero.
    "pautas_mantencion": FuenteSpec(["*pauta*"]),
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _matchea(nombre: str, spec: FuenteSpec) -> bool:
    n = _norm(nombre)
    if any(fnmatch.fnmatch(n, _norm(p)) for p in spec.excluye):
        return False
    return any(fnmatch.fnmatch(n, _norm(p)) for p in spec.incluye)


def es_de_alguna_fuente(
    nombre: str, excepto: str | None = None, fuentes: dict[str, FuenteSpec] | None = None
) -> bool:
    """¿El archivo corresponde a alguna fuente declarada (fuera de `excepto`)?

    Sirve para identificar los respaldos anuales de venta por descarte: se llaman
    "2025 (4).xlsx" y no hay patrón que los reconozca, pero sí se sabe qué NO son.
    Una lista negra a mano ya falló dos veces (el seguimiento importado leído como
    nacional, el "BASE NUEVO MIX 2026_1" leído como respaldo de ventas).

    `fuentes`: las de la configuración de la plataforma cuando está en modo
    `activa`, incluidas las que solo se reconocen. Por defecto, `FUENTES`."""
    return any(
        _matchea(nombre, spec) for n, spec in (fuentes or FUENTES).items() if n != excepto
    )


def archivos_crudos() -> list[pathlib.Path]:
    """Todos los Excel/CSV de todas las carpetas configuradas.

    Recursivo: asi cada carpeta puede estar organizada en subcarpetas (Ventas/,
    stock/, Seguimientos de compras/...) en vez de un monton de archivos sueltos.
    Una carpeta que no existe se salta sin ruido: la biblioteca de SharePoint
    puede estar desconectada o todavia sin sincronizar, y eso no tiene por que
    voltear una corrida que igual puede trabajar con lo que si esta a mano. Lo
    que quede viejo ya lo denuncia el control de frescura.
    """
    from .config_fuentes import listar

    salida: list[pathlib.Path] = []
    for carpeta in CRUDOS_DIRS:
        salida += listar(carpeta, recursiva=True, extensiones=_EXT)
    return salida


def archivos_de_stock() -> list[pathlib.Path]:
    """Los Excel/CSV de las carpetas de MOTOR_STOCK_DIR, solo del primer nivel.

    Esas carpetas se leen SOLO para el stock porque no son del motor: la de
    SharePoint donde el equipo sube "Stock bodegas.xlsx" cada dia (Data BI/Datos)
    trae tambien los seguimientos de compras y la produccion post-venta de las
    dos empresas. Sumarla a MOTOR_CRUDOS_DIR haria que esos archivos compitan por
    fecha con los nuestros: "Frontera - Produccion Mensual Post-Venta.xlsx" calza
    con el patron de las ventas de Frontera y "Curifor - Seguimiento Compras.xlsx"
    con el del seguimiento nacional.

    Sin recursion por lo mismo: la subcarpeta "Anteriores" guarda versiones viejas.
    Una carpeta que no existe se salta, igual que en `archivos_crudos`.
    """
    from .config_fuentes import listar

    salida: list[pathlib.Path] = []
    for carpeta in STOCK_DIRS:
        salida += listar(carpeta, recursiva=False, extensiones=_EXT)
    return salida


def _carpetas_de_la_fuente(fuente: str) -> list[pathlib.Path]:
    """Donde se busca una fuente: las de crudos, y para el stock tambien las suyas."""
    return CRUDOS_DIRS + (STOCK_DIRS if fuente in FUENTES_DE_STOCK else [])


def _candidatos(fuente: str) -> list[pathlib.Path]:
    if fuente not in FUENTES:
        raise KeyError(f"Fuente desconocida: {fuente!r}. Válidas: {sorted(FUENTES)}")
    spec = FUENTES[fuente]
    archivos = archivos_crudos()
    if fuente in FUENTES_DE_STOCK:
        archivos += archivos_de_stock()
    matches = [p for p in archivos if _matchea(p.name, spec)]
    # Entre varias copias manda la FECHA, no en que carpeta esta: durante una
    # migracion el mismo respaldo vive un tiempo en las dos.
    return sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)


def mensaje_sin_archivo(fuente: str, carpetas, incluye, excluye) -> str:
    donde = "\n  ".join(str(c) for c in carpetas)
    return (
        f"No se encontró archivo para la fuente '{fuente}'. Se buscó en:\n  {donde}\n"
        f"Patrones: incluye={incluye} excluye={excluye}.\n"
        "Descarga el Excel desde SharePoint y déjalo ahí (ver data/crudos/README.md)."
    )


# El manifiesto de la corrida en curso (`config_fuentes.Manifiesto`). Con uno
# fijado, todos los pasos leen la COPIA que se hizo al partir, y no lo que haya
# en la carpeta en ese momento: el sugerido leia el stock al partir y las altas
# de la lista de precios lo volvian a buscar media hora despues, cuando OneDrive
# ya podia haberlo reemplazado. Se fija de una vez y entero; nada de `FUENTES` ni
# de las carpetas se modifica.
_MANIFIESTO = None


def fijar_manifiesto(m) -> None:
    global _MANIFIESTO
    _MANIFIESTO = m


def soltar_manifiesto() -> None:
    global _MANIFIESTO
    _MANIFIESTO = None


def manifiesto_fijado():
    return _MANIFIESTO


def rutas_de(fuente: str) -> list[pathlib.Path]:
    """Todos los archivos que matchean la fuente (más reciente primero).

    Con un manifiesto fijado devuelve la copia del archivo elegido, y solo esa:
    lo unico que se lee de esta lista es el primero (`ruta_de`)."""
    if _MANIFIESTO is not None and _MANIFIESTO.cubre(fuente):
        rutas = _MANIFIESTO.rutas(fuente)
        if not rutas:
            raise FileNotFoundError(_MANIFIESTO.mensaje_sin_archivo(fuente))
        return list(rutas)
    candidatos = _candidatos(fuente)
    if not candidatos:
        spec = FUENTES[fuente]
        raise FileNotFoundError(mensaje_sin_archivo(
            fuente, _carpetas_de_la_fuente(fuente), spec.incluye, spec.excluye))
    return candidatos


def ruta_de(fuente: str) -> pathlib.Path:
    return rutas_de(fuente)[0]


def _leer(ruta: pathlib.Path, spec: FuenteSpec) -> pl.DataFrame:
    if ruta.suffix.lower() == ".csv":
        return pl.read_csv(ruta, skip_rows=spec.header_row, infer_schema_length=10000)
    read_options = {"header_row": spec.header_row} if spec.header_row else None
    kwargs: dict = {}
    if spec.hoja is not None:
        kwargs["sheet_name" if isinstance(spec.hoja, str) else "sheet_id"] = (
            spec.hoja if isinstance(spec.hoja, str) else spec.hoja + 1
        )
    if read_options:
        kwargs["read_options"] = read_options
    return pl.read_excel(ruta, **kwargs)


def cargar(fuente: str) -> pl.DataFrame:
    """Carga el archivo más reciente de la fuente con su fila de header correcta."""
    spec = FUENTES[fuente]
    return _leer(ruta_de(fuente), spec)


def cargar_todos(fuente: str) -> pl.DataFrame:
    """Concatena todos los archivos de la fuente (p. ej. ventas partidas por año)."""
    spec = FUENTES[fuente]
    dfs = [_leer(r, spec) for r in rutas_de(fuente)]
    if len(dfs) == 1:
        return dfs[0]
    return pl.concat(dfs, how="diagonal_relaxed")


def inventariar() -> str:
    """Reporte de qué archivo resolvió cada fuente, con sus columnas. Herramienta
    de la Fase 0 para fijar el mapeo real contra las descargas."""
    lineas = ["Carpetas de crudos:"]
    for c in CRUDOS_DIRS:
        lineas.append(f"  {c}" + ("" if c.exists() else "   (no existe todavía)"))
    if STOCK_DIRS:
        lineas.append("Carpetas solo para el stock:")
        for c in STOCK_DIRS:
            lineas.append(f"  {c}" + ("" if c.exists() else "   (no existe todavía)"))
    lineas.append("")
    if not any(c.exists() for c in CRUDOS_DIRS):
        return "\n".join(lineas + ["(ninguna de las carpetas existe todavía)"])
    asignados: set[str] = set()
    for fuente in FUENTES:
        candidatos = _candidatos(fuente)
        if not candidatos:
            lineas.append(f"[FALTA] {fuente}")
            continue
        elegido = candidatos[0]
        asignados.update(c.name for c in candidatos)
        lineas.append(f"[OK]    {fuente}: {elegido.name}")
        try:
            df = cargar(fuente)
            lineas.append(f"        {df.height} filas x {df.width} cols")
            lineas.append(f"        columnas: {df.columns}")
        except Exception as e:  # noqa: BLE001 - el inventario no debe morir por un archivo
            lineas.append(f"        (no se pudo leer: {e})")
        if len(candidatos) > 1:
            lineas.append(f"        + {len(candidatos)-1} archivo(s) más se concatenan")
    presentes = {p.name for p in archivos_crudos()}
    huerfanos = presentes - asignados
    if huerfanos:
        lineas += ["", f"Sin fuente asignada: {sorted(huerfanos)}"]
    return "\n".join(lineas)


if __name__ == "__main__":
    print(inventariar())
