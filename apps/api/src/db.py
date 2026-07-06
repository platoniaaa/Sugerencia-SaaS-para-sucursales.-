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
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS empresa VARCHAR",
        "ALTER TABLE sugerencia_manual ADD COLUMN IF NOT EXISTS lote_id VARCHAR",
        "CREATE INDEX IF NOT EXISTS ix_sugmanual_lote ON sugerencia_manual (lote_id)",
        "ALTER TABLE sugerencia_manual ADD COLUMN IF NOT EXISTS expira_en TIMESTAMP WITH TIME ZONE",
        "CREATE INDEX IF NOT EXISTS ix_sugmanual_expira ON sugerencia_manual (expira_en)",
        # 2026-07: traslado lateral + stock por bodega en el sugerido.
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS trasladar_desde VARCHAR",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_linderos INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_curico INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_talca INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_rancagua INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_diez_de_julio_2 INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_chillan INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_cd_repuestos INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_brasil_18 INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_placilla INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_chillan_viejo INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_talca_2 INTEGER",
    ]
    # SQLite NO soporta "ADD COLUMN IF NOT EXISTS" (error de sintaxis que se
    # tragaba el try, dejando bases locales viejas sin las columnas nuevas):
    # se ejecuta sin la clausula y el error por columna duplicada se ignora.
    es_sqlite = settings.database_url.startswith("sqlite")
    for sql in migraciones:
        if es_sqlite and sql.startswith("ALTER TABLE"):
            sql = sql.replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN", 1)
        try:
            # Transaccion por sentencia: una que falle (columna ya existe) no
            # aborta las siguientes (en Postgres abortaria la transaccion entera).
            with engine.begin() as conn:
                conn.execute(text(sql))
        except Exception:
            pass


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: entrega una sesion y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
