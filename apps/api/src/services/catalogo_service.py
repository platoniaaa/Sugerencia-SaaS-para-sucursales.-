"""Consulta del catálogo maestro de productos (tabla producto_catalogo)."""
from __future__ import annotations

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ProductoCatalogo
from . import stock_service

settings = get_settings()

SORTABLE = {c.name for c in ProductoCatalogo.__table__.columns}


def _apply_filters(stmt, f):
    stmt = stmt.where(ProductoCatalogo.tenant_id == settings.default_tenant_id)
    if f.q:
        like = f"%{f.q}%"
        stmt = stmt.where(
            or_(ProductoCatalogo.producto.ilike(like), ProductoCatalogo.glosa.ilike(like))
        )
    if f.familia:
        stmt = stmt.where(ProductoCatalogo.familia.in_(f.familia))
    if f.procedencia:
        stmt = stmt.where(ProductoCatalogo.procedencia.in_(f.procedencia))
    if f.categoria:
        stmt = stmt.where(ProductoCatalogo.categoria.in_(f.categoria))
    if f.con_stock:
        stmt = stmt.where(ProductoCatalogo.stock_total > 0)
    return stmt


def _apply_sort(stmt, sort: str | None):
    if not sort:
        return stmt.order_by(ProductoCatalogo.producto.asc())
    desc = sort.startswith("-")
    col_name = sort[1:] if desc else sort
    if col_name in SORTABLE:
        col = getattr(ProductoCatalogo, col_name)
        return stmt.order_by(col.desc().nullslast() if desc else col.asc().nullslast())
    return stmt.order_by(ProductoCatalogo.producto.asc())


def listar(db: Session, f, page: int = 1, limit: int = 100, sort: str | None = None):
    base = _apply_filters(select(ProductoCatalogo), f)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = _apply_sort(base, sort).offset((page - 1) * limit).limit(limit)
    items = list(db.scalars(stmt).all())
    # Enriquecer cada fila con el stock real del BI (sumado entre sucursales).
    # El stock del CSV maestro es un snapshot estatico de cuando se subio.
    stock_map = stock_service.stock_total_por_producto(db, [p.producto for p in items])
    salida = []
    for p in items:
        d = {c.name: getattr(p, c.name) for c in ProductoCatalogo.__table__.columns}
        if p.producto in stock_map:
            d["stock_total"] = stock_map[p.producto]
        salida.append(d)
    return salida, total


def detalle(db: Session, producto: str) -> dict | None:
    """Devuelve los datos del catálogo + desglose de stock por sucursal/bodega."""
    p = db.scalars(
        select(ProductoCatalogo).where(
            ProductoCatalogo.tenant_id == settings.default_tenant_id,
            ProductoCatalogo.producto == producto,
        )
    ).first()
    if not p:
        return None
    d = {c.name: getattr(p, c.name) for c in ProductoCatalogo.__table__.columns}
    desglose = stock_service.stock_por_sucursal(db, producto)
    d["stock_total"] = sum(r["stock"] for r in desglose) if desglose else d.get("stock_total")
    d["stock_por_sucursal"] = desglose
    return d


def opciones_filtros(db: Session) -> dict:
    """Devuelve los valores distintos para poblar dropdowns de filtros."""
    t = settings.default_tenant_id

    def _vals(col):
        rows = db.execute(
            select(distinct(col))
            .where(ProductoCatalogo.tenant_id == t, col.isnot(None), col != "")
            .order_by(col.asc())
        ).all()
        return [r[0] for r in rows]

    return {
        "familias": _vals(ProductoCatalogo.familia),
        "procedencias": _vals(ProductoCatalogo.procedencia),
        "categorias": _vals(ProductoCatalogo.categoria),
    }
