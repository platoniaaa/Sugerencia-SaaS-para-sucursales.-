"""Exporta la 'Planilla Post Venta' del Power BI Desktop ABIERTO a un Excel local.

Autónomo: NO usa la base de datos ni la nube. Lee el modelo abierto vía el script
extract_powerbi_desktop.ps1 (OLE DB MSOLAP), filtra por período y sucursal, y escribe
un .xlsx. Pensado para correrse desde exportar_post_venta.ps1 (doble clic).

Uso:
    python exportar_post_venta.py --salida "C:\\...\\archivo.xlsx" [--desde 202405]
        [--hasta 202505] [--sucursal RANCAGUA]
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import unicodedata
from datetime import date
from pathlib import Path

from openpyxl import Workbook

TABLA = "Planilla Post_venta"
EXCEL_MAX_FILAS = 1_048_575
SCRIPT_PS = Path(__file__).resolve().parent / "extract_powerbi_desktop.ps1"

# Columnas (nombre normalizado) que se escriben como número.
NUM_COLS = {"items", "cantidad", "neto", "total", "costo_neto", "total_neta"}


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    for ch in (" ", "-", "/", ".", "°", "º"):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def _periodo(yyyymm_offset: int) -> str:
    """YYYYMM de hace `yyyymm_offset` meses respecto a hoy (0 = mes actual)."""
    hoy = date.today()
    total = hoy.year * 12 + (hoy.month - 1) - yyyymm_offset
    return f"{total // 12:04d}{total % 12 + 1:02d}"


def construir_dax(desde: str, hasta: str, sucursal: str | None) -> str:
    cond = [f"'{TABLA}'[Periodo] >= {int(desde)}", f"'{TABLA}'[Periodo] <= {int(hasta)}"]
    if sucursal:
        # Comillas dobles escapadas para DAX; el valor puede tener espacios.
        valor = sucursal.replace('"', '""')
        cond.append(f'\'{TABLA}\'[SUCURSAL] = "{valor}"')
    return f"EVALUATE FILTER('{TABLA}', {' && '.join(cond)})"


def ejecutar_extractor(dax: str) -> dict:
    if not SCRIPT_PS.exists():
        raise SystemExit(f"No se encontró el extractor: {SCRIPT_PS}")
    proc = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(SCRIPT_PS), "-Dax", dax,
        ],
        capture_output=True, text=True, encoding="utf-8", timeout=900,
    )
    out = (proc.stdout or "").strip()
    if not out:
        raise SystemExit((proc.stderr or "").strip() or "El extractor no devolvió datos.")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise SystemExit(f"Respuesta no válida del extractor: {out[:300]}")


def csv_a_xlsx(csv_path: str, salida: Path) -> int:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader, [])
        if not headers:
            raise SystemExit("El archivo de datos vino vacío.")
        num_idx = {i for i, c in enumerate(headers) if _norm(c) in NUM_COLS}

        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Post Venta")
        ws.append(headers)
        n = 0
        for fila in reader:
            if num_idx:
                for i in num_idx:
                    if i < len(fila) and fila[i] not in ("", None):
                        try:
                            fila[i] = float(fila[i].replace(",", "."))
                        except (ValueError, AttributeError):
                            pass
            ws.append(fila)
            n += 1
        wb.save(salida)
        return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--desde", default=None, help="YYYYMM (def: hace 12 meses)")
    ap.add_argument("--hasta", default=None, help="YYYYMM (def: mes actual)")
    ap.add_argument("--sucursal", default=None)
    args = ap.parse_args()

    desde = (args.desde or _periodo(11)).strip()
    hasta = (args.hasta or _periodo(0)).strip()
    sucursal = (args.sucursal or "").strip() or None
    if not (desde.isdigit() and hasta.isdigit() and len(desde) == 6 and len(hasta) == 6):
        raise SystemExit("Período inválido. Usa el formato AAAAMM (ej. 202505).")
    if desde > hasta:
        raise SystemExit(f"El período inicial ({desde}) es posterior al final ({hasta}).")

    print(f"Extrayendo Post Venta {desde}–{hasta}"
          + (f", sucursal {sucursal}" if sucursal else ", todas las sucursales") + " ...")
    data = ejecutar_extractor(construir_dax(desde, hasta, sucursal))
    if not data.get("ok"):
        err = data.get("error") or "No se pudo leer Power BI Desktop."
        if "MSOLAP" in err:
            err += " Falta el proveedor MSOLAP (instala DAX Studio o las client libraries de AS)."
        raise SystemExit(err)

    filas = int(data.get("rows") or 0)
    if filas == 0:
        raise SystemExit("No hay filas para ese período/sucursal.")
    if filas > EXCEL_MAX_FILAS:
        raise SystemExit(
            f"Son {filas:,} filas y exceden el máximo de Excel ({EXCEL_MAX_FILAS:,}). "
            "Acota el período o elige una sucursal.".replace(",", ".")
        )

    csv_path = data.get("csv")
    try:
        n = csv_a_xlsx(csv_path, Path(args.salida))
    finally:
        try:
            if csv_path:
                Path(csv_path).unlink(missing_ok=True)
        except OSError:
            pass

    print(f"OK: {n:,} filas escritas en {args.salida}".replace(",", "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
