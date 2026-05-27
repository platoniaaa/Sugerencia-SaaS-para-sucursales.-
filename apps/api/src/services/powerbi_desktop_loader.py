"""Ingesta desde un Power BI Desktop ABIERTO (instancia local de Analysis Services).

Pensado para el interino local: con Power BI Desktop abierto en el mismo equipo donde
corre el backend, un boton "Actualizar desde Power BI" lee el modelo y carga los datos.

La conexion la hace un script de PowerShell (`scripts/extract_powerbi_desktop.ps1`) via
el proveedor OLE DB MSOLAP, porque `pythonnet` no tiene soporte para Python 3.14. Python
solo orquesta y procesa el JSON resultante.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess

from sqlalchemy.orm import Session

from ..config import get_settings
from . import excel_loader, ventas_loader

settings = get_settings()

# scripts/ esta en la raiz del repo: .../apps/api/src/services/<este archivo>
_SCRIPT = pathlib.Path(__file__).resolve().parents[4] / "scripts" / "extract_powerbi_desktop.ps1"


def _ejecutar_script(dax: str) -> dict:
    if not _SCRIPT.exists():
        raise RuntimeError(f"No se encontro el script {_SCRIPT}")
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_SCRIPT),
            "-Dax",
            dax,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",  # el script emite UTF-8; evitar mojibake en acentos
        timeout=240,
    )
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError((proc.stderr or "").strip() or "El script no devolvio datos.")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Respuesta no valida del script: {out[:300]}") from e


def sync_desktop(db: Session, dax: str | None = None) -> dict:
    """Lee la tabla del sugerido desde el Power BI Desktop abierto y reemplaza el snapshot."""
    consulta = dax or settings.powerbi_dax_query
    data = _ejecutar_script(consulta)

    if not data.get("ok"):
        error = data.get("error") or "No se pudo leer Power BI Desktop."
        if "MSOLAP" in error:
            error += (
                " Falta el proveedor MSOLAP: instala DAX Studio o las 'Analysis Services "
                "client libraries' de Microsoft (ver docs/powerbi-sync.md)."
            )
        raise RuntimeError(error)

    csv_path = data.get("csv")
    if not csv_path or not os.path.exists(csv_path):
        raise RuntimeError("El script no genero el archivo de datos esperado.")

    try:
        with open(csv_path, "rb") as f:
            contenido = f.read()
        # Reutiliza el cargador de CSV (las cabeceras ya vienen limpias: Producto, SucursalID...).
        resultado = excel_loader.cargar_sugerido(db, "sugerido_powerbi.csv", contenido)
    finally:
        try:
            os.remove(csv_path)
        except OSError:
            pass

    resultado["origen"] = "powerbi-desktop"
    resultado["filas_recibidas"] = int(data.get("rows") or 0)
    return resultado


def sync_ventas_desktop(db: Session, dax: str | None = None) -> dict:
    """Lee el histórico de ventas desde el Power BI Desktop abierto y reemplaza el snapshot."""
    consulta = dax or settings.powerbi_ventas_dax
    data = _ejecutar_script(consulta)

    if not data.get("ok"):
        error = data.get("error") or "No se pudo leer Power BI Desktop."
        if "MSOLAP" in error:
            error += (
                " Falta el proveedor MSOLAP: instala DAX Studio o las 'Analysis Services "
                "client libraries' de Microsoft (ver docs/powerbi-sync.md)."
            )
        raise RuntimeError(error)

    csv_path = data.get("csv")
    if not csv_path or not os.path.exists(csv_path):
        raise RuntimeError("El script no generó el archivo de datos esperado.")

    try:
        with open(csv_path, "rb") as f:
            contenido = f.read()
        resultado = ventas_loader.cargar_ventas(db, "ventas_powerbi.csv", contenido)
    finally:
        try:
            os.remove(csv_path)
        except OSError:
            pass

    resultado["origen"] = "powerbi-desktop"
    resultado["filas_recibidas"] = int(data.get("rows") or 0)
    return resultado
