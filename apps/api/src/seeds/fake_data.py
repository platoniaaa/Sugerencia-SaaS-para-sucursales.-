"""Genera datos de ejemplo para que la app arranque sin cargar el CSV real.

Crea ~100 productos repartidos en varias sucursales (incluyendo el CD), con valores
realistas inspirados en Curifor (auto-partes). Ejecutar con:

    python -m src.seeds.fake_data
"""
from __future__ import annotations

import math
import random

from sqlalchemy import delete

from ..config import get_settings
from ..db import SessionLocal, create_all
from ..models import DimProducto, DimSucursal, Sugerido

settings = get_settings()
TENANT = settings.default_tenant_id
random.seed(42)

SUCURSALES = [
    ("CD REPUESTOS", "CD Repuestos", "Metropolitana", "No", 0),
    ("LINDEROS", "Linderos", "Metropolitana", "Si", 1),
    ("RANCAGUA", "Rancagua", "O'Higgins", "Si", 2),
    ("CURICO", "Curico", "Maule", "Si", 3),
    ("TALCA", "Talca", "Maule", "Si", 4),
    ("CHILLAN", "Chillan", "Nuble", "Si", 5),
    ("OFICINAS CENTRALES", "Oficinas Centrales", "Metropolitana", "Si", 6),
]

MARCAS = ["FORD", "BOSCH", "MAHLE", "GM", "DELPHI", "NGK", "VALEO"]
PROVEEDORES = {
    "FORD": ("Ford Motor Company Chile", True, "Importado"),
    "GM": ("General Motors Chile", True, "Importado"),
    "BOSCH": ("Robert Bosch S.A.", False, "Nacional"),
    "MAHLE": ("Mahle Chile Ltda.", False, "Nacional"),
    "DELPHI": ("Delphi Automotive", True, "Importado"),
    "NGK": ("NGK Spark Plug", True, "Frontera"),
    "VALEO": ("Valeo Chile", False, "Nacional"),
}
UNIDADES = ["UNIDAD", "LITRO", "JUEGO", "KIT"]
DESCR = [
    "ACEITE 5W30 LITRO", "FILTRO DE ACEITE", "PASTILLA DE FRENO DEL", "BUJIA IRIDIO",
    "CORREA DISTRIBUCION", "AMORTIGUADOR DEL", "BOMBA DE AGUA", "DISCO DE FRENO",
    "FILTRO DE AIRE", "RADIADOR", "ALTERNADOR", "BATERIA 70AH", "EMBRAGUE KIT",
    "TERMINAL DE DIRECCION", "ROTULA SUSPENSION", "SENSOR OXIGENO",
]

Z = 1.65
CO = 5
DIAS_HABILES_MES = 22


def _ceil(x: float) -> int:
    return int(math.ceil(max(0.0, x)))


def gen_productos(n: int = 100) -> list[dict]:
    productos = []
    for i in range(n):
        marca = random.choice(MARCAS)
        proveedor, importado, tipo = PROVEEDORES[marca]
        code = f"{random.randint(10, 99)} {random.choice('ABXOPR')}{random.randint(1000, 9999)}{random.choice('AB')}"
        productos.append({
            "producto": code,
            "descripcion": f"{random.choice(DESCR)} {marca}",
            "filtro1_final": marca,
            "proveedor": proveedor,
            "es_importado": importado,
            "tipo_origen": tipo,
            "unidad_medida": random.choice(UNIDADES),
            "costo_unitario": round(random.uniform(2000, 180000), 0),
            "abc": random.choices(["A", "B", "C"], weights=[2, 3, 5])[0],
        })
    return productos


