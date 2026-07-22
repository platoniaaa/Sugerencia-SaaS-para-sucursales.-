"""Tests de regresión del motor: paridad exacta contra los goldens congelados.

Los fixtures en `fixtures/` son un subconjunto de 107 productos master extraídos del
modelo Power BI (snapshot 10-jul-2026, winsor k=3 + proveedor COALESCE) que cubre
todas las ramas del cálculo (cada clase ABC, centralización CD, importados, frontera,
traslados, empates laterales, aceites mL).
Cada cálculo del motor es por producto, así que el subconjunto conserva la paridad.

Si algún cambio futuro al motor rompe la paridad, estos tests fallan señalando la
etapa y las filas afectadas. Para regenerar los fixtures: `python -m tests_motor.regenerar_fixtures`.
"""
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from src.motor import (
    clasificacion_abc,
    demanda as demanda_mod,
    lead_time as lead_time_mod,
    pipeline,
    safety_stock as safety_stock_mod,
    sugerido as sugerido_mod,
    traslados as traslados_mod,
)

FIXT = Path(__file__).parent / "fixtures"
FIN = date(2026, 7, 1)
HOY = date(2026, 7, 10)
S = {"Producto": pl.Utf8, "SucursalID": pl.Utf8}
CLAVE = ["Producto", "SucursalID"]


def _golden(nombre: str) -> pl.DataFrame:
    return pl.read_csv(FIXT / nombre, schema_overrides=S)


@pytest.fixture(scope="module")
def fuentes():
    return pipeline.cargar_fuentes(FIXT)


@pytest.fixture(scope="module")
def etapas(fuentes):
    abc = clasificacion_abc.calcular_abc(fuentes["ventas"], fuentes["mapeo"], fuentes["dim_producto"], FIN)
    dem = demanda_mod.calcular_demanda(fuentes["ventas"], fuentes["mapeo"], fuentes["dim_producto"], abc, FIN)
    lt = lead_time_mod.calcular_lead_time(
        abc, fuentes["seguimiento"], fuentes["lt_proveedor"], fuentes["lt_proveedor_sucursal"],
        fuentes["dim_sucursal"], fuentes["importados"].get_column("Producto").to_list(),
    )
    ss = safety_stock_mod.calcular_safety_stock(lt, dem)
    sug = sugerido_mod.calcular_sugerido(
        ss, dem, fuentes["stock"], fuentes["stock_frontera"], fuentes["seguimiento_transito"], fuentes["mapeo"], HOY,
    )
    tr = traslados_mod.calcular_traslados(sug, fuentes["mapeo"], fuentes["stock"], fuentes["stock_frontera"], fuentes["dim_sucursal"])
    return {"abc": abc, "dem": dem, "lt": lt, "ss": ss, "sug": sug, "tr": tr}


def _motor_key(df: pl.DataFrame) -> pl.DataFrame:
    return df.rename({"producto_master": "Producto", "sucursal_final": "SucursalID"})


def _mismatch(motor: pl.DataFrame, golden: pl.DataFrame, pares, tol=None):
    """Devuelve las filas donde alguna columna (motor_col, golden_col) difiere.
    Numérico si tol!=None (con BLANK/null == 0 salvo que ambos null); texto si null.
    """
    j = golden.join(_motor_key(motor), on=CLAVE, how="left", suffix="_m")
    cond_ok = pl.lit(True)
    for mcol, gcol in pares:
        m = pl.col(mcol)
        g = pl.col(gcol)
        if tol is not None:
            gm = g.cast(pl.Float64, strict=False)
            mm = m.cast(pl.Float64)
            ambos_null = gm.is_null() & mm.is_null()
            # BLANK de DAX se compara como 0 salvo que el motor también sea null
            igual = ((mm.fill_null(0) - gm.fill_null(0)).abs() <= tol) | ambos_null
        else:
            igual = (m == g) | (m.is_null() & g.is_null())
        cond_ok = cond_ok & igual
    return j.filter(~cond_ok)


