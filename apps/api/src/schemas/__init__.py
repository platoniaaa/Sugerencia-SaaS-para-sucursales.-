"""Schemas Pydantic (contratos de la API)."""
from .sugerido import (
    SugeridoRow,
    SugeridoPage,
    SugeridoKpis,
    SugeridoFiltros,
    ExportRequest,
    AgrupadoRow,
    VentaMes,
    VentasResponse,
)
from .sugerencia_manual import (
    SugerenciaManualOut,
    SugerenciaManualCreate,
    SugerenciaManualUpdate,
    SugerenciaManualMasiva,
    SugerenciaManualMasivaResultado,
    RecurrenteCreate,
    RecurrenteOut,
)
from .catalogo import ProductoOut, ProductoPage, SucursalOut
from .producto_catalogo import (
    CatalogoRow,
    CatalogoPage,
    CatalogoFiltros,
    CatalogoDetalle,
    StockSucursalRow,
)
from .compras import (
    LineaCarro,
    CarroProveedor,
    CarrosResponse,
    ExportCarrosRequest,
)
from .post_venta import PostVentaMetaOut, PostVentaFiltros

__all__ = [
    "SugeridoRow",
    "SugeridoPage",
    "SugeridoKpis",
    "SugeridoFiltros",
    "ExportRequest",
    "AgrupadoRow",
    "VentaMes",
    "VentasResponse",
    "SugerenciaManualOut",
    "SugerenciaManualCreate",
    "SugerenciaManualUpdate",
    "SugerenciaManualMasiva",
    "SugerenciaManualMasivaResultado",
    "RecurrenteCreate",
    "RecurrenteOut",
    "ProductoOut",
    "ProductoPage",
    "SucursalOut",
    "CatalogoRow",
    "CatalogoPage",
    "CatalogoFiltros",
    "CatalogoDetalle",
    "StockSucursalRow",
    "LineaCarro",
    "CarroProveedor",
    "CarrosResponse",
    "ExportCarrosRequest",
    "PostVentaMetaOut",
    "PostVentaFiltros",
]
