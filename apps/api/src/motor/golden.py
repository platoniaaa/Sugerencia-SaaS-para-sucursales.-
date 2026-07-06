"""Golden snapshot: congela el `sugerido` que hoy produce el Power BI.

Lee la tabla `sugerido` de la base configurada en .env (Supabase, que el
pipeline original de Power BI sigue actualizando a diario) y la guarda como
CSV de referencia. Los tests de paridad del motor comparan contra este archivo.

Uso:
    python -m src.motor.golden            # escribe data/golden/sugerido_golden_<fecha>.csv
Solo LEE de la base; no escribe nada en ella.
"""
from __future__ import annotations

import csv
import pathlib
from datetime import date

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Sugerido

GOLDEN_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "golden"

# Columnas del contrato, en orden estable (las mismas del modelo ORM).
COLUMNAS = [c.name for c in Sugerido.__table__.columns if c.name != "id"]


def exportar(destino: pathlib.Path | None = None) -> pathlib.Path:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    destino = destino or GOLDEN_DIR / f"sugerido_golden_{date.today():%Y%m%d}.csv"

    db = SessionLocal()
    try:
        filas = db.scalars(select(Sugerido)).all()
        if not filas:
            raise RuntimeError(
                "La tabla `sugerido` está vacía en la base configurada. "
                "Corre primero una sync del pipeline original de Power BI."
            )
        with open(destino, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(COLUMNAS)
            for s in filas:
                w.writerow([getattr(s, c) for c in COLUMNAS])
    finally:
        db.close()
    return destino


if __name__ == "__main__":
    ruta = exportar()
    print(f"Golden snapshot escrito: {ruta}")
