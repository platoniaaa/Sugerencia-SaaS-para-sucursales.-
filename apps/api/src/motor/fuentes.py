"""Origen de los datos crudos del motor.

v1 (actual): lee archivos Excel/CSV desde una carpeta local donde el usuario
deja las descargas manuales de SharePoint (`apps/api/data/crudos/` por defecto,
configurable con MOTOR_CRUDOS_DIR).

v2 (Fase 6, al final): misma interfaz pero descargando desde SharePoint vía
Microsoft Graph API. Nada aguas abajo debe cambiar cuando eso llegue: el motor
solo conoce `cargar(<fuente>)`.
"""
from __future__ import annotations

import os
import pathlib
import unicodedata

import polars as pl

# Raíz del repo: .../apps/api/src/motor/fuentes.py -> subir 4 niveles.
_API_DIR = pathlib.Path(__file__).resolve().parents[2]
CRUDOS_DIR = pathlib.Path(os.environ.get("MOTOR_CRUDOS_DIR", _API_DIR / "data" / "crudos"))

# Fuentes lógicas -> patrones de nombre de archivo (glob, case-insensitive tras
# normalizar). Los patrones son deliberadamente amplios: el nombre exacto de cada
# archivo se fija en la Fase 0 al inventariar las muestras reales; si un patrón
# matchea más de un archivo se usa el de fecha de modificación más reciente.
FUENTES: dict[str, list[str]] = {
    # Ventas transaccionales (RespaldosBBDD): histórico Curifor + Frontera.
    "ventas": ["*venta*"],
    # Stock por bodega Curifor y Frontera (site Abastecimiento-DataBI).
    "stock_bodegas": ["*stock*curifor*", "*stock*bodega*"],
    "stock_bodegas_frontera": ["*stock*frontera*"],
    # Seguimiento de compras (órdenes de compra) por origen.
    "seguimiento_curifor_nacional": ["*seguimiento*nacional*", "*seguimiento*curifor*"],
    "seguimiento_curifor_importado": ["*seguimiento*importado*"],
    "seguimiento_frontera": ["*seguimiento*frontera*"],
    # Fuentes menores.
    "mix_reemplazos": ["*mix*", "*reemplaz*"],
    "dim_sucursal": ["*sucursal*"],
    "catalogo": ["*catalogo*", "*maestro*", "*lista*producto*"],
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _candidatos(fuente: str) -> list[pathlib.Path]:
    if fuente not in FUENTES:
        raise KeyError(f"Fuente desconocida: {fuente!r}. Válidas: {sorted(FUENTES)}")
    if not CRUDOS_DIR.exists():
        return []
    archivos = [
        p for p in CRUDOS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".xlsx", ".xlsm", ".csv")
    ]
    encontrados: list[pathlib.Path] = []
    for patron in FUENTES[fuente]:
        import fnmatch

        encontrados += [
            p for p in archivos
            if fnmatch.fnmatch(_norm(p.name), _norm(patron)) and p not in encontrados
        ]
    return sorted(encontrados, key=lambda p: p.stat().st_mtime, reverse=True)


def ruta_de(fuente: str) -> pathlib.Path:
    """Resuelve el archivo de una fuente. Error claro si no está."""
    candidatos = _candidatos(fuente)
    if not candidatos:
        raise FileNotFoundError(
            f"No se encontró un archivo para la fuente '{fuente}' en {CRUDOS_DIR}.\n"
            f"Patrones buscados: {FUENTES[fuente]}.\n"
            "Descarga el Excel correspondiente desde SharePoint y déjalo en esa "
            "carpeta (ver data/crudos/README.md)."
        )
    return candidatos[0]


def cargar(fuente: str, hoja: str | int | None = None) -> pl.DataFrame:
    """Carga una fuente como DataFrame de polars (xlsx vía fastexcel, csv nativo)."""
    ruta = ruta_de(fuente)
    if ruta.suffix.lower() == ".csv":
        return pl.read_csv(ruta, infer_schema_length=5000)
    kwargs = {"sheet_name": hoja} if isinstance(hoja, str) else (
        {"sheet_id": hoja + 1} if isinstance(hoja, int) else {}
    )
    return pl.read_excel(ruta, **kwargs)


def inventariar() -> str:
    """Reporte de qué hay en la carpeta de crudos: archivo elegido por fuente,
    hojas y columnas. Es la herramienta de la Fase 0 para fijar el mapeo real."""
    lineas = [f"Carpeta de crudos: {CRUDOS_DIR}", ""]
    if not CRUDOS_DIR.exists():
        return "\n".join(lineas + ["(la carpeta no existe todavía)"])
    for fuente in FUENTES:
        candidatos = _candidatos(fuente)
        if not candidatos:
            lineas.append(f"[FALTA] {fuente}: sin archivo (patrones {FUENTES[fuente]})")
            continue
        elegido = candidatos[0]
        lineas.append(f"[OK]    {fuente}: {elegido.name}")
        try:
            df = cargar(fuente)
            lineas.append(f"        {df.height} filas x {df.width} cols")
            lineas.append(f"        columnas: {df.columns}")
        except Exception as e:  # noqa: BLE001 - el inventario no debe morir por un archivo
            lineas.append(f"        (no se pudo leer: {e})")
        extras = [p.name for p in candidatos[1:]]
        if extras:
            lineas.append(f"        otros candidatos ignorados: {extras}")
    sin_asignar = {
        p.name
        for p in CRUDOS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".xlsx", ".xlsm", ".csv")
    } - {c.name for f in FUENTES for c in _candidatos(f)}
    if sin_asignar:
        lineas += ["", f"Archivos sin fuente asignada: {sorted(sin_asignar)}"]
    return "\n".join(lineas)


if __name__ == "__main__":
    print(inventariar())
