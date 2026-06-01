"""Carga del Stock Unificado (CSV del Power BI) hacia la tabla `stock_unificado`.

Reemplaza el snapshot completo en cada push. La tabla del BI trae 1 fila por
(producto, bodega, origen).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import StockUnificado
from .excel_loader import _norm, _rows_from_csv, _rows_from_xlsx, _to_float

settings = get_settings()

HEADER_ALIASES: dict[str, str] = {
    "producto": "producto",
    "codigo": "producto",
    "bodega": "bodega",
    "sucursal": "sucursal_id",
    "sucursalid": "sucursal_id",
    "sucursal_id": "sucursal_id",
    "stock": "stock",
    "cantidad": "stock",
    "origen": "origen",
    "empresa": "origen",
}


def _mapear(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping: dict[str, str] = {}
    for reg in registros:
        for h in reg.keys():
            if h in mapping:
                continue
            field = HEADER_ALIASES.get(_norm(h))
            if field:
                mapping[h] = field

    filas: list[dict[str, Any]] = []
    for reg in registros:
        v: dict[str, Any] = {}
        for h, field in mapping.items():
            if h not in reg:
                continue
            if field == "stock":
                v[field] = _to_float(reg[h])
            else:
                val = reg[h]
                v[field] = str(val).strip() if val not in (None, "") else None
        filas.append(v)
    return filas


def persistir_stock(db: Session, filas: list[dict[str, Any]]) -> dict:
    """Reemplaza el snapshot completo de `stock_unificado` con las filas dadas."""
    tenant = settings.default_tenant_id
    registros: list[dict[str, Any]] = []
    saltadas = 0
    for f in filas:
        if not f.get("producto"):
            saltadas += 1
            continue
        registros.append(
            {
                "tenant_id": tenant,
                "producto": f["producto"],
                "bodega": f.get("bodega"),
                "sucursal_id": f.get("sucursal_id"),
                "stock": f.get("stock") or 0.0,
                "origen": f.get("origen"),
            }
        )

    db.execute(delete(StockUnificado).where(StockUnificado.tenant_id == tenant))
    for i in range(0, len(registros), 1000):
        lote = registros[i : i + 1000]
        if lote:
            db.execute(insert(StockUnificado).values(lote))
    db.commit()

    return {
        "filas_cargadas": len(registros),
        "filas_omitidas": saltadas,
    }


def cargar_stock(db: Session, filename: str, content: bytes) -> dict:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        headers, data = _rows_from_csv(content)
    elif name.endswith((".xlsx", ".xlsm")):
        headers, data = _rows_from_xlsx(content)
    else:
        raise ValueError("Formato no soportado. Usa .xlsx o .csv")
    registros = [dict(zip(headers, raw)) for raw in data]
    filas = _mapear(registros)
    return persistir_stock(db, filas)
