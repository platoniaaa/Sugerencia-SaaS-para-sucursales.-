"""Endpoints del modulo Ventas (KPIs + grafico + por-sucursal).

La descarga del Excel sigue en /api/post-venta/export-excel (post_venta router),
porque alli ya esta el armado del archivo grande.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import ventas_post_service

router = APIRouter(prefix="/api/ventas", tags=["ventas"])


@router.get("/kpis")
def kpis(db: Session = Depends(get_db)) -> dict:
    """KPIs del mes mas reciente vs el anterior."""
    return ventas_post_service.kpis(db)


@router.get("/mensual")
def mensual(
    meses: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Serie mensual (ultimos N meses) con totales CLP + unidades."""
    return ventas_post_service.serie_mensual(db, meses=meses)


@router.get("/por-sucursal")
def por_sucursal(
    periodo: str | None = Query(None, description="YYYYMM. Si se omite, el mes mas reciente."),
    db: Session = Depends(get_db),
) -> dict:
    """Lista de sucursales con sus totales para un periodo dado."""
    if not periodo:
        periodos = ventas_post_service.periodos_disponibles(db)
        if not periodos:
            return {"periodo": None, "items": []}
        periodo = periodos[-1]
    items = ventas_post_service.por_sucursal(db, periodo)
    return {"periodo": periodo, "items": items}


@router.get("/lineas")
def lineas(
    periodo_desde: str | None = Query(None),
    periodo_hasta: str | None = Query(None),
    sucursal: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> dict:
    """Lineas detalladas de Post Venta (estilo ERP) con filtros + paginacion."""
    items, total, columnas = ventas_post_service.listar_lineas(
        db,
        periodo_desde=periodo_desde, periodo_hasta=periodo_hasta,
        sucursal=sucursal, q=q, page=page, limit=limit,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "columnas": columnas,
    }
