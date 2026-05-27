"""Modelos SQLAlchemy de la plataforma."""
from .sugerido import Sugerido
from .sugerencia_manual import SugerenciaManual
from .dim_producto import DimProducto
from .dim_sucursal import DimSucursal
from .usuario import Usuario
from .venta_mensual import VentaMensual
from .post_venta import PostVentaFila, PostVentaMeta

__all__ = [
    "Sugerido",
    "SugerenciaManual",
    "DimProducto",
    "DimSucursal",
    "Usuario",
    "VentaMensual",
    "PostVentaFila",
    "PostVentaMeta",
]
