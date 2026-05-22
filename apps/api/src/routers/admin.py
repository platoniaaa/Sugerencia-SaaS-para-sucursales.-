"""Endpoints de administracion: carga del sugerido (Excel/CSV o desde Power BI)."""
import subprocess

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..services import excel_loader, powerbi_desktop_loader, powerbi_loader

router = APIRouter(prefix="/api/admin", tags=["admin"])
settings = get_settings()


@router.post("/cargar-sugerido")
async def cargar_sugerido(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Recibe el Excel/CSV exportado del Power BI y reemplaza la tabla `sugerido`."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo esta vacio")
    try:
        resumen = excel_loader.cargar_sugerido(db, file.filename or "", content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return resumen


@router.get("/powerbi/estado")
def powerbi_estado() -> dict:
    """Indica si la sincronizacion automatica con Power BI esta configurada."""
    return {"configurado": settings.powerbi_configurado}


@router.post("/cargar-desde-powerbi")
def cargar_desde_powerbi(db: Session = Depends(get_db)):
    """Trae la tabla del sugerido directo desde Power BI (API) y reemplaza el snapshot."""
    if not settings.powerbi_configurado:
        raise HTTPException(
            status_code=503,
            detail="Power BI no esta configurado. Define las variables POWERBI_* en .env",
        )
    try:
        return powerbi_loader.sync(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (RuntimeError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=f"Error consultando Power BI: {e}") from e


@router.post("/cargar-desde-powerbi-desktop")
def cargar_desde_powerbi_desktop(db: Session = Depends(get_db)):
    """Lee el sugerido desde un Power BI Desktop ABIERTO en este equipo y lo carga."""
    try:
        return powerbi_desktop_loader.sync_desktop(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Power BI Desktop no respondio a tiempo.") from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
