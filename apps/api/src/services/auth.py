"""Autenticacion simple (email + contrasena) sin dependencias externas.

- Hash de contrasena con PBKDF2-HMAC-SHA256 (stdlib `hashlib`), con salt por usuario.
- Token de sesion firmado con HMAC-SHA256 (estilo JWT HS256), con expiracion.

Sin paquetes nuevos -> cero riesgo de instalacion en local o en la nube.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException

from ..config import get_settings
from ..db import get_db

settings = get_settings()

_PBKDF2_ITER = 200_000


# --------------------------- contrasenas --------------------------- #
def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITER)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, dk_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITER)
        return hmac.compare_digest(base64.b64encode(dk).decode(), dk_b64)
    except Exception:
        return False


# --------------------------- tokens --------------------------- #
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def crear_token(email: str) -> str:
    payload = {"sub": email, "exp": int(time.time()) + settings.token_horas * 3600}
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verificar_token(token: str) -> str | None:
    try:
        body, sig = token.split(".")
        esperado = _b64(
            hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, esperado):
            return None
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload.get("sub")
    except Exception:
        return None


# --------------------------- dependencia FastAPI --------------------------- #
def requiere_auth(authorization: str | None = Header(default=None)) -> str:
    """Valida el header Authorization: Bearer <token>. Devuelve el email."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
    email = verificar_token(authorization[7:])
    if not email:
        raise HTTPException(status_code=401, detail="Sesion invalida o expirada")
    return email


def requiere_admin(email: str = Depends(requiere_auth), db=Depends(get_db)) -> str:
    """Bloquea endpoints reservados a admin. Devuelve el email si es admin."""
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    if not user or not user.es_admin:
        raise HTTPException(status_code=403, detail="Requiere permisos de admin")
    return email
