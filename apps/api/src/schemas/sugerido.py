"""Schemas del sugerido: fila, pagina, KPIs, filtros y request de export."""
from pydantic import BaseModel, ConfigDict, Field


class SugeridoRow(BaseModel):
    """Una fila del sugerido (producto x sucursal). Refleja la tabla del BI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    producto: str
    descripcion: str | None = None
    sucursal_id: str
    nombre_sucursal: str | None = None
    clasificacion_abc: str | None = None
    proveedor: str | None = None
    filtro1_final: str | None = None
    tipo_origen: str | None = None
    es_importado: bool | None = None
    unidad_medida: str | None = None
    lead_time_dias: int | None = None
    lt_efectivo: int | None = None
    lt_cd_a_sucursal_dias: int | None = None
    lt_origen: str | None = None
    abastece_cd: str | None = None
    prioridad_cd: int | None = None
    comprar_en_el_cd: str | None = None
    tiene_stock_cd: bool | None = None
    demanda_mensual: float | None = None
    demanda_diaria: float | None = None
    desv_std_mensual: float | None = None
    stock_seguridad: int | None = None
    punto_de_pedido: int | None = None
    costo_unitario: float | None = None
    pedir: str | None = None
    reemplazos: str | None = None
    sugerido_suc: float | None = None
    stock_activo_suc: float | None = None
    stock_en_transito_suc: float | None = None
    stock_en_cd: float | None = None
    sugerido_traslado: float | None = None
    sugerido_compra_neto: float | None = None
    total_sugerido_suc: float | None = None
    total_valor_sugerido_clp: float | None = None
    pedir_flag: str | None = None


class SugeridoPage(BaseModel):
    """Resultado paginado del listado de sugerido."""

    items: list[SugeridoRow]
    total: int
    page: int
    limit: int


class SugeridoKpis(BaseModel):
    """KPIs agregados segun los filtros aplicados."""

    total_sugerido: float = 0
    valor_total_clp: float = 0
    n_productos: int = 0
    n_proveedores: int = 0


class AgrupadoRow(BaseModel):
    """Fila de agregacion (para graficos): un grupo con sus sumas."""

    grupo: str
    total_sugerido: float = 0
    valor_clp: float = 0
    n_productos: int = 0


class SugeridoFiltros(BaseModel):
    """Filtros reutilizables del dashboard (usados por listado, KPIs y export)."""

    q: str | None = None
    sucursales: list[str] = Field(default_factory=list)
    abc: list[str] = Field(default_factory=list)
    filtro1: list[str] = Field(default_factory=list)
    tipo_origen: list[str] = Field(default_factory=list)
    proveedor: str | None = None
    solo_pedir: bool = True


class ExportRequest(BaseModel):
    """Body para exportar a Excel: filtros + columnas visibles."""

    filtros: SugeridoFiltros = Field(default_factory=SugeridoFiltros)
    columnas: list[str] = Field(default_factory=list)  # vacio = columnas por defecto
    sort: str | None = None
