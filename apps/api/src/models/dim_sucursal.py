"""Catalogo de sucursales (`dim_sucursal`)."""
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class DimSucursal(Base):
    __tablename__ = "dim_sucursal"

    sucursal_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    abastece_desde_cd: Mapped[str | None] = mapped_column(String, nullable=True)
    prioridad_cd: Mapped[int | None] = mapped_column(Integer, nullable=True)
