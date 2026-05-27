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
)
from .catalogo import ProductoOut, ProductoPage, SucursalOut
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
    "ProductoOut",
    "ProductoPage",
    "SucursalOut",
    "LineaCarro",
    "CarroProveedor",
    "CarrosResponse",
    "ExportCarrosRequest",
    "PostVentaMetaOut",
    "PostVentaFiltros",
]
