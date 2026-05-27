"""Endpoints de la Planilla Post Venta: metadatos, conteo y exportación a Excel."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import PostVentaFiltros, PostVentaMetaOut
from ..services import post_venta_service

router = APIRouter(prefix="/api/post-venta", tags=["post-venta"])


@router.get("/meta", response_model=PostVentaMetaOut)
def obtener_meta(db: Session = Depends(get_db)):
    return PostVentaMetaOut(**post_venta_service.meta(db))


@router.get("/contar")
def contar(
    periodo_desde: str | None = Query(None),
    periodo_hasta: str | None = Query(None),
    sucursal: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    return {"filas": post_venta_service.contar(db, periodo_desde, periodo_hasta, sucursal)}


@router.post("/export-excel")
def export_excel(f: PostVentaFiltros, db: Session = Depends(get_db)):
    n = post_venta_service.contar(db, f.periodo_desde, f.periodo_hasta, f.sucursal)
    if n == 0:
        raise HTTPException(status_code=404, detail="No hay filas para esos filtros.")
    if n > post_venta_service.EXCEL_MAX_FILAS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La selección tiene {n:,} filas y excede el máximo de Excel "
                f"({post_venta_service.EXCEL_MAX_FILAS:,}). Acota el período o elige una sucursal."
            ).replace(",", "."),
        )
    meta = post_venta_service.meta(db)
    contenido = post_venta_service.generar_excel(
        db, meta["columnas"], f.periodo_desde, f.periodo_hasta, f.sucursal
    )
    nombre = f"planilla_post_venta_{date.today():%Y%m%d}.xlsx"
    return StreamingResponse(
        iter([contenido]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
