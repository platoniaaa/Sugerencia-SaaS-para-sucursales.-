"""Hace importable `src.motor` al correr `pytest tests_motor` desde apps/api,
sin depender de PYTHONPATH ni de las dependencias de la plataforma (fastapi, etc.).
"""
import sys
from pathlib import Path

# apps/api/ es el padre de tests_motor/; ahí vive el paquete `src`.
_API_DIR = Path(__file__).resolve().parents[1]
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))
