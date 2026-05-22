"""Job de sincronizacion desde Power BI (para programar diariamente).

Ejecutar manualmente:
    python -m src.jobs.sync_powerbi

Para programarlo en Windows: usar el Programador de tareas apuntando a
`scripts\\sync_powerbi.ps1` (ver README). En la nube: un cron (GitHub Actions,
Azure Container Apps Job, etc.).
"""
from __future__ import annotations

import sys

from ..db import SessionLocal, create_all
from ..services import powerbi_loader


def run() -> int:
    create_all()
    db = SessionLocal()
    try:
        res = powerbi_loader.sync(db)
        print(
            f"Sync Power BI OK: {res['filas_cargadas']} filas cargadas "
            f"({res['filas_recibidas']} recibidas), "
            f"{res['productos']} productos, {res['sucursales']} sucursales."
        )
        for a in res.get("advertencias", []):
            print(f"  advertencia: {a}")
        return 0
    except Exception as e:  # noqa: BLE001 - el job reporta el error y sale con codigo !=0
        print(f"ERROR en la sincronizacion con Power BI: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(run())
