"""Tabla `sugerencia_manual`: sugerencias agregadas a mano por el usuario,
por encima de las que calcula el sistema."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SugerenciaManual(Base):
    __tablename__ = "sugerencia_manual"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sucursal_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    unidades: Mapped[int] = mapped_column(Integer, nullable=False)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)

    creado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    aprobado: Mapped[bool] = mapped_column(Boolean, default=False)
    usado_en_compra: Mapped[bool] = mapped_column(Boolean, default=False)
