"""Healthcheck."""
from fastapi import APIRouter

router = APIRouter(tags=["sistema"])


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok", "servicio": "sugerido-api"}
