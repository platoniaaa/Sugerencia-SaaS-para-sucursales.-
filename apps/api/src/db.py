"""Configuracion de SQLAlchemy: engine, sesiones y base declarativa."""
import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

# En Vercel (serverless) no se mantienen conexiones entre invocaciones.
EN_SERVERLESS = bool(os.environ.get("VERCEL"))

settings = get_settings()


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos."""


def _make_engine():
    url = settings.database_url
    connect_args: dict = {}
    kwargs: dict = {}
    if url.startswith("sqlite"):
        # SQLite necesita esto para usarse desde varios threads (FastAPI).
        connect_args = {"check_same_thread": False}
        # Asegurar que la carpeta del archivo .db exista (ej. ./data/sugerido.db).
        if ":///" in url:
            db_path = url.split(":///", 1)[1]
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    elif url.startswith("postgresql"):
        # PostgreSQL (Supabase): SSL obligatorio + reciclar conexiones para evitar
        # cortes del pooler. pg8000 habilita TLS via ssl_context.
        kwargs["pool_pre_ping"] = True
        if EN_SERVERLESS:
            # Sin pool persistente: cada invocacion abre/cierra su conexion.
            from sqlalchemy.pool import NullPool

            kwargs["poolclass"] = NullPool
        else:
            kwargs["pool_recycle"] = 300
        if "pg8000" in url and settings.db_ssl:
            import ssl

            ctx = ssl.create_default_context()
            # En redes corporativas con inspeccion TLS (proxy/antivirus) la verificacion
            # del certificado falla. La conexion sigue encriptada; solo no se verifica la
            # cadena. Poner DB_SSL_VERIFY=true si el entorno tiene certificados validos.
            if not settings.db_ssl_verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            connect_args = {"ssl_context": ctx}
    return create_engine(url, connect_args=connect_args, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def create_all() -> None:
    """Crea las tablas si no existen (Fase 0; en Fase 1+ se usa Alembic)."""
    # Importa los modelos para registrarlos en el metadata antes de create_all.
    from . import models  # noqa: F401
    from sqlalchemy import text

    Base.metadata.create_all(bind=engine)
    # Mini-migracion in-line: agregar columnas nuevas a tablas ya creadas.
    # Mientras no haya Alembic, usamos ADD COLUMN IF NOT EXISTS (Postgres y SQLite>=3.35).
    migraciones = [
        "ALTER TABLE sugerencia_recurrente ADD COLUMN IF NOT EXISTS dias_inventario INTEGER",
        "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS es_admin BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    with engine.begin() as conn:
        for sql in migraciones:
            try:
                conn.execute(text(sql))
            except Exception:
                # En SQLite viejo no existe IF NOT EXISTS; lo ignoramos silenciosamente.
                pass


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: entrega una sesion y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
