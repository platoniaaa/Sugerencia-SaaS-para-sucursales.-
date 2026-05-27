"""Job que lee el Power BI Desktop ABIERTO y carga el sugerido en la base configurada.

Sirve para EMPUJAR datos desde el PC de Francisco hacia la nube (Supabase): basta con
poner DATABASE_URL apuntando a la base de la nube en el .env y ejecutar:

    python -m src.jobs.sync_powerbi_desktop

(o usar el script scripts/push_to_cloud.ps1, que hace esto con un doble clic).

Requiere: Power BI Desktop abierto con el modelo + proveedor MSOLAP instalado.
"""
from __future__ import annotations

import sys

from ..config import get_settings
from ..db import SessionLocal, create_all
from ..services import powerbi_desktop_loader


def run() -> int:
    settings = get_settings()
    destino = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Destino de la carga: {destino}")
    create_all()
    db = SessionLocal()
    try:
        res = powerbi_desktop_loader.sync_desktop(db)
        print(
            f"OK sugerido: {res['filas_cargadas']} filas cargadas "
            f"({res.get('filas_recibidas', '?')} recibidas), "
            f"{res['productos']} productos, {res['sucursales']} sucursales."
        )
        for a in res.get("advertencias", []):
            print(f"  advertencia: {a}")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR sugerido: {e}", file=sys.stderr)
        return 1

    # Ventas (histórico 12 meses). No es crítico: si falla, el sugerido ya quedó cargado.
    try:
        vres = powerbi_desktop_loader.sync_ventas_desktop(db)
        print(
            f"OK ventas: {vres['filas_cargadas']} filas cargadas "
            f"({vres.get('filas_recibidas', '?')} recibidas)."
        )
    except Exception as e:  # noqa: BLE001
        print(f"AVISO ventas (continuo igual): {e}", file=sys.stderr)

    # Planilla Post Venta (solo año en curso, para exportar desde la web). No es crítico.
    try:
        pres = powerbi_desktop_loader.sync_post_venta_desktop(db)
        print(
            f"OK post-venta: {pres['filas_cargadas']} filas cargadas "
            f"({pres.get('filas_recibidas', '?')} recibidas), "
            f"{pres['periodos']} períodos, {pres['sucursales']} sucursales."
        )
    except Exception as e:  # noqa: BLE001
        print(f"AVISO post-venta (continuo igual): {e}", file=sys.stderr)

    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