def test_abc_paridad(etapas):
    g = _golden("golden_abc.csv")
    d = _mismatch(etapas["abc"], g, [("m3", "m3"), ("m6", "m6"), ("m12", "m12")], tol=0)
    assert d.height == 0, f"meses con venta difieren en {d.height} filas: {d.select(CLAVE).head(5).to_dicts()}"
    d2 = _mismatch(etapas["abc"], g, [("clasificacion_abc", "ABC"), ("clasificacion_abc_agregada", "ABCAgg")])
    assert d2.height == 0, f"clase ABC difiere en {d2.height} filas: {d2.select(CLAVE).head(5).to_dicts()}"


def test_demanda_paridad(etapas):
    g = _golden("golden_demanda.csv")
    d = _mismatch(etapas["dem"], g, [("demanda_mensual", "DemandaMensual"), ("desv_std_mensual", "DesvStd")], tol=0.01)
    assert d.height == 0, f"demanda/desv difieren en {d.height} filas: {d.select(CLAVE).head(5).to_dicts()}"


def test_lead_time_safety_paridad(etapas):
    g = _golden("golden_lt_ss.csv")
    d_txt = _mismatch(etapas["lt"], g, [("proveedor", "Proveedor"), ("lt_origen", "LTOrigen"), ("abastece_cd", "AbasteceCD")])
    assert d_txt.height == 0, f"proveedor/origen/abastece difieren en {d_txt.height}: {d_txt.select(CLAVE).head(5).to_dicts()}"
    d_num = _mismatch(
        etapas["lt"], g,
        [("lead_time_dias", "LeadTimeDias"), ("lt_efectivo", "LTEfectivo"), ("lt_cd_a_sucursal_dias", "LTCDaSucursal")],
        tol=0.05,
    )
    assert d_num.height == 0, f"lead time difiere en {d_num.height}: {d_num.select(CLAVE).head(5).to_dicts()}"
    d_ss = _mismatch(etapas["ss"], g, [("stock_seguridad", "StockSeguridad")], tol=0.5)
    assert d_ss.height == 0, f"safety stock difiere en {d_ss.height}: {d_ss.select(CLAVE).head(5).to_dicts()}"


def test_sugerido_paridad(etapas):
    g = _golden("golden_sugerido.csv")
    d = _mismatch(
        etapas["sug"], g,
        [("sugerido", "Sugerido"), ("stock_activo", "StockActivo"), ("stock_transito", "StockTransito"),
         ("necesidad_bruta", "NecesidadBruta"), ("punto_pedido", "PuntoPedido")],
        tol=0.5,
    )
    assert d.height == 0, f"sugerido/stock difieren en {d.height}: {d.select(CLAVE).head(5).to_dicts()}"
    d_pedir = _mismatch(etapas["sug"], g, [("pedir", "Pedir")])
    assert d_pedir.height == 0, f"pedir difiere en {d_pedir.height}: {d_pedir.select(CLAVE).head(5).to_dicts()}"


def test_traslados_paridad(etapas):
    g = _golden("golden_traslados.csv")
    d = _mismatch(
        etapas["tr"], g,
        [("prioridad_cd", "PrioridadCD"), ("stock_cd", "StockCD"), ("sugerido_traslado", "Traslado"),
         ("compra_neta", "CompraNeto")],
        tol=0.5,
    )
    assert d.height == 0, f"traslado/compra neta difieren en {d.height}: {d.select(CLAVE).head(5).to_dicts()}"
    d_ccd = _mismatch(etapas["tr"], g, [("comprar_en_cd", "ComprarEnCD")])
    assert d_ccd.height == 0, f"comprar en CD difiere en {d_ccd.height}: {d_ccd.select(CLAVE).head(5).to_dicts()}"


def test_traslado_lateral_contenido(etapas):
    """El texto lateral: mismas fuentes+cantidades. Ignora el orden entre stocks
    empatados (el desempate de CONCATENATEX no es determinista en el modelo)."""
    g = _golden("golden_traslados.csv")
    j = g.join(_motor_key(etapas["tr"]), on=CLAVE, how="left")
    canon = lambda c: pl.col(c).str.split("; ").list.sort().list.join("; ")
    d = j.filter(~((canon("Lateral") == canon("trasladar_desde")) | (pl.col("Lateral").is_null() & pl.col("trasladar_desde").is_null())))
    assert d.height == 0, f"lateral (contenido) difiere en {d.height}: {d.select(CLAVE).head(5).to_dicts()}"


