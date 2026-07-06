"""Tabla `sugerido`: snapshot pre-calculado que viene del Power BI.

Incluye los campos de la tabla del BI + las "medidas" que el BI calcula dinamicamente
(ej. total_sugerido_suc). En Fase 0 todo llega pre-calculado en el Excel/CSV que se sube.
La columna `tenant_id` esta presente desde ya para el multi-tenant de la Fase 2.
"""
from sqlalchemy import Boolean, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Sugerido(Base):
    __tablename__ = "sugerido"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # Empresa del grupo (Curifor / Frontera). Viene del BI desde 2026-06.
    empresa: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # --- Identificacion producto x sucursal ---
    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)
    descripcion: Mapped[str | None] = mapped_column(String, nullable=True)
    sucursal_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    nombre_sucursal: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Clasificacion / origen ---
    clasificacion_abc: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    proveedor: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    filtro1_final: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    tipo_origen: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    es_importado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    unidad_medida: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Lead time ---
    lead_time_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lt_efectivo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lt_cd_a_sucursal_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lt_origen: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Abastecimiento desde CD ---
    abastece_cd: Mapped[str | None] = mapped_column(String, nullable=True)
    prioridad_cd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comprar_en_el_cd: Mapped[str | None] = mapped_column(String, nullable=True)
    tiene_stock_cd: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # --- Demanda / parametros de inventario ---
    demanda_mensual: Mapped[float | None] = mapped_column(Float, nullable=True)
    demanda_diaria: Mapped[float | None] = mapped_column(Float, nullable=True)
    desv_std_mensual: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_seguridad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    punto_de_pedido: Mapped[int | None] = mapped_column(Integer, nullable=True)
    costo_unitario: Mapped[float | None] = mapped_column(Float, nullable=True)
    pedir: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    reemplazos: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Medidas pre-calculadas del BI ---
    sugerido_suc: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_activo_suc: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_en_transito_suc: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_en_cd: Mapped[float | None] = mapped_column(Float, nullable=True)
    sugerido_traslado: Mapped[float | None] = mapped_column(Float, nullable=True)
    sugerido_compra_neto: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_sugerido_suc: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    total_valor_sugerido_clp: Mapped[float | None] = mapped_column(Float, nullable=True)
    pedir_flag: Mapped[str | None] = mapped_column(String, nullable=True)
    # Traslado lateral sugerido: "N unidades desde X; M desde Y" (medida del BI).
    trasladar_desde: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Stock por bodega/sucursal (columnas fisicas del BI, incluyen grupo de
    # reemplazo). Espejo de las columnas hardcodeadas del modelo: si se agrega
    # una sucursal alla, hay que agregarla aca tambien. ---
    stock_linderos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_curico: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_talca: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_rancagua: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_diez_de_julio_2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_chillan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_cd_repuestos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_brasil_18: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_placilla: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_chillan_viejo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_talca_2: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_sugerido_prod_suc", "producto", "sucursal_id"),
    )
