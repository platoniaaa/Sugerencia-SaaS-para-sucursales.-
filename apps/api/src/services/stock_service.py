"""Consultas sobre stock_unificado: total por producto y desglose por sucursal."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import StockUnificado


def stock_total_por_producto(db: Session, productos: list[str]) -> dict[str, float]:
    """Suma stock total para una lista de códigos. Devuelve {producto: total}.

    Tolerante: si la tabla aún no existe (primer deploy antes del push), devuelve {}.
    """
    if not productos:
        return {}
    stmt = (
        select(StockUnificado.producto, func.coalesce(func.sum(StockUnificado.stock), 0))
        .where(StockUnificado.producto.in_(productos))
        .group_by(StockUnificado.producto)
    )
    try:
        return {p: float(t) for p, t in db.execute(stmt).all()}
    except Exception:
        db.rollback()
        return {}


def stock_por_sucursal(db: Session, producto: str) -> list[dict]:
    """Lista filas (bodega, sucursal_id, stock, origen) de un producto, orden por stock desc."""
    stmt = (
        select(
            StockUnificado.bodega,
            StockUnificado.sucursal_id,
            StockUnificado.stock,
            StockUnificado.origen,
        )
        .where(StockUnificado.producto == producto)
        .order_by(StockUnificado.stock.desc())
    )
    try:
        return [
            {"bodega": b, "sucursal_id": s, "stock": float(st or 0), "origen": o}
            for b, s, st, o in db.execute(stmt).all()
        ]
    except Exception:
        db.rollback()
        return []
