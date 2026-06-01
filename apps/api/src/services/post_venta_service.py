"""Consulta y exportación de la Planilla Post Venta cargada en la base."""
from __future__ import annotations

import io
import json
import unicodedata

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import PostVentaFila, PostVentaMeta

settings = get_settings()

# Límite de Excel: 1.048.576 filas por hoja (menos la cabecera).
EXCEL_MAX_FILAS = 1_048_575

# Columnas (por nombre normalizado) que conviene escribir como número.
_NUM_COLS = {"items", "cantidad", "neto", "total", "costo_neto", "total_neta"}


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    for ch in (" ", "-", "/", ".", "°", "º"):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def meta(db: Session) -> dict:
    m = db.get(PostVentaMeta, settings.default_tenant_id)
    if not m:
        return {"columnas": [], "filas": 0, "periodos": [], "sucursales": [], "actualizado_en": None}
    return {
        "columnas": json.loads(m.columnas or "[]"),
        "filas": m.filas,
        "periodos": json.loads(m.periodos or "[]"),
        "sucursales": json.loads(m.sucursales or "[]"),
        "actualizado_en": m.actualizado_en,
    }


def _stmt_filtrado(periodo_desde, periodo_hasta, sucursal):
    stmt = select(PostVentaFila).where(PostVentaFila.tenant_id == settings.default_tenant_id)
    if periodo_desde:
        stmt = stmt.where(PostVentaFila.periodo >= periodo_desde)
    if periodo_hasta:
        stmt = stmt.where(PostVentaFila.periodo <= periodo_hasta)
    if sucursal:
        stmt = stmt.where(PostVentaFila.sucursal == sucursal)
    return stmt


def contar(db: Session, periodo_desde, periodo_hasta, sucursal) -> int:
    stmt = _stmt_filtrado(periodo_desde, periodo_hasta, sucursal).order_by(None)
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def generar_csv_stream(db: Session, columnas, periodo_desde, periodo_hasta, sucursal):
    """Generador que va emitiendo el CSV fila por fila (streaming real).

    Mucho mas rapido y liviano que el Excel: 45k filas se descargan en segundos
    sin acumular memoria. Excel abre el CSV directamente.
    """
    if not columnas:
        m = db.get(PostVentaMeta, settings.default_tenant_id)
        columnas = json.loads((m.columnas if m else "[]") or "[]")

    # BOM UTF-8 para que Excel reconozca acentos en Windows.
    yield "﻿".encode("utf-8")

    def _esc(v) -> str:
        if v is None:
            return ""
        s = str(v)
        if any(ch in s for ch in [",", '"', "\n", "\r"]):
            return '"' + s.replace('"', '""') + '"'
        return s

    yield (",".join(_esc(c) for c in columnas) + "\n").encode("utf-8")

    stmt = _stmt_filtrado(periodo_desde, periodo_hasta, sucursal).order_by(PostVentaFila.id)
    for fila in db.scalars(stmt).yield_per(2000):
        try:
            valores = json.loads(fila.datos)
        except Exception:
            continue
        # Alinear longitud
        if len(valores) < len(columnas):
            valores = valores + [""] * (len(columnas) - len(valores))
        yield (",".join(_esc(v) for v in valores[: len(columnas)]) + "\n").encode("utf-8")


def generar_excel(db: Session, columnas, periodo_desde, periodo_hasta, sucursal) -> bytes:
    """Excel de la Planilla Post Venta filtrada. write_only para soportar muchas filas."""
    if not columnas:
        m = db.get(PostVentaMeta, settings.default_tenant_id)
        columnas = json.loads((m.columnas if m else "[]") or "[]")

    num_idx = {i for i, c in enumerate(columnas) if _norm(c) in _NUM_COLS}

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Post Venta")
    ws.append(columnas)

    stmt = _stmt_filtrado(periodo_desde, periodo_hasta, sucursal).order_by(PostVentaFila.id)
    for fila in db.scalars(stmt).yield_per(2000):
        valores = json.loads(fila.datos)  # arreglo posicional alineado a `columnas`
        if num_idx:
            for i in num_idx:
                if i < len(valores) and valores[i] not in ("", None):
                    try:
                        valores[i] = float(str(valores[i]).replace(",", "."))
                    except (ValueError, TypeError):
                        pass
        ws.append(valores)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
