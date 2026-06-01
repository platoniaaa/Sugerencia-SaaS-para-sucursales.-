"""Modelos SQLAlchemy de la plataforma."""
from .sugerido import Sugerido
from .sugerencia_manual import SugerenciaManual
from .sugerencia_recurrente import SugerenciaRecurrente
from .dim_producto import DimProducto
from .dim_sucursal import DimSucursal
from .usuario import Usuario
from .venta_mensual import VentaMensual
from .post_venta import PostVentaFila, PostVentaMeta
from .producto_catalogo import ProductoCatalogo
from .stock_unificado import StockUnificado

__all__ = [
    "Sugerido",
    "SugerenciaManual",
    "SugerenciaRecurrente",
    "DimProducto",
    "DimSucursal",
    "Usuario",
    "VentaMensual",
    "PostVentaFila",
    "PostVentaMeta",
    "ProductoCatalogo",
    "StockUnificado",
]
