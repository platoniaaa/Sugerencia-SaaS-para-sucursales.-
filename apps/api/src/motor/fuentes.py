"""Origen de los datos crudos del motor.

v1 (actual): lee archivos Excel/CSV desde una carpeta local donde el usuario
deja las descargas de SharePoint (`apps/api/data/crudos/` por defecto,
configurable con MOTOR_CRUDOS_DIR).

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
CRUDOS_DIR = pathlib.Path(os.environ.get("MOTOR_CRUDOS_DIR", _API_DIR / "data" / "crudos"))

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
    "mix_reemplazos": FuenteSpec(["*mix*", "*reemplaz*"], header_row=1),
    "catalogo": FuenteSpec(["*maestro*", "*listado*maestro*"], header_row=1),
    "dim_sucursal": FuenteSpec(
        ["*sucursal*", "*dim*local*"], excluye=["*seguimiento*", "*stock*", "*venta*"]
    ),
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _matchea(nombre: str, spec: FuenteSpec) -> bool:
    n = _norm(nombre)
    if any(fnmatch.fnmatch(n, _norm(p)) for p in spec.excluye):
        return False
    return any(fnmatch.fnmatch(n, _norm(p)) for p in spec.incluye)


def _candidatos(fuente: str) -> list[pathlib.Path]:
    if fuente not in FUENTES:
        raise KeyError(f"Fuente desconocida: {fuente!r}. Válidas: {sorted(FUENTES)}")
    if not CRUDOS_DIR.exists():
        return []
    spec = FUENTES[fuente]
    archivos = [
        p for p in CRUDOS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _EXT and not p.name.startswith("~$")
    ]
    matches = [p for p in archivos if _matchea(p.name, spec)]
    return sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)


def rutas_de(fuente: str) -> list[pathlib.Path]:
    """Todos los archivos que matchean la fuente (más reciente primero)."""
    candidatos = _candidatos(fuente)
    if not candidatos:
        spec = FUENTES[fuente]
        raise FileNotFoundError(
            f"No se encontró archivo para la fuente '{fuente}' en {CRUDOS_DIR}.\n"
            f"Patrones: incluye={spec.incluye} excluye={spec.excluye}.\n"
            "Descarga el Excel desde SharePoint y déjalo ahí (ver data/crudos/README.md)."
        )
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
    lineas = [f"Carpeta de crudos: {CRUDOS_DIR}", ""]
    if not CRUDOS_DIR.exists():
        return "\n".join(lineas + ["(la carpeta no existe todavía)"])
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
    presentes = {
        p.name for p in CRUDOS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _EXT and not p.name.startswith("~$")
    }
    huerfanos = presentes - asignados
    if huerfanos:
        lineas += ["", f"Sin fuente asignada: {sorted(huerfanos)}"]
    return "\n".join(lineas)


if __name__ == "__main__":
    print(inventariar())
