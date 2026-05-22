"""Endpoints del sugerido: listado, KPIs, detalle y export a Excel."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import (
    AgrupadoRow,
    ExportRequest,
    SugeridoFiltros,
    SugeridoKpis,
    SugeridoPage,
    SugeridoRow,
)
from ..services import excel_export, sugerido_service

router = APIRouter(prefix="/api/sugerido", tags=["sugerido"])


def _filtros(
    q: str | None = Query(None, description="Busqueda en producto o descripcion"),
    sucursal: list[str] = Query(default=[], description="Nombres de sucursal"),
    abc: list[str] = Query(default=[], description="Clasificacion ABC"),
    filtro1: list[str] = Query(default=[], description="Marca / segmento"),
    tipo_origen: list[str] = Query(default=[]),
    proveedor: str | None = Query(None),
    solo_pedir: bool = Query(True, description="Mostrar solo pedir=Si"),
) -> SugeridoFiltros:
    return SugeridoFiltros(
        q=q, sucursales=sucursal, abc=abc, filtro1=filtro1,
        tipo_origen=tipo_origen, proveedor=proveedor, solo_pedir=solo_pedir,
    )


@router.get("", response_model=SugeridoPage)
def listar(
    f: SugeridoFiltros = Depends(_filtros),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=5000),
    sort: str | None = Query(None, description="Campo de orden, prefijo '-' para desc"),
    db: Session = Depends(get_db),
):
    items, total = sugerido_service.listar(db, f, page=page, limit=limit, sort=sort)
    return SugeridoPage(items=items, total=total, page=page, limit=limit)


@router.get("/kpis", response_model=SugeridoKpis)
def kpis(f: SugeridoFiltros = Depends(_filtros), db: Session = Depends(get_db)):
    return SugeridoKpis(**sugerido_service.kpis(db, f))


@router.get("/agrupado", response_model=list[AgrupadoRow])
def agrupado(
    por: str = Query("sucursal", description="Dimension: sucursal | marca | proveedor"),
    f: SugeridoFiltros = Depends(_filtros),
    db: Session = Depends(get_db),
):
    try:
        return sugerido_service.agrupado(db, f, por)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{producto}/{sucursal_id}", response_model=SugeridoRow)
def detalle(producto: str, sucursal_id: str, db: Session = Depends(get_db)):
    row = sugerido_service.detalle(db, producto, sucursal_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe sugerido para ese producto/sucursal")
    return row


@router.post("/export-excel")
def export_excel(req: ExportRequest, db: Session = Depends(get_db)):
    # Trae todas las filas que cumplen el filtro (sin paginar) para el Excel.
    items, _ = sugerido_service.listar(db, req.filtros, page=1, limit=100000, sort=req.sort)
    contenido = excel_export.generar_excel(items, req.columnas)
    nombre = excel_export.nombre_archivo()
    return StreamingResponse(
        iter([contenido]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
