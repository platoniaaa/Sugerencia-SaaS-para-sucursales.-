"""Endpoints para tareas programadas (cron). Públicos pero protegidos por un secreto.

Los llama un workflow de GitHub Actions (no un usuario), por eso no usan el login normal
sino una cabecera 'X-Cron-Secret' que debe coincidir con CRON_SECRET del entorno.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..services import recurrentes_service

router = APIRouter(prefix="/api/cron", tags=["cron"])
settings = get_settings()


def _verificar(secret: str | None) -> None:
    if not settings.cron_secret or secret != settings.cron_secret:
        raise HTTPException(status_code=403, detail="No autorizado")


@router.post("/procesar-recurrentes")
def procesar_recurrentes(
    x_cron_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Crea las sugerencias de las reglas recurrentes que tocan hoy y archiva las
    sugerencias manuales cuya duracion ya vencio."""
    _verificar(x_cron_secret)
    resultado = recurrentes_service.procesar(db)
    resultado["expiradas_archivadas"] = recurrentes_service.archivar_expiradas(db)
    return resultado
