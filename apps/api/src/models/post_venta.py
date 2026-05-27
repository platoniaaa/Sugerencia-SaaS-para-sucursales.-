"""Tablas para exportar la 'Planilla Post Venta' del BI desde la web.

La tabla del BI es enorme (1,4M filas), así que a la nube se sube solo una ventana
acotada (el año en curso). Para que ocupe poco, cada fila guarda sus valores como un
ARREGLO JSON posicional (sin repetir los nombres de columna en cada fila); los nombres
viven una sola vez en `PostVentaMeta.columnas`. `periodo` y `sucursal` van como columnas
indexadas para filtrar la exportación.
"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class PostVentaFila(Base):
    __tablename__ = "post_venta_fila"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    periodo: Mapped[str | None] = mapped_column(String, nullable=True, index=True)  # YYYYMM
    sucursal: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    datos: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array posicional

    __table_args__ = (
        Index("ix_postventa_periodo_suc", "periodo", "sucursal"),
    )


class PostVentaMeta(Base):
    __tablename__ = "post_venta_meta"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True, default="curifor")
    columnas: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list (orden)
    filas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    periodos: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    sucursales: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
