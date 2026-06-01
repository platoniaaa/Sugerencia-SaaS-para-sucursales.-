"""Endpoints del catálogo maestro (~400k productos)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import CatalogoDetalle, CatalogoFiltros, CatalogoPage, CatalogoRow
from ..services import catalogo_service

router = APIRouter(prefix="/api/catalogo", tags=["catalogo"])


def _filtros(
    q: str | None = Query(None, description="Búsqueda en producto o descripción"),
    familia: list[str] = Query(default=[]),
    procedencia: list[str] = Query(default=[]),
    categoria: list[str] = Query(default=[]),
    con_stock: bool = Query(False, description="Solo productos con stock > 0"),
) -> CatalogoFiltros:
    return CatalogoFiltros(
        q=q, familia=familia, procedencia=procedencia,
        categoria=categoria, con_stock=con_stock,
    )


@router.get("", response_model=CatalogoPage)
def listar(
    f: CatalogoFiltros = Depends(_filtros),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=5000),
    sort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    items, total = catalogo_service.listar(db, f, page=page, limit=limit, sort=sort)
    # SQLAlchemy → dict para que from_attributes funcione bien
    return CatalogoPage(
        items=[CatalogoRow.model_validate(i) for i in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/filtros")
def filtros_disponibles(db: Session = Depends(get_db)) -> dict:
    """Devuelve listas únicas de familia/procedencia/categoría para los dropdowns."""
    return catalogo_service.opciones_filtros(db)


@router.get("/{producto:path}", response_model=CatalogoDetalle)
def detalle(producto: str, db: Session = Depends(get_db)):
    """Datos del catálogo del producto + desglose de stock por sucursal/bodega."""
    d = catalogo_service.detalle(db, producto)
    if not d:
        raise HTTPException(status_code=404, detail="Producto no esta en el catalogo")
    return CatalogoDetalle.model_validate(d)