def gen_sugerido(productos: list[dict]) -> list[Sugerido]:
    filas: list[Sugerido] = []
    for p in productos:
        # Cada producto aparece en un subconjunto de sucursales.
        sucs = random.sample(SUCURSALES, k=random.randint(2, len(SUCURSALES)))
        for suc_id, suc_nombre, region, abastece, prioridad in sucs:
            demanda_mensual = round(random.uniform(0, 120), 1)
            demanda_diaria = round(demanda_mensual / DIAS_HABILES_MES, 3)
            desv = round(demanda_mensual * random.uniform(0.1, 0.5), 2)
            lt = random.choice([4, 7, 8, 12, 20, 30])
            proteccion = (lt + CO) / DIAS_HABILES_MES
            ss = _ceil(Z * desv * math.sqrt(proteccion))
            punto_pedido = _ceil(demanda_diaria * lt + ss)
            stock_activo = round(random.uniform(0, demanda_mensual * 1.5), 0)
            stock_transito = round(random.uniform(0, demanda_mensual * 0.3), 0)
            stock_optimo = demanda_diaria * (CO + lt) + ss
            sugerido = _ceil(stock_optimo - stock_activo - stock_transito)
            stock_cd = round(random.uniform(0, 200), 0) if suc_id != "CD REPUESTOS" else 0
            traslado = min(sugerido, _ceil(stock_cd)) if abastece == "Si" else 0
            compra_neto = max(0, sugerido - traslado)
            total = traslado + compra_neto
            costo = p["costo_unitario"]

            filas.append(Sugerido(
                tenant_id=TENANT,
                producto=p["producto"],
                descripcion=p["descripcion"],
                sucursal_id=suc_id,
                nombre_sucursal=suc_nombre,
                clasificacion_abc=p["abc"],
                proveedor=p["proveedor"],
                filtro1_final=p["filtro1_final"],
                tipo_origen=p["tipo_origen"],
                es_importado=p["es_importado"],
                unidad_medida=p["unidad_medida"],
                lead_time_dias=lt,
                lt_efectivo=lt,
                lt_cd_a_sucursal_dias=random.choice([1, 2, 3]),
                lt_origen=random.choice(["Por sucursal", "Global proveedor", "Fallback 8 dias"]),
                abastece_cd=abastece,
                prioridad_cd=prioridad,
                comprar_en_el_cd="Si" if abastece == "Si" else "No",
                tiene_stock_cd=stock_cd > 0,
                demanda_mensual=demanda_mensual,
                demanda_diaria=demanda_diaria,
                desv_std_mensual=desv,
                stock_seguridad=ss,
                punto_de_pedido=punto_pedido,
                costo_unitario=costo,
                pedir="Si" if total > 0 else "No",
                reemplazos=None,
                sugerido_suc=float(sugerido),
                stock_activo_suc=float(stock_activo),
                stock_en_transito_suc=float(stock_transito),
                stock_en_cd=float(stock_cd),
                sugerido_traslado=float(traslado),
                sugerido_compra_neto=float(compra_neto),
                total_sugerido_suc=float(total),
                total_valor_sugerido_clp=float(total * costo),
                pedir_flag="Si" if total > 0 else "No",
            ))
    return filas


def run() -> None:
    create_all()
    db = SessionLocal()
    try:
        # Limpiar lo existente del tenant.
        db.execute(delete(Sugerido).where(Sugerido.tenant_id == TENANT))
        db.execute(delete(DimProducto).where(DimProducto.tenant_id == TENANT))
        db.execute(delete(DimSucursal).where(DimSucursal.tenant_id == TENANT))

        productos = gen_productos(100)
        filas = gen_sugerido(productos)
        db.add_all(filas)

        db.add_all([
            DimProducto(
                producto=p["producto"], tenant_id=TENANT, descripcion=p["descripcion"],
                filtro1_final=p["filtro1_final"], unidad_medida=p["unidad_medida"],
                costo_unitario=p["costo_unitario"], proveedor=p["proveedor"],
                es_importado=p["es_importado"],
            )
            for p in productos
        ])
        db.add_all([
            DimSucursal(
                sucursal_id=s[0], tenant_id=TENANT, nombre=s[1], region=s[2],
                abastece_desde_cd=s[3], prioridad_cd=s[4],
            )
            for s in SUCURSALES
        ])
        db.commit()
        print(f"Seed OK: {len(filas)} filas de sugerido, {len(productos)} productos, {len(SUCURSALES)} sucursales.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
