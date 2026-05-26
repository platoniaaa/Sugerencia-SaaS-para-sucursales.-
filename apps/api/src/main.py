"""Punto de entrada de la API FastAPI.

Levantar con:
    uvicorn src.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import create_all
from .routers import admin, compras, health, productos, sugerencias_manuales, sugerido

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crea las tablas si no existen (Fase 0; en Fase 1+ se usa Alembic).
    # En Vercel (serverless) las tablas ya existen -> se evita el costo en cada arranque.
    import os

    if not os.environ.get("VERCEL"):
        create_all()
    yield


app = FastAPI(
    title="Sugerido de Compras API",
    description="Backend de la plataforma de sugerido de reposicion (Fase 0). Cliente cero: Curifor S.A.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    # Sin login/cookies en esta etapa; False permite usar CORS_ORIGINS="*" sin problemas.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sugerido.router)
app.include_router(productos.router)
app.include_router(sugerencias_manuales.router)
app.include_router(compras.router)
app.include_router(admin.router)


@app.get("/", include_in_schema=False)
def root():
    return {"servicio": "sugerido-api", "docs": "/docs"}
