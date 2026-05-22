"""Configuracion de SQLAlchemy: engine, sesiones y base declarativa."""
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

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

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: entrega una sesion y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
