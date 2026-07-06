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
    # Fecha en que la sugerencia deja de tener efecto. NULL = no vence (vive hasta que
    # se elimine a mano). Al pasar esta fecha el cron diario la archiva, y las sumas del
    # sugerido la excluyen al instante (sin esperar al cron).
    expira_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    aprobado: Mapped[bool] = mapped_column(Boolean, default=False)
    usado_en_compra: Mapped[bool] = mapped_column(Boolean, default=False)
    # Archivada = de un ciclo anterior; ya no suma a la compra (pero se conserva el historial).
    archivada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    # Si vino de una regla recurrente, su id (para reemplazar/archivar la instancia anterior).
    recurrente_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Si vino de una carga masiva (por grupo / a todos), todas las filas del mismo lote
    # comparten este UUID. Permite borrar el lote completo en un solo SQL.
    lote_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
