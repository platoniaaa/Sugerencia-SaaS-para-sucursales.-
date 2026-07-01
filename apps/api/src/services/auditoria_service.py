"""Helpers para registrar eventos en `auditoria_log` y disparar notificaciones in-app.

Pensado para que los endpoints solo llamen `registrar(...)` y opcionalmente `notificar(...)`
en un par de lineas. No interrumpe el flujo principal si falla (los logs no deben
romper la accion del usuario).
"""
from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AuditoriaLog, Notificacion

settings = get_settings()


def registrar(
    db: Session,
    *,
    accion: str,
    entidad: str,
    entidad_id: str | None = None,
    usuario_email: str | None = None,
    producto: str | None = None,
    sucursal_id: str | None = None,
    unidades: int | None = None,
    dias_inventario: int | None = None,
    motivo: str | None = None,
    detalle: str | None = None,
) -> AuditoriaLog | None:
    try:
        log = AuditoriaLog(
            tenant_id=settings.default_tenant_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            usuario_email=usuario_email,
            producto=producto,
            sucursal_id=sucursal_id,
            unidades=unidades,
            dias_inventario=dias_inventario,
            motivo=motivo,
            detalle=detalle,
        )
        db.add(log)
        # Se commitea con la transaccion del endpoint.
        db.flush()
        return log
    except Exception:
        # Auditoria no debe romper la accion principal.
        return None


def notificar(
    db: Session,
    *,
    tipo: str,
    titulo: str,
    mensaje: str | None = None,
    creado_por_email: str | None = None,
    producto: str | None = None,
    sucursal_id: str | None = None,
) -> Notificacion | None:
    try:
        n = Notificacion(
            tenant_id=settings.default_tenant_id,
            tipo=tipo,
            titulo=titulo,
            mensaje=mensaje,
            creado_por_email=creado_por_email,
            producto=producto,
            sucursal_id=sucursal_id,
            vistas_por="",
        )
        db.add(n)
        db.flush()
        return n
    except Exception:
        return None


def listar_auditoria(
    db: Session,
    *,
    accion: str | None = None,
    excluir_acciones: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[AuditoriaLog], int]:
    base = select(AuditoriaLog).where(
        AuditoriaLog.tenant_id == settings.default_tenant_id
    )
    if accion is not None:
        base = base.where(AuditoriaLog.accion == accion)
    if excluir_acciones:
        base = base.where(AuditoriaLog.accion.not_in(excluir_acciones))
    total = len(list(db.scalars(base).all()))
    rows = list(
        db.scalars(
            base.order_by(desc(AuditoriaLog.creado_en)).offset(offset).limit(limit)
        ).all()
    )
    return rows, total


def listar_notificaciones(
    db: Session, *, usuario_email: str, solo_no_leidas: bool = False, limit: int = 50
) -> list[Notificacion]:
    rows = list(
        db.scalars(
            select(Notificacion)
            .where(Notificacion.tenant_id == settings.default_tenant_id)
            .order_by(desc(Notificacion.creado_en))
            .limit(limit if not solo_no_leidas else limit * 3)
        ).all()
    )
    if solo_no_leidas:
        rows = [n for n in rows if usuario_email not in _vistas_set(n.vistas_por)][:limit]
    return rows


def contar_no_leidas(db: Session, *, usuario_email: str) -> int:
    rows = list(
        db.scalars(
            select(Notificacion).where(
                Notificacion.tenant_id == settings.default_tenant_id
            )
        ).all()
    )
    return sum(1 for n in rows if usuario_email not in _vistas_set(n.vistas_por))


def marcar_leidas(db: Session, *, usuario_email: str, ids: list[str] | None = None) -> int:
    """Marca como leida(s) por el usuario. Si ids=None, marca todas."""
    stmt = select(Notificacion).where(
        Notificacion.tenant_id == settings.default_tenant_id
    )
    if ids:
        stmt = stmt.where(Notificacion.id.in_(ids))
    n_actualizadas = 0
    for n in db.scalars(stmt).all():
        vistos = _vistas_set(n.vistas_por)
        if usuario_email not in vistos:
            vistos.add(usuario_email)
            n.vistas_por = ",".join(sorted(vistos))
            n_actualizadas += 1
    db.commit()
    return n_actualizadas


def _vistas_set(csv: str | None) -> set[str]:
    if not csv:
        return set()
    return {e.strip() for e in csv.split(",") if e.strip()}
