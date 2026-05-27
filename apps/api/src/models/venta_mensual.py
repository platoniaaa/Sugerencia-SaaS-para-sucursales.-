"""Tabla `venta_mensual`: histórico de ventas por producto/sucursal/mes.

Snapshot que viene del Power BI (tabla 'Ventas Unificadas'). Se usa para mostrar la
tendencia de venta de los últimos 12 meses en la vista de detalle del producto.
`mes` es el período en formato YYYYMM (ej. "202504").
"""
from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class VentaMensual(Base):
    __tablename__ = "venta_mensual"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sucursal_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    mes: Mapped[str] = mapped_column(String, nullable=False, index=True)  # YYYYMM
    cantidad: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_venta_prod_suc_mes", "producto", "sucursal_id", "mes"),
    )
