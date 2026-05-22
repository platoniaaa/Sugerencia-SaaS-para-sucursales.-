"""Ingesta desde un Power BI Desktop ABIERTO (instancia local de Analysis Services).

Pensado para el interino local: con Power BI Desktop abierto en el mismo equipo donde
corre el backend, un boton "Actualizar desde Power BI" lee el modelo y carga los datos.

La conexion la hace un script de PowerShell (`scripts/extract_powerbi_desktop.ps1`) via
el proveedor OLE DB MSOLAP, porque `pythonnet` no tiene soporte para Python 3.14. Python
solo orquesta y procesa el JSON resultante.
"""
from __future__ import annotations

import json
import pathlib
import subprocess

from sqlalchemy.orm import Session

from ..config import get_settings
from . import excel_loader, powerbi_loader

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

    rows = data.get("rows") or []
    if isinstance(rows, dict):  # PowerShell serializa 1 fila como objeto, no como lista.
        rows = [rows]

    registros = powerbi_loader.transformar(rows)
    filas, detectadas, ignoradas = excel_loader.procesar_registros(registros)
    resultado = excel_loader.persistir_filas(db, filas, detectadas, ignoradas)
    resultado["origen"] = "powerbi-desktop"
    resultado["filas_recibidas"] = len(rows)
    return resultado
