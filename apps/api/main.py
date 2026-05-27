"""Punto de entrada para Vercel (Python serverless).

Asegura que la carpeta del proyecto (donde vive `src/`) este en el path de importacion
y expone la app FastAPI. Vercel enruta todas las peticiones hacia `app`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import app  # noqa: E402

__all__ = ["app"]
