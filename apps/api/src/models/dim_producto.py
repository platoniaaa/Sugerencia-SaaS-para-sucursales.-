"""Catalogo de productos (`dim_producto`)."""
from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class DimProducto(Base):
    __tablename__ = "dim_producto"

    producto: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    descripcion: Mapped[str | None] = mapped_column(String, nullable=True)
    filtro1_final: Mapped[str | None] = mapped_column(String, nullable=True)  # marca/segmento
    unidad_medida: Mapped[str | None] = mapped_column(String, nullable=True)
    costo_unitario: Mapped[float | None] = mapped_column(Float, nullable=True)
    proveedor: Mapped[str | None] = mapped_column(String, nullable=True)
    es_importado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
