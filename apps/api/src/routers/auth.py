"""Endpoints de autenticacion: login y datos del usuario actual."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Usuario
from ..services import auth, auditoria_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    email: str
    nombre: str | None = None
    es_admin: bool = False


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    usuario = db.get(Usuario, email)
    if not usuario or not usuario.activo or not auth.verify_password(payload.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    # Registrar el acceso para la vista de auditoria (quien entro y a que hora).
    auditoria_service.registrar(
        db, accion="login", entidad="sesion", usuario_email=email,
        detalle=usuario.nombre,
    )
    db.commit()
    return LoginResponse(
        token=auth.crear_token(email), email=email, nombre=usuario.nombre,
        es_admin=usuario.es_admin,
    )


@router.get("/me")
def me(email: str = Depends(auth.requiere_auth), db: Session = Depends(get_db)):
    usuario = db.get(Usuario, email)
    return {
        "email": email,
        "nombre": usuario.nombre if usuario else None,
        "es_admin": bool(usuario and usuario.es_admin),
    }
