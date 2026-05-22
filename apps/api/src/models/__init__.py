"""Modelos SQLAlchemy de la plataforma."""
from .sugerido import Sugerido
from .sugerencia_manual import SugerenciaManual
from .dim_producto import DimProducto
from .dim_sucursal import DimSucursal

__all__ = ["Sugerido", "SugerenciaManual", "DimProducto", "DimSucursal"]
