"""Schemas del catálogo maestro (lista completa de productos del ERP)."""
from pydantic import BaseModel, ConfigDict, Field


class CatalogoRow(BaseModel):
    """Una fila del catálogo maestro (un producto con datos agregados)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    producto: str
    glosa: str | None = None
    familia: str | None = None
    subfamilia: str | None = None
    procedencia: str | None = None
    tipo_repuesto: str | None = None
    categoria: str | None = None
    sub_categoria: str | None = None
    tipo_producto: str | None = None
    clasificacion_stock: str | None = None
    costo: float | None = None
    precio: float | None = None
    stock_total: float | None = None
    stock_minimo: float | None = None
    stock_maximo: float | None = None
    sub_modelo: str | None = None
    cilindrada: str | None = None
    combustible: str | None = None
    anio: str | None = None
    unidad: str | None = None
    reemplazo: str | None = None


class CatalogoPage(BaseModel):
    """Listado paginado del catálogo."""

    items: list[CatalogoRow]
    total: int
    page: int
    limit: int


class CatalogoFiltros(BaseModel):
    """Filtros aplicables al listado del catálogo."""

    q: str | None = None
    familia: list[str] = Field(default_factory=list)
    procedencia: list[str] = Field(default_factory=list)
    categoria: list[str] = Field(default_factory=list)
    con_stock: bool = False


class StockSucursalRow(BaseModel):
    """Desglose de stock en una sucursal/bodega (tabla Stock Unificado del BI)."""

    bodega: str | None = None
    sucursal_id: str | None = None
    stock: float = 0
    origen: str | None = None


class CatalogoDetalle(CatalogoRow):
    """Detalle del producto del catálogo + desglose de stock por sucursal."""

    stock_por_sucursal: list[StockSucursalRow] = Field(default_factory=list)
