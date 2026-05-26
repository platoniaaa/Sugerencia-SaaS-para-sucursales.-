"""Punto de entrada para Vercel (Python serverless).

Vercel detecta la variable `app` (ASGI) y la sirve. El `vercel.json` reenvia todas
las rutas a este archivo, y FastAPI enruta internamente (/api/health, etc.).
"""
import sys
from pathlib import Path

# Permite importar el paquete `src` (que esta un nivel arriba de /api).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.main import app  # noqa: E402

__all__ = ["app"]