def test_pipeline_contrato_columnas(fuentes):
    """El CSV final tiene EXACTArente las columnas del contrato de la plataforma."""
    df = pipeline.ejecutar(fuentes, fin_mes_cerrado=FIN, hoy=HOY)
    salida = pipeline.contrato(df)
    esperadas = [c for c, _ in pipeline._CONTRATO] + [f"Stock {s}" for s in pipeline.P.SUCURSALES_STOCK_COLUMNAS]
    assert salida.columns == esperadas, f"columnas del contrato cambiaron:\n  esperadas={esperadas}\n  reales={salida.columns}"
    assert salida.height == df.height


def test_catalogo_y_costo(fuentes):
    """Con catálogo + costo conectados, las 5 columnas de metadata/valor se llenan
    y el Valor CLP = Sugerido × Costo."""
    df = pipeline.ejecutar(fuentes, fin_mes_cerrado=FIN, hoy=HOY)
    sal = pipeline.contrato(df)
    # Descripcion y Unidad vienen para (casi) todo producto del catálogo.
    assert sal.filter(pl.col("Descripcion").is_not_null()).height > 0
    assert sal.filter(pl.col("Unidad de Medida").is_not_null()).height > 0
    # Valor CLP = Sugerido × Costo donde hay ambos.
    chk = df.filter((pl.col("sugerido") > 0) & pl.col("costo_unitario").is_not_null())
    mal = chk.filter((pl.col("valor_clp") - pl.col("sugerido") * pl.col("costo_unitario")).abs() > 0.5)
    assert mal.height == 0, f"Valor CLP != Sugerido*Costo en {mal.height} filas"


def test_pipeline_export_roundtrip(fuentes, tmp_path):
    df = pipeline.ejecutar(fuentes, fin_mes_cerrado=FIN, hoy=HOY)
    ruta = pipeline.exportar_csv(df, tmp_path / "sugerido_motor.csv")
    # infer_schema_length=0 -> todo Utf8, para inspeccionar el texto tal como se escribió.
    relee = pl.read_csv(ruta, infer_schema_length=0)
    assert relee.height == df.height
    assert "total_sugerido_suc" in relee.columns and "trasladar_desde" in relee.columns
    # Es Importado / Tiene Stock CD como texto True/False (igual que la sync).
    assert set(relee.get_column("Es Importado").unique()).issubset({"True", "False"})


def test_abc_solo_toma_combos_de_los_ultimos_12_meses():
    """El DAX arma CombosVenta desde Ventas12m, no desde todo el historico.

    Sacarlos de todas las ventas cargadas agregaba una fila por cada combo que
    vendio ANTES de la ventana y nada dentro: 6.769 filas fantasma, todas clase D
    con m3=m6=m12=0, que el modelo no tiene."""
    fin = date(2026, 7, 1)  # ventana: 202507..202606
    ventas = pl.DataFrame({
        "Producto": ["DENTRO", "FUERA"],
        "SUCURSAL": ["TALCA", "TALCA"],
        "TipoVenta": ["VTA MESON", "VTA MESON"],
        "Fecha": [date(2026, 3, 10), date(2025, 1, 15)],
        "CantidadAjustada": [5, 5],
        "Fuente": ["Curifor", "Curifor"],
    })
    vacio_mapeo = pl.DataFrame(schema={"Producto": pl.Utf8, "Producto_Master": pl.Utf8})
    dim = pl.DataFrame({"Producto": ["DENTRO", "FUERA"], "Categoria": ["MECANICA", "MECANICA"]})

    abc = clasificacion_abc.calcular_abc(ventas, vacio_mapeo, dim, fin)
    assert abc["producto_master"].to_list() == ["DENTRO"]


def test_costo_acepta_coma_decimal():
    """El Excel de stock trae el costo con coma decimal ('95233,75000000') y el
    snapshot congelado con punto. Un cast a secas devolvia null para TODOS los del
    Excel: Costo Unitario -y con el, el valor en CLP- vacio en el 100% de las filas."""
    df = pl.DataFrame({"Costo": ["95233,75000000", "25933", "1.234,50", " -", None]})
    assert df.select(pipeline._valor("Costo").alias("v"))["v"].to_list() == [
        95233.75, 25933.0, 1234.5, None, None,
    ]
