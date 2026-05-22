"""Endpoints del catalogo: productos y sucursales."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DimProducto, DimSucursal
from ..schemas import ProductoOut, ProductoPage, SucursalOut

router = APIRouter(prefix="/api", tags=["catalogo"])


@router.get("/productos", response_model=ProductoPage)
def listar_productos(
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    base = select(DimProducto)
    if q:
        like = f"%{q}%"
        base = base.where(
            or_(DimProducto.producto.ilike(like), DimProducto.descripcion.ilike(like))
        )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = db.scalars(
        base.order_by(DimProducto.producto).offset((page - 1) * limit).limit(limit)
    ).all()
    return ProductoPage(items=list(items), total=total, page=page, limit=limit)


@router.get("/productos/{producto}", response_model=ProductoOut)
def detalle_producto(producto: str, db: Session = Depends(get_db)):
    p = db.get(DimProducto, producto)
    if not p:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return p


@router.get("/sucursales", response_model=list[SucursalOut])
def listar_sucursales(db: Session = Depends(get_db)):
    items = db.scalars(select(DimSucursal).order_by(DimSucursal.prioridad_cd)).all()
    return list(items)
