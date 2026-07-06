"""Endpoints CRUD de las sugerencias manuales."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

# Zona horaria del negocio: el vencimiento se ancla a la medianoche de Chile.
# Si se anclara a UTC, el ultimo dia se recortaria 3-4 horas (la sugerencia
# dejaria de sumar a las 20:00-21:00 hora chilena del propio dia elegido).
TZ_CHILE = ZoneInfo("America/Santiago")


def _expira_en(fecha_limite: date | None) -> datetime | None:
    """Convierte la fecha limite (inclusive) en el instante de vencimiento.

    La sugerencia vive todo el dia elegido (hora de Chile) y vence al comenzar
    el dia siguiente. None si no se pidio fecha limite."""
    if not fecha_limite:
        return None
    if fecha_limite < datetime.now(TZ_CHILE).date():
        raise HTTPException(status_code=422, detail="La fecha limite ya paso.")
    if fecha_limite.year > 2100:
        raise HTTPException(status_code=422, detail="Fecha limite demasiado lejana.")
    inicio = datetime(
        fecha_limite.year, fecha_limite.month, fecha_limite.day, tzinfo=TZ_CHILE
    )
    return (inicio + timedelta(days=1)).astimezone(timezone.utc)

from ..config import get_settings
from ..db import get_db
from ..models import SugerenciaManual
from ..schemas import (
    RecurrenteCreate,
    RecurrenteOut,
    SugerenciaManualCreate,
    SugerenciaManualMasiva,
    SugerenciaManualMasivaResultado,
    SugerenciaManualOut,
    SugerenciaManualUpdate,
)
from ..services import auditoria_service, recurrentes_service, sugerido_service
from ..services.auth import requiere_auth


def _recurrente_out(rec) -> RecurrenteOut:
    return RecurrenteOut(
        id=rec.id, modo=rec.modo, resumen=recurrentes_service.resumen(rec),
        unidades=rec.unidades, dias_inventario=rec.dias_inventario,
        motivo=rec.motivo, cada_dias=rec.cada_dias,
        proxima_ejecucion=rec.proxima_ejecucion, fecha_fin=rec.fecha_fin,
        activa=rec.activa, ultima_ejecucion=rec.ultima_ejecucion,
    )

router = APIRouter(prefix="/api/sugerencias-manuales", tags=["sugerencias manuales"])
settings = get_settings()


@router.get("", response_model=list[SugerenciaManualOut])
def listar(
    producto: str | None = Query(None),
    sucursal_id: str | None = Query(None),
    incluir_archivadas: bool = Query(False, description="Incluir las de ciclos anteriores"),
    solo_unicas: bool = Query(
        False,
        description="Solo sugerencias unicas (no instancias generadas por una regla recurrente)",
    ),
    db: Session = Depends(get_db),
):
    stmt = select(SugerenciaManual)
    if producto:
        stmt = stmt.where(SugerenciaManual.producto == producto)
    if sucursal_id:
        stmt = stmt.where(SugerenciaManual.sucursal_id == sucursal_id)
    if not incluir_archivadas:
        stmt = stmt.where(SugerenciaManual.archivada.is_(False))
    if solo_unicas:
        stmt = stmt.where(SugerenciaManual.recurrente_id.is_(None))
    stmt = stmt.order_by(SugerenciaManual.creado_en.desc())
    return list(db.scalars(stmt).all())


@router.post("", response_model=SugerenciaManualOut, status_code=201)
def crear(
    payload: SugerenciaManualCreate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    if payload.dias_inventario:
        unidades = sugerido_service.unidades_desde_dias(
            db, payload.producto, payload.sucursal_id, payload.dias_inventario
        )
        if unidades is None:
            raise HTTPException(
                status_code=400,
                detail="Sin demanda diaria para este producto/sucursal. Usa modo 'unidades'.",
            )
    elif payload.unidades:
        unidades = payload.unidades
    else:
        raise HTTPException(status_code=400, detail="Falta unidades o dias_inventario.")
    s = SugerenciaManual(
        producto=payload.producto,
        sucursal_id=payload.sucursal_id,
        unidades=unidades,
        motivo=payload.motivo,
        creado_por=email,
        tenant_id=settings.default_tenant_id,
        expira_en=_expira_en(payload.expira_en),
    )
    db.add(s)
    db.flush()
    auditoria_service.registrar(
        db, accion="creada", entidad="sugerencia_manual", entidad_id=s.id,
        usuario_email=email, producto=s.producto, sucursal_id=s.sucursal_id,
        unidades=unidades, dias_inventario=payload.dias_inventario, motivo=payload.motivo,
    )
    auditoria_service.notificar(
        db, tipo="sugerencia_creada",
        titulo=f"{email.split('@')[0]} sugirio {s.producto}",
        mensaje=f"+{unidades} u en {s.sucursal_id}"
        + (f". Motivo: {s.motivo}" if s.motivo else ""),
        creado_por_email=email, producto=s.producto, sucursal_id=s.sucursal_id,
    )
    db.commit()
    db.refresh(s)
    return s


@router.post("/masiva", response_model=SugerenciaManualMasivaResultado, status_code=201)
def crear_masiva(
    payload: SugerenciaManualMasiva,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    """Crea una sugerencia manual para cada producto x sucursal que cumple los filtros.

    Modo 'dias_inventario': calcula unidades por par segun demanda_diaria del BI; los
    pares sin demanda quedan omitidos. Modo 'unidades': mismo numero para todos.

    Todas las filas creadas en esta llamada comparten un mismo `lote_id` (UUID4)
    para poder borrarlas juntas despues con DELETE /lote/{lote_id}.
    """
    import uuid as _uuid_mod

    pares = sugerido_service.pares_filtrados(db, payload.filtros)
    omitidas = 0
    nuevas: list[SugerenciaManual] = []
    lote_id = str(_uuid_mod.uuid4())
    expira_en = _expira_en(payload.expira_en)
    if payload.dias_inventario:
        mapa = sugerido_service.unidades_por_par(db, pares, payload.dias_inventario)
        for par in pares:
            u = mapa.get(par)
            if u is None:
                omitidas += 1
                continue
            nuevas.append(
                SugerenciaManual(
                    producto=par[0], sucursal_id=par[1], unidades=u,
                    motivo=payload.motivo, creado_por=email,
                    tenant_id=settings.default_tenant_id,
                    lote_id=lote_id, expira_en=expira_en,
                )
            )
    elif payload.unidades:
        nuevas = [
            SugerenciaManual(
                producto=p, sucursal_id=s, unidades=payload.unidades,
                motivo=payload.motivo, creado_por=email,
                tenant_id=settings.default_tenant_id,
                lote_id=lote_id, expira_en=expira_en,
            )
            for p, s in pares
        ]
    else:
        raise HTTPException(status_code=400, detail="Falta unidades o dias_inventario.")
    db.add_all(nuevas)
    db.flush()
    cantidad_str = (
        f"{payload.dias_inventario} dias" if payload.dias_inventario
        else f"{payload.unidades} u"
    )
    auditoria_service.registrar(
        db, accion="masiva_creada", entidad="sugerencia_manual",
        entidad_id=lote_id,
        usuario_email=email, unidades=payload.unidades,
        dias_inventario=payload.dias_inventario, motivo=payload.motivo,
        detalle=f"Masiva: {len(nuevas)} pares, {omitidas} omitidos, +{cantidad_str} (lote {lote_id[:8]})",
    )
    auditoria_service.notificar(
        db, tipo="masiva_creada",
        titulo=f"{email.split('@')[0]} cargo {len(nuevas)} sugerencias",
        mensaje=f"+{cantidad_str} por producto"
        + (f". Motivo: {payload.motivo}" if payload.motivo else "")
        + (f". {omitidas} omitidos sin demanda." if omitidas else ""),
        creado_por_email=email,
    )
    db.commit()
    # Si no se creo ninguna (todas omitidas), no devolver lote_id que apunta a nada.
    lote_id_resp = lote_id if nuevas else None
    return SugerenciaManualMasivaResultado(
        creadas=len(nuevas), omitidas=omitidas, lote_id=lote_id_resp
    )


@router.post("/recurrentes", response_model=RecurrenteOut, status_code=201)
def crear_recurrente(
    payload: RecurrenteCreate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    """Crea una regla recurrente y la aplica de inmediato (primera instancia)."""
    if payload.modo == "individual" and not (payload.producto and payload.sucursal_id):
        raise HTTPException(status_code=400, detail="Falta producto o sucursal.")
    if not payload.unidades and not payload.dias_inventario:
        raise HTTPException(status_code=400, detail="Falta unidades o dias_inventario.")
    rec = recurrentes_service.crear(db, payload, usuario_email=email)
    return _recurrente_out(rec)


@router.get("/recurrentes", response_model=list[RecurrenteOut])
def listar_recurrentes(
    incluir_inactivas: bool = Query(False), db: Session = Depends(get_db)
):
    return [_recurrente_out(r) for r in recurrentes_service.listar(db, incluir_inactivas)]


@router.delete("/recurrentes/{id}", status_code=204)
def eliminar_recurrente(
    id: str,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    rec = recurrentes_service.eliminar(db, id, usuario_email=email)
    if not rec:
        raise HTTPException(status_code=404, detail="Recurrencia no encontrada")


@router.delete("/lote/{lote_id}")
def eliminar_lote(
    lote_id: str,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    """Elimina todas las sugerencias creadas en una misma carga masiva.

    Solo borra filas con `recurrente_id` NULL (no toca instancias de reglas
    recurrentes). Si el lote no existe o esta vacio, devuelve 404.
    """
    # Tomamos info representativa (motivo, unidades, etc.) antes de borrar para
    # el log y la notificacion.
    filas = list(
        db.scalars(
            select(SugerenciaManual).where(
                SugerenciaManual.lote_id == lote_id,
                SugerenciaManual.recurrente_id.is_(None),
            )
        ).all()
    )
    if not filas:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    motivo = filas[0].motivo
    n = len(filas)
    for f in filas:
        db.delete(f)
    auditoria_service.registrar(
        db, accion="lote_eliminado", entidad="sugerencia_manual",
        entidad_id=lote_id, usuario_email=email, motivo=motivo,
        detalle=f"Carga masiva eliminada: {n} sugerencias (lote {lote_id[:8]})",
    )
    auditoria_service.notificar(
        db, tipo="lote_eliminado",
        titulo=f"{email.split('@')[0]} elimino una carga masiva",
        mensaje=f"{n} sugerencias eliminadas"
        + (f". Motivo original: {motivo}" if motivo else ""),
        creado_por_email=email,
    )
    db.commit()
    return {"eliminadas": n}


@router.patch("/{id}", response_model=SugerenciaManualOut)
def actualizar(
    id: str,
    payload: SugerenciaManualUpdate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    s = db.get(SugerenciaManual, id)
    if not s:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
    data = payload.model_dump(exclude_unset=True)
    unidades_antes = s.unidades
    cambios = []
    for k, v in data.items():
        antes = getattr(s, k)
        if antes != v:
            cambios.append(f"{k}: {antes} -> {v}")
        setattr(s, k, v)
    if cambios:
        auditoria_service.registrar(
            db, accion="modificada", entidad="sugerencia_manual", entidad_id=s.id,
            usuario_email=email, producto=s.producto, sucursal_id=s.sucursal_id,
            unidades=s.unidades, motivo=s.motivo, detalle="; ".join(cambios),
        )
        if "unidades" in data and unidades_antes != s.unidades:
            auditoria_service.notificar(
                db, tipo="sugerencia_modificada",
                titulo=f"{email.split('@')[0]} ajusto {s.producto}",
                mensaje=f"{s.sucursal_id}: {unidades_antes} -> {s.unidades} u",
                creado_por_email=email, producto=s.producto, sucursal_id=s.sucursal_id,
            )
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{id}", status_code=204)
def eliminar(
    id: str,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    s = db.get(SugerenciaManual, id)
    if not s:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
    snap = {
        "id": s.id, "producto": s.producto, "sucursal_id": s.sucursal_id,
        "unidades": s.unidades, "motivo": s.motivo,
    }
    db.delete(s)
    auditoria_service.registrar(
        db, accion="eliminada", entidad="sugerencia_manual", entidad_id=snap["id"],
        usuario_email=email, producto=snap["producto"], sucursal_id=snap["sucursal_id"],
        unidades=snap["unidades"], motivo=snap["motivo"],
    )
    auditoria_service.notificar(
        db, tipo="sugerencia_eliminada",
        titulo=f"{email.split('@')[0]} elimino sugerencia de {snap['producto']}",
        mensaje=f"{snap['sucursal_id']}: -{snap['unidades']} u",
        creado_por_email=email, producto=snap["producto"], sucursal_id=snap["sucursal_id"],
    )
    db.commit()
