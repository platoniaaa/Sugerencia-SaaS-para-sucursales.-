"""Schemas Pydantic (contratos de la API)."""
from .sugerido import (
    SugeridoRow,
    SugeridoPage,
    SugeridoKpis,
    SugeridoFiltros,
    ExportRequest,
    AgrupadoRow,
)
from .sugerencia_manual import (
    SugerenciaManualOut,
    SugerenciaManualCreate,
    SugerenciaManualUpdate,
    SugerenciaManualMasiva,
    SugerenciaManualMasivaResultado,
)
from .catalogo import ProductoOut, ProductoPage, SucursalOut

__all__ = [
    "SugeridoRow",
    "SugeridoPage",
    "SugeridoKpis",
    "SugeridoFiltros",
    "ExportRequest",
    "AgrupadoRow",
    "SugerenciaManualOut",
    "SugerenciaManualCreate",
    "SugerenciaManualUpdate",
    "SugerenciaManualMasiva",
    "SugerenciaManualMasivaResultado",
    "ProductoOut",
    "ProductoPage",
    "SucursalOut",
]
