"""Corre el motor con los crudos reales y manda el resultado a la plataforma.

Este es el job que reemplaza al Power BI. Lee los Excel que el usuario publica en
SharePoint (carpeta sincronizada localmente), calcula el sugerido con el motor
—el que tiene paridad demostrada contra el modelo— y sube el CSV a la nube.

    python -m src.jobs.correr_motor_real                # compara (modo sombra)
    python -m src.jobs.correr_motor_real --oficial      # carga de verdad

**Por defecto va en modo SOMBRA**: sube el resultado al endpoint de comparacion,
que contrasta contra lo que produjo el Power BI y guarda un reporte sin tocar la
tabla que ven los compradores. Recien cuando la paridad se sostenga varios dias
se corre con `--oficial`, y ahi el mismo CSV entra por el endpoint de carga.

Configuracion (por entorno, nunca en el repo):
    MOTOR_CRUDOS_DIR      carpeta con los Excel (la biblioteca de SharePoint sincronizada)
    MOTOR_SNAPSHOT_DIR    CSV congelados de las tablas chicas y estables
    PLATAFORMA_API_URL    URL del backend
    PLATAFORMA_EMAIL      credenciales de un usuario admin de la plataforma
    PLATAFORMA_PASSWORD
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

_API_DIR = Path(__file__).resolve().parents[2]
# La carpeta de crudos la resuelve `motor.fuentes` (variable de entorno o .env).
# Tener aqui una copia de esa logica hacia que el job leyera el stock y el
# seguimiento de la carpeta buena y las VENTAS de la copia vieja de data/crudos.
from ..motor import fuentes as _fuentes  # noqa: E402

CRUDOS_DIR = _fuentes.CRUDOS_DIR
SNAPSHOT_DIR = Path(os.environ.get("MOTOR_SNAPSHOT_DIR", _API_DIR / "data" / "paridad"))
SALIDA = _API_DIR / "data" / "sugerido_motor.csv"


def _fin_mes_cerrado(hoy: date) -> date:
    """Primer dia del mes en curso: el motor usa meses CERRADOS."""
    return hoy.replace(day=1)


def _buscar(fuente: str, obligatorio: bool = True) -> Path | None:
    """Archivo de una fuente declarada en `motor.fuentes.FUENTES`.

    Usa esas specs y NO patrones propios: ahi cada fuente ya trae sus exclusiones
    ("seguimiento" nacional excluye importado y frontera). Un patron ad-hoc como
    "*seguimiento*compras*" matchea las tres, y al desempatar por fecha el motor
    terminaba leyendo el importado como si fuera el nacional: 48.000 ordenes de
    compra quedaban fuera y casi todos los productos se quedaban sin proveedor.
    """
    from ..motor import fuentes

    try:
        return fuentes.ruta_de(fuente)
    except FileNotFoundError:
        if obligatorio:
            raise
        return None


def _archivos_de_ventas(fin_mes_cerrado: date) -> list[Path]:
    """Respaldos de venta que cubren la ventana de 12 meses que usa el motor.

    Los respaldos vienen por ano y el historico completo pesa cientos de MB, pero
    el sugerido solo mira los 12 meses cerrados: para jul-2026 alcanzan 2026 y
    2025. Cargar 2018-2024 ademas seria minutos de lectura para nada.
    """
    anios = {str(fin_mes_cerrado.year), str(fin_mes_cerrado.year - 1)}
    if not CRUDOS_DIR.exists():
        return []
    return sorted(
        p for p in CRUDOS_DIR.rglob("*.xlsx")
        if not p.name.startswith("~$")
        and "stock" not in p.name.lower()
        and "seguimiento" not in p.name.lower()
        # Frontera entra por su propia fuente: otro esquema y otros filtros.
        and "frontera" not in p.name.lower()
        and any(a in p.name for a in anios)
    )


def construir_csv(hoy: date | None = None) -> Path:
    """Corre el pipeline completo con los crudos reales y escribe el CSV contrato."""
    from ..motor import fuentes_reales, lectores_excel, pipeline

    hoy = hoy or date.today()
    ventas = _archivos_de_ventas(_fin_mes_cerrado(hoy))
    # Ventas Frontera (E07): opcional, pero sin ellas el motor pierde los combos
    # que solo se venden ahi y subestima la demanda de los que venden en las dos.
    frontera_xlsx = _buscar("ventas_frontera", obligatorio=False)
    ventas_frontera = (
        lectores_excel.leer_ventas_frontera_excel(frontera_xlsx) if frontera_xlsx else None
    )
    fuentes = fuentes_reales.cargar_fuentes_reales(
        stock_curifor_xlsx=_buscar("stock_bodegas"),
        stock_frontera_xlsx=_buscar("stock_bodegas_frontera"),
        snapshot_dir=SNAPSHOT_DIR,
        seguimiento_nacional_xlsx=_buscar("seguimiento_curifor_nacional", obligatorio=False),
        seguimiento_importado_xlsx=_buscar("seguimiento_curifor_importado", obligatorio=False),
        seguimiento_frontera_xlsx=_buscar("seguimiento_frontera", obligatorio=False),
        ventas_xlsx=ventas or None,
        ventas_frontera_crudo=ventas_frontera,
    )
    df = pipeline.ejecutar(fuentes, fin_mes_cerrado=_fin_mes_cerrado(hoy), hoy=hoy)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    return pipeline.exportar_csv(df, SALIDA)


def enviar(csv_path: Path, oficial: bool = False) -> dict:
    """Sube el CSV a la plataforma: comparacion (sombra) o carga (oficial)."""
    import httpx

    base = os.environ.get("PLATAFORMA_API_URL", "http://localhost:8000").rstrip("/")
    email = os.environ.get("PLATAFORMA_EMAIL")
    password = os.environ.get("PLATAFORMA_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "Faltan credenciales: define PLATAFORMA_EMAIL y PLATAFORMA_PASSWORD "
            "en el entorno (nunca en el repo)."
        )

    with httpx.Client(timeout=300) as c:
        r = c.post(f"{base}/api/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        token = r.json()["token"]
        ruta = "/api/admin/cargar-sugerido" if oficial else "/api/admin/motor/comparar"
        with open(csv_path, "rb") as f:
            r = c.post(
                f"{base}{ruta}",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (csv_path.name, f, "text/csv")},
            )
        r.raise_for_status()
        return r.json()


def run(oficial: bool = False) -> int:
    print(f"Crudos: {CRUDOS_DIR}")
    try:
        csv_path = construir_csv()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"CSV generado: {csv_path}")

    try:
        resultado = enviar(csv_path, oficial=oficial)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR al enviar a la plataforma: {e}", file=sys.stderr)
        return 1

    if oficial:
        print(f"CARGA OFICIAL: {resultado.get('filas_cargadas')} filas.")
        for a in resultado.get("advertencias", []):
            print(f"  advertencia: {a}")
    else:
        print(
            f"SOMBRA: paridad {resultado['paridad_pct']}% "
            f"({resultado['filas_comunes']} filas comunes, "
            f"{resultado['filas_solo_motor']} solo motor, "
            f"{resultado['filas_solo_bi']} solo BI)."
        )
        peores = [
            f"{e['producto']}/{e['sucursal_id']}" for e in resultado.get("ejemplos", [])[:5]
        ]
        if peores:
            print(f"  mayores divergencias: {', '.join(peores)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Corre el motor con los crudos reales.")
    ap.add_argument(
        "--oficial",
        action="store_true",
        help="Carga el resultado como sugerido oficial (por defecto solo compara).",
    )
    args = ap.parse_args()
    raise SystemExit(run(oficial=args.oficial))
