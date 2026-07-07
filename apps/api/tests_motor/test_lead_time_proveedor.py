"""Tests del cálculo de lead time por proveedor desde el seguimiento.

Casos sintéticos con distribuciones conocidas: verifican el percentil de corte
(0.7 si predominan nacionales-reposición, 0.8 si no), el promedio de los que caen
bajo el corte, el N Muestras, el tope de 30 días (salvo importado) y el filtro de motivo.
"""
from datetime import date, timedelta

import polars as pl

from src.motor import lead_time_proveedor as LTP

OC = date(2026, 1, 1)


def _rows(prov, suc, lts, origen="Curifor Nacional", motivo="reposicion"):
    return [
        {"RazonSocial": prov, "SucursalID": suc, "FechaOC": OC,
         "FechaPE": OC + timedelta(days=lt), "Origen": origen, "Motivo": motivo}
        for lt in lts
    ]


def test_percentil_70_y_promedio():
    # nacional+reposicion -> nNac=6 > nOtros=0 -> pctil 0.7.
    # LT [1,1,2,2,3,10]; P70 INC = 2.5; bajo corte [1,1,2,2] -> LT=1.5, N=4.
    df = pl.DataFrame(_rows("PROV A", "LINDEROS", [1, 1, 2, 2, 3, 10]))
    r = LTP.calcular_lead_time_proveedor_sucursal(df)
    fila = r.filter(pl.col("Razon Social Proveedor") == "PROV A").to_dicts()[0]
    assert abs(fila["Lead Time Dias"] - 1.5) < 1e-9
    assert fila["N Muestras"] == 4


def test_percentil_80_cuando_no_predominan_nacionales():
    # todas Frontera (no nacional) -> nNac=0, nOtros=5 -> pctil 0.8.
    # LT [1,2,3,4,20]; P80 INC = rank 0.8*4=3.2 -> 4 + .2*(20-4)=7.2; bajo corte [1,2,3,4] -> 2.5, N=4.
    df = pl.DataFrame(_rows("PROV B", "TALCA", [1, 2, 3, 4, 20], origen="Frontera Nacional", motivo="x"))
    r = LTP.calcular_lead_time_proveedor_sucursal(df)
    fila = r.filter(pl.col("Razon Social Proveedor") == "PROV B").to_dicts()[0]
    assert abs(fila["Lead Time Dias"] - 2.5) < 1e-9
    assert fila["N Muestras"] == 4


def test_tope_30_dias_excluye_no_importado():
    # nacional-reposicion con LT >= 30 se excluye (tope). Solo [5, 10] quedan.
    df = pl.DataFrame(_rows("PROV C", "CURICO", [5, 10, 40, 60]))
    r = LTP.calcular_lead_time_proveedor_sucursal(df)
    fila = r.filter(pl.col("Razon Social Proveedor") == "PROV C").to_dicts()[0]
    # [5,10]: pctil 0.7 -> P70=6.5; bajo corte [5] -> 5.0, N=1.
    assert abs(fila["Lead Time Dias"] - 5.0) < 1e-9
    assert fila["N Muestras"] == 1


def test_importado_sin_tope_30():
    # importado: NO aplica el tope de 30 -> los 4 valores entran a la base.
    df = pl.DataFrame(_rows("PROV D", "LINDEROS", [10, 20, 40, 60], origen="Curifor Importado", motivo="x"))
    r = LTP.calcular_lead_time_proveedor_sucursal(df)
    fila = r.filter(pl.col("Razon Social Proveedor") == "PROV D").to_dicts()[0]
    # nNac=0 (no nacional), nOtros=4 -> pctil 0.8; [10,20,40,60] P80 rank 2.4 -> 40+.4*20=48; bajo [10,20,40]->23.33,N=3.
    assert abs(fila["Lead Time Dias"] - (70 / 3)) < 1e-6
    assert fila["N Muestras"] == 3


def test_motivo_no_reposicion_se_excluye_para_nacional():
    # nacional pero motivo != reposicion -> se excluye del base -> proveedor no aparece.
    df = pl.DataFrame(_rows("PROV E", "TALCA", [5, 6], motivo="compra calzada"))
    r = LTP.calcular_lead_time_proveedor_sucursal(df)
    assert r.filter(pl.col("Razon Social Proveedor") == "PROV E").height == 0


def test_tabla_proveedor_sin_muestras():
    # la tabla por proveedor (global) no lleva N Muestras.
    df = pl.DataFrame(_rows("PROV F", "LINDEROS", [1, 2, 3]))
    r = LTP.calcular_lead_time_proveedor(df)
    assert "N Muestras" not in r.columns
    assert r.filter(pl.col("Razon Social Proveedor") == "PROV F").height == 1
