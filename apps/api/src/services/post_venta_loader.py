"""Carga de la 'Planilla Post Venta' (CSV del Power BI) hacia las tablas post_venta.

Snapshot completo (vacía y reinserta). Cada fila se guarda como arreglo JSON posicional
(valores en el orden de `columnas`), no como objeto con claves, para ocupar poco espacio.
"""
from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from typing import Any

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import PostVentaFila, PostVentaMeta
from .excel_loader import _rows_from_csv, _rows_from_xlsx

settings = get_settings()


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    for ch in (" ", "-", "/", ".", "°", "º"):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def _idx_columna(headers: list[str], *nombres: str) -> int | None:
    """Índice de la cabecera que coincide, respetando la PRIORIDAD de `nombres`.

    Importa porque la planilla trae a la vez 'SUCURSAL' (nombre, ej. RANCAGUA) y 'Local'
    (código, ej. SUC130): queremos el nombre aunque 'Local' aparezca antes.
    """
    norman = [_norm(h) for h in headers]
    for nombre in nombres:
        objetivo = _norm(nombre)
        for i, h in enumerate(norman):
            if h == objetivo:
                return i
    return None


def cargar_post_venta(db: Session, filename: str, content: bytes) -> dict:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        headers, data = _rows_from_csv(content)
    elif name.endswith((".xlsx", ".xlsm")):
        headers, data = _rows_from_xlsx(content)
    else:
        raise ValueError("Formato no soportado. Usa .xlsx o .csv")

    headers = [str(h) if h is not None else "" for h in headers]
    ncols = len(headers)
    i_periodo = _idx_columna(headers, "periodo", "mes")
    i_sucursal = _idx_columna(headers, "sucursal", "local")

    tenant = settings.default_tenant_id
    db.execute(delete(PostVentaFila).where(PostVentaFila.tenant_id == tenant))

    registros: list[dict[str, Any]] = []
    periodos: set[str] = set()
    sucursales: set[str] = set()

    for raw in data:
        # Normaliza a strings y alinea al número de columnas.
        valores = ["" if v is None else str(v) for v in raw][:ncols]
        if len(valores) < ncols:
            valores += [""] * (ncols - len(valores))
        periodo = (valores[i_periodo].strip() if i_periodo is not None else "") or None
        sucursal = (valores[i_sucursal].strip() if i_sucursal is not None else "") or None
        if periodo:
            periodos.add(periodo)
        if sucursal:
            sucursales.add(sucursal)
        registros.append(
            {
                "tenant_id": tenant,
                "periodo": periodo,
                "sucursal": sucursal,
                "datos": json.dumps(valores, ensure_ascii=False),
            }
        )

    for i in range(0, len(registros), 500):
        lote = registros[i : i + 500]
        if lote:
            db.execute(insert(PostVentaFila).values(lote))

    db.execute(delete(PostVentaMeta).where(PostVentaMeta.tenant_id == tenant))
    db.execute(
        insert(PostVentaMeta).values(
            {
                "tenant_id": tenant,
                "columnas": json.dumps(headers, ensure_ascii=False),
                "filas": len(registros),
                "periodos": json.dumps(sorted(periodos), ensure_ascii=False),
                "sucursales": json.dumps(sorted(sucursales), ensure_ascii=False),
                "actualizado_en": datetime.utcnow(),
            }
        )
    )
    db.commit()

    return {
        "filas_cargadas": len(registros),
        "periodos": len(periodos),
        "sucursales": len(sucursales),
        "columnas": ncols,
    }
