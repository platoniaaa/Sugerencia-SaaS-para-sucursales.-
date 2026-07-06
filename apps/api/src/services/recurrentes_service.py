"""Lógica de las sugerencias recurrentes: crear, listar, eliminar y procesar.

Comportamiento "mantener vigente": cada vez que una regla se ejecuta, archiva la
instancia que ella misma creó antes y crea una nueva, así no se acumulan.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import SugerenciaManual, SugerenciaRecurrente
from ..schemas import SugeridoFiltros
from . import auditoria_service
from .sugerido_service import pares_filtrados, unidades_desde_dias, unidades_por_par

settings = get_settings()


def _archivar_instancias(db: Session, rec_id: str) -> None:
    db.execute(
        update(SugerenciaManual)
        .where(SugerenciaManual.recurrente_id == rec_id, SugerenciaManual.archivada.is_(False))
        .values(archivada=True)
    )


def _crear_instancias(db: Session, rec: SugerenciaRecurrente) -> int:
    """Archiva la instancia anterior de esta regla y crea la nueva. Devuelve cuántas creó.

    Si la regla esta en modo 'dias de inventario', recalcula unidades en cada ejecucion
    usando la demanda diaria actualizada del BI. Pares sin demanda se omiten.
    """
    _archivar_instancias(db, rec.id)
    tenant = rec.tenant_id
    nuevas: list[SugerenciaManual] = []
    if rec.modo == "individual":
        if rec.dias_inventario:
            u = unidades_desde_dias(db, rec.producto, rec.sucursal_id, rec.dias_inventario)
        else:
            u = rec.unidades
        if u and u > 0:
            nuevas.append(
                SugerenciaManual(
                    producto=rec.producto, sucursal_id=rec.sucursal_id, unidades=u,
                    motivo=rec.motivo, creado_por="recurrente", tenant_id=tenant,
                    recurrente_id=rec.id,
                )
            )
    else:  # grupo
        f = SugeridoFiltros(**json.loads(rec.filtros or "{}"))
        pares = pares_filtrados(db, f)
        if rec.dias_inventario:
            mapa = unidades_por_par(db, pares, rec.dias_inventario)
            for par in pares:
                u = mapa.get(par)
                if not u:
                    continue
                nuevas.append(
                    SugerenciaManual(
                        producto=par[0], sucursal_id=par[1], unidades=u, motivo=rec.motivo,
                        creado_por="recurrente", tenant_id=tenant, recurrente_id=rec.id,
                    )
                )
        else:
            for prod, suc in pares:
                nuevas.append(
                    SugerenciaManual(
                        producto=prod, sucursal_id=suc, unidades=rec.unidades, motivo=rec.motivo,
                        creado_por="recurrente", tenant_id=tenant, recurrente_id=rec.id,
                    )
                )
    db.add_all(nuevas)
    return len(nuevas)


def _avanzar(rec: SugerenciaRecurrente, hoy: date) -> None:
    rec.ultima_ejecucion = hoy
    prox = rec.proxima_ejecucion
    while prox <= hoy:
        prox = prox + timedelta(days=rec.cada_dias)
    rec.proxima_ejecucion = prox
    if rec.fecha_fin and prox > rec.fecha_fin:
        rec.activa = False


def crear(db: Session, payload, usuario_email: str | None = None) -> SugerenciaRecurrente:
    hoy = date.today()
    filtros_json = None
    if payload.modo == "grupo":
        filtros_json = json.dumps((payload.filtros or SugeridoFiltros()).model_dump())
    # Si la regla es por dias de inventario, no requiere un valor de unidades; lo dejamos en 0
    # como placeholder (la columna es NOT NULL) y la regla se recalcula en cada ejecucion.
    unidades_inicial = payload.unidades or 0
    rec = SugerenciaRecurrente(
        tenant_id=settings.default_tenant_id,
        modo=payload.modo,
        producto=payload.producto,
        sucursal_id=payload.sucursal_id,
        filtros=filtros_json,
        unidades=unidades_inicial,
        dias_inventario=payload.dias_inventario,
        motivo=payload.motivo,
        cada_dias=payload.cada_dias,
        fecha_fin=payload.fecha_fin,
        proxima_ejecucion=hoy,
        creado_por=usuario_email or settings.admin_email,
    )
    db.add(rec)
    db.flush()
    # Aplica de inmediato (primera instancia) y agenda la próxima.
    n_creadas = _crear_instancias(db, rec)
    _avanzar(rec, hoy)
    cantidad_str = (
        f"{payload.dias_inventario} dias" if payload.dias_inventario
        else f"{payload.unidades} u"
    )
    auditoria_service.registrar(
        db, accion="recurrente_creada", entidad="sugerencia_recurrente", entidad_id=rec.id,
        usuario_email=usuario_email, producto=rec.producto, sucursal_id=rec.sucursal_id,
        unidades=payload.unidades, dias_inventario=payload.dias_inventario,
        motivo=rec.motivo,
        detalle=f"Recurrente {rec.modo}, +{cantidad_str} cada {rec.cada_dias} dias, "
        f"{n_creadas} instancia(s) creada(s)",
    )
    if usuario_email:
        nombre = usuario_email.split("@")[0]
        titulo = (
            f"{nombre} creo recurrencia para {rec.producto}"
            if rec.modo == "individual" else
            f"{nombre} creo recurrencia ({n_creadas} productos)"
        )
        auditoria_service.notificar(
            db, tipo="recurrente_creada", titulo=titulo,
            mensaje=f"+{cantidad_str} cada {rec.cada_dias} dias",
            creado_por_email=usuario_email,
            producto=rec.producto, sucursal_id=rec.sucursal_id,
        )
    db.commit()
    db.refresh(rec)
    return rec


def listar(db: Session, incluir_inactivas: bool = False) -> list[SugerenciaRecurrente]:
    stmt = select(SugerenciaRecurrente).where(
        SugerenciaRecurrente.tenant_id == settings.default_tenant_id
    )
    if not incluir_inactivas:
        stmt = stmt.where(SugerenciaRecurrente.activa.is_(True))
    stmt = stmt.order_by(SugerenciaRecurrente.creado_en.desc())
    return list(db.scalars(stmt).all())


def eliminar(db: Session, rec_id: str, usuario_email: str | None = None) -> bool:
    rec = db.get(SugerenciaRecurrente, rec_id)
    if not rec:
        return False
    snap = {
        "producto": rec.producto, "sucursal_id": rec.sucursal_id,
        "unidades": rec.unidades, "dias_inventario": rec.dias_inventario,
        "motivo": rec.motivo, "modo": rec.modo, "cada_dias": rec.cada_dias,
    }
    _archivar_instancias(db, rec_id)  # quita su aporte vigente de la compra
    db.delete(rec)
    auditoria_service.registrar(
        db, accion="recurrente_eliminada", entidad="sugerencia_recurrente", entidad_id=rec_id,
        usuario_email=usuario_email, producto=snap["producto"], sucursal_id=snap["sucursal_id"],
        unidades=snap["unidades"], dias_inventario=snap["dias_inventario"], motivo=snap["motivo"],
        detalle=f"Recurrente {snap['modo']} cada {snap['cada_dias']} dias",
    )
    db.commit()
    return True


def procesar(db: Session, hoy: date | None = None) -> dict:
    """Ejecuta todas las reglas vigentes cuyo turno llegó. Lo llama el cron diario."""
    hoy = hoy or date.today()
    recs = list(
        db.scalars(
            select(SugerenciaRecurrente).where(
                SugerenciaRecurrente.activa.is_(True),
                SugerenciaRecurrente.proxima_ejecucion <= hoy,
            )
        ).all()
    )
    creadas = 0
    procesadas = 0
    for rec in recs:
        if rec.fecha_fin and hoy > rec.fecha_fin:
            rec.activa = False
            continue
        n = _crear_instancias(db, rec)
        creadas += n
        _avanzar(rec, hoy)
        procesadas += 1
        auditoria_service.registrar(
            db, accion="recurrente_aplicada", entidad="sugerencia_recurrente",
            entidad_id=rec.id, usuario_email="cron",
            producto=rec.producto, sucursal_id=rec.sucursal_id,
            unidades=rec.unidades, dias_inventario=rec.dias_inventario,
            detalle=f"Ejecucion automatica: {n} instancia(s) creada(s)",
        )
    db.commit()
    return {"recurrencias_procesadas": procesadas, "sugerencias_creadas": creadas}


def archivar_expiradas(db: Session, ahora: datetime | None = None) -> int:
    """Archiva las sugerencias manuales cuya fecha de vencimiento ya paso.

    Archivar (no borrar) preserva el historial, igual que con las instancias de un
    ciclo recurrente anterior. Las sumas del sugerido ya las excluyen al instante via
    expira_en; esto es la limpieza diaria que las saca del listado vigente. Devuelve
    cuantas archivo.
    """
    ahora = ahora or datetime.now(timezone.utc)
    res = db.execute(
        update(SugerenciaManual)
        .where(
            SugerenciaManual.archivada.is_(False),
            SugerenciaManual.expira_en.isnot(None),
            SugerenciaManual.expira_en <= ahora,
        )
        .values(archivada=True)
    )
    n = res.rowcount or 0
    if n:
        auditoria_service.registrar(
            db, accion="expiradas_archivadas", entidad="sugerencia_manual",
            usuario_email="cron",
            detalle=f"Vencimiento automatico: {n} sugerencia(s) manual(es) archivada(s)",
        )
    db.commit()
    return n


def resumen(rec: SugerenciaRecurrente) -> str:
    """Texto corto para mostrar la regla en la UI."""
    if rec.modo == "individual":
        return f"{rec.producto} · {rec.sucursal_id}"
    try:
        f = json.loads(rec.filtros or "{}")
    except json.JSONDecodeError:
        f = {}
    partes: list[str] = []
    if f.get("sucursales"):
        partes.append("Sucursal: " + ", ".join(f["sucursales"]))
    if f.get("filtro1"):
        partes.append("Marca: " + ", ".join(f["filtro1"]))
    if f.get("abc"):
        partes.append("ABC: " + ", ".join(f["abc"]))
    return " · ".join(partes) if partes else "Todos los productos"
