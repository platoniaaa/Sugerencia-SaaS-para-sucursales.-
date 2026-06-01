"""Endpoints de auditoria (log de acciones) y notificaciones in-app."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AuditoriaLog
from ..schemas import (
    AuditoriaLogOut,
    AuditoriaPage,
    MarcarLeidasRequest,
    NotificacionesResponse,
    NotificacionOut,
)
from ..services import auditoria_service
from ..services.auth import requiere_auth

router = APIRouter(tags=["auditoria"])
settings = get_settings()


@router.get("/api/ultima-sincronizacion")
def ultima_sync(db: Session = Depends(get_db)):
    """Devuelve el timestamp de la ultima carga desde Power BI Desktop."""
    log = db.scalars(
        select(AuditoriaLog)
        .where(
            AuditoriaLog.tenant_id == settings.default_tenant_id,
            AuditoriaLog.accion == "powerbi_sincronizado",
        )
        .order_by(desc(AuditoriaLog.creado_en))
        .limit(1)
    ).first()
    if not log:
        return {"creado_en": None, "detalle": None}
    return {"creado_en": log.creado_en, "detalle": log.detalle}


@router.get("/api/auditoria", response_model=AuditoriaPage)
def listar(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows, total = auditoria_service.listar_auditoria(db, limit=limit, offset=offset)
    return AuditoriaPage(
        items=[AuditoriaLogOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )


@router.get("/api/notificaciones", response_model=NotificacionesResponse)
def listar_notificaciones(
    solo_no_leidas: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    rows = auditoria_service.listar_notificaciones(
        db, usuario_email=email, solo_no_leidas=solo_no_leidas, limit=limit
    )
    no_leidas = auditoria_service.contar_no_leidas(db, usuario_email=email)
    items: list[NotificacionOut] = []
    for n in rows:
        vistos = {e.strip() for e in (n.vistas_por or "").split(",") if e.strip()}
        items.append(
            NotificacionOut(
                id=n.id, tipo=n.tipo, titulo=n.titulo, mensaje=n.mensaje,
                creado_por_email=n.creado_por_email, producto=n.producto,
                sucursal_id=n.sucursal_id, creado_en=n.creado_en,
                leida=email in vistos,
            )
        )
    return NotificacionesResponse(items=items, no_leidas=no_leidas)


@router.post("/api/notificaciones/marcar-leidas")
def marcar_leidas(
    payload: MarcarLeidasRequest,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    n = auditoria_service.marcar_leidas(db, usuario_email=email, ids=payload.ids)
    return {"actualizadas": n}
