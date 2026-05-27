"""Carga del histórico de ventas (CSV del Power BI) hacia la tabla `venta_mensual`.

Tolerante a las cabeceras: normaliza y mapea contra alias conocidos. Reemplaza el
snapshot completo (vacía y reinserta). Espera columnas producto, sucursal, periodo
(YYYYMM) y cantidad.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import VentaMensual
from .excel_loader import _norm, _rows_from_csv, _rows_from_xlsx, _to_float

settings = get_settings()

# Mapa: cabecera_normalizada -> campo del modelo.
HEADER_ALIASES: dict[str, str] = {
    "producto": "producto",
    "codigo": "producto",
    "codigo_producto": "producto",
    "sucursal": "sucursal_id",
    "sucursal_id": "sucursal_id",
    "sucursalid": "sucursal_id",
    "nombre_sucursal": "sucursal_id",
    "periodo": "mes",
    "mes": "mes",
    "anio_mes": "mes",
    "cantidad": "cantidad",
    "cantidad_vendida": "cantidad",
    "venta": "cantidad",
    "ventas": "cantidad",
    "unidades": "cantidad",
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
            if field == "cantidad":
                v[field] = _to_float(reg[h])
            else:
                val = reg[h]
                v[field] = str(val).strip() if val not in (None, "") else None
        filas.append(v)
    return filas


def persistir_ventas(db: Session, filas: list[dict[str, Any]]) -> dict:
    """Reemplaza el snapshot de `venta_mensual` con las filas dadas."""
    tenant = settings.default_tenant_id
    registros: list[dict[str, Any]] = []
    saltadas = 0
    for f in filas:
        if not f.get("producto") or not f.get("sucursal_id") or not f.get("mes"):
            saltadas += 1
            continue
        registros.append(
            {
                "tenant_id": tenant,
                "producto": f["producto"],
                "sucursal_id": f["sucursal_id"],
                "mes": f["mes"],
                "cantidad": f.get("cantidad"),
            }
        )

    db.execute(delete(VentaMensual).where(VentaMensual.tenant_id == tenant))
    for i in range(0, len(registros), 500):
        lote = registros[i : i + 500]
        if lote:
            db.execute(insert(VentaMensual).values(lote))
    db.commit()

    return {
        "filas_cargadas": len(registros),
        "filas_omitidas": saltadas,
    }


def cargar_ventas(db: Session, filename: str, content: bytes) -> dict:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        headers, data = _rows_from_csv(content)
    elif name.endswith((".xlsx", ".xlsm")):
        headers, data = _rows_from_xlsx(content)
    else:
        raise ValueError("Formato no soportado. Usa .xlsx o .csv")
    registros = [dict(zip(headers, raw)) for raw in data]
    filas = _mapear(registros)
    return persistir_ventas(db, filas)
