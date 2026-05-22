"""Endpoints CRUD de las sugerencias manuales."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import SugerenciaManual
from ..schemas import (
    SugerenciaManualCreate,
    SugerenciaManualMasiva,
    SugerenciaManualMasivaResultado,
    SugerenciaManualOut,
    SugerenciaManualUpdate,
)
from ..services import sugerido_service

router = APIRouter(prefix="/api/sugerencias-manuales", tags=["sugerencias manuales"])
settings = get_settings()


@router.get("", response_model=list[SugerenciaManualOut])
def listar(
    producto: str | None = Query(None),
    sucursal_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    stmt = select(SugerenciaManual)
    if producto:
        stmt = stmt.where(SugerenciaManual.producto == producto)
    if sucursal_id:
        stmt = stmt.where(SugerenciaManual.sucursal_id == sucursal_id)
    stmt = stmt.order_by(SugerenciaManual.creado_en.desc())
    return list(db.scalars(stmt).all())


@router.post("", response_model=SugerenciaManualOut, status_code=201)
def crear(payload: SugerenciaManualCreate, db: Session = Depends(get_db)):
    s = SugerenciaManual(
        producto=payload.producto,
        sucursal_id=payload.sucursal_id,
        unidades=payload.unidades,
        motivo=payload.motivo,
        creado_por=settings.admin_email,
        tenant_id=settings.default_tenant_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.post("/masiva", response_model=SugerenciaManualMasivaResultado, status_code=201)
def crear_masiva(payload: SugerenciaManualMasiva, db: Session = Depends(get_db)):
    """Crea una sugerencia manual (misma cantidad) para cada producto x sucursal
    que cumple los filtros. Sirve para los modos 'por grupo' y 'todos'."""
    pares = sugerido_service.pares_filtrados(db, payload.filtros)
    nuevas = [
        SugerenciaManual(
            producto=producto,
            sucursal_id=sucursal_id,
            unidades=payload.unidades,
            motivo=payload.motivo,
            creado_por=settings.admin_email,
            tenant_id=settings.default_tenant_id,
        )
        for producto, sucursal_id in pares
    ]
    db.add_all(nuevas)
    db.commit()
    return SugerenciaManualMasivaResultado(creadas=len(nuevas))


@router.patch("/{id}", response_model=SugerenciaManualOut)
def actualizar(id: str, payload: SugerenciaManualUpdate, db: Session = Depends(get_db)):
    s = db.get(SugerenciaManual, id)
    if not s:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{id}", status_code=204)
def eliminar(id: str, db: Session = Depends(get_db)):
    s = db.get(SugerenciaManual, id)
    if not s:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
    db.delete(s)
    db.commit()
