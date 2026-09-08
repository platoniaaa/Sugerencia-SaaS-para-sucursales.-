"""Tests de regresión del motor: paridad exacta contra los goldens congelados.

Los fixtures en `fixtures/` son un subconjunto de 107 productos master extraídos del
modelo Power BI (snapshot 10-jul-2026, winsor k=3 + proveedor COALESCE) que cubre
todas las ramas del cálculo (cada clase ABC, centralización CD, importados, frontera,
traslados, empates laterales, aceites mL).
Cada cálculo del motor es por producto, así que el subconjunto conserva la paridad.

Si algún cambio futuro al motor rompe la paridad, estos tests fallan señalando la
etapa y las filas afectadas. Para regenerar los fixtures: `python -m tests_motor.regenerar_fixtures`.
"""
import math
from contextlib import contextmanager
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


@contextmanager
def _gestion(dias: int):
    """Fija los dias de gestion de Abastecimiento mientras dure el bloque."""
    from src.motor import parametros as P

    original = P.LT_GESTION_ABASTECIMIENTO_DIAS
    P.LT_GESTION_ABASTECIMIENTO_DIAS = dias
    try:
        yield
    finally:
        P.LT_GESTION_ABASTECIMIENTO_DIAS = original


@contextmanager
def _como_el_dax():
    """El motor con las reglas que tenia el DAX cuando se congelaron los goldens.

    Hoy son tres: el dia de gestion de Abastecimiento, la regla de centralizacion
    en el CD y el lead time de fallback (era 8 dias, ahora 3). Se apagan aca para que los goldens sigan validando TODO lo demas;
    cada regla nueva tiene su propio test. Cada divergencia que se le agregue al
    motor se apaga en este mismo lugar.
    """
    from src.motor import parametros as P

    clases, solo_d = P.CENTRALIZACION_CLASES_LOCALES, P.CENTRALIZACION_AGREGADA_SOLO_D
    fallback = P.LT_FALLBACK_DIAS
    P.CENTRALIZACION_CLASES_LOCALES = ("C", "D")
    P.CENTRALIZACION_AGREGADA_SOLO_D = False
    P.LT_FALLBACK_DIAS = 8
    try:
        with _gestion(0):
            yield
    finally:
        P.CENTRALIZACION_CLASES_LOCALES = clases
        P.CENTRALIZACION_AGREGADA_SOLO_D = solo_d
        P.LT_FALLBACK_DIAS = fallback


def _calcular_etapas(fuentes):
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


@pytest.fixture(scope="module")
def etapas(fuentes):
    """Las etapas calculadas con las reglas del DAX (ver `_como_el_dax`).

    Los goldens son la foto del DAX de julio. Cada divergencia deliberada que se le
    agrega al motor se apaga aca, para que sigan validando TODO lo demas: son la
    unica red que avisa cuando un cambio rompe algo que no se queria tocar.

    A diferencia del ciclo de orden 3->5 —que solo movio las filas abastecidas por
    CD y por eso se pudo excluir ese subconjunto con `_solo_directo`—, el dia de
    gestion afecta a filas de todo el universo, asi que no quedaria nada contra que
    comparar. Se valida aparte, en `test_gestion_abastecimiento_suma_un_dia`.
    """
    with _como_el_dax():
        return _calcular_etapas(fuentes)


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


def _solo_directo(golden: pl.DataFrame, etapas) -> pl.DataFrame:
    """El golden sin las filas abastecidas por CD.

    El ciclo de orden vía CD cambió de 3 a 5 días por decisión de Abastecimiento
    (Marilyn Ramos, 24-jul-2026: "en ambos debe ser 5"). Eso mueve el stock de
    seguridad —y con él, sugerido y traslados— de las filas abastecidas por CD
    respecto del golden extraído del DAX viejo (que usaba 3). Esas filas ya NO
    deben calzar con ese golden; la regla nueva la fija `test_ciclo_orden_cd_es_5`.
    Las de compra directa (ciclo 5 antes y ahora) se siguen validando contra el DAX.
    """
    cd = (
        etapas["lt"].filter(pl.col("abastece_cd") == "Si")
        .select(
            pl.col("producto_master").alias("Producto"),
            pl.col("sucursal_final").alias("SucursalID"),
        )
        .unique()
    )
    return golden.join(cd, on=CLAVE, how="anti")


def test_gestion_abastecimiento_suma_un_dia(fuentes):
    """Regla nueva (Abastecimiento, 13-ago): el LT del proveedor lleva +1 día.

    El lead time se mide desde la fecha de la OC hasta la recepción, así que el
    tramo previo —revisar el sugerido, decidir, emitir la orden— no estaba contado
    en ninguna parte: el modelo asumía que la OC sale el mismo día que aparece la
    necesidad.

    Se verifica comparando el motor consigo mismo con y sin el día, que es la única
    forma de aislar el efecto: los goldens no lo tienen.
    """
    with _gestion(0):
        sin = _calcular_etapas(fuentes)["lt"]
    with _gestion(1):
        con = _calcular_etapas(fuentes)["lt"]

    j = sin.select(["producto_master", "sucursal_final", "lead_time_dias", "lt_efectivo",
                    "lt_cd_a_sucursal_dias", "abastece_cd"]).join(
        con.select(["producto_master", "sucursal_final", "lead_time_dias", "lt_efectivo",
                    "lt_cd_a_sucursal_dias"]),
        on=["producto_master", "sucursal_final"], how="inner", suffix="_con",
    )
    assert j.height > 0

    # El LT del proveedor sube exactamente 1 día en TODAS las filas.
    d = j.select((pl.col("lead_time_dias_con") - pl.col("lead_time_dias")).alias("d"))
    distintos = d.filter((pl.col("d") - 1.0).abs() > 1e-9)
    assert distintos.height == 0, f"{distintos.height} filas no subieron exactamente 1 día"

    # El traslado CD -> sucursal NO lo lleva: ahí no hay compra que gestionar.
    cd = j.select(
        (pl.col("lt_cd_a_sucursal_dias_con") - pl.col("lt_cd_a_sucursal_dias")).alias("d")
    ).filter(pl.col("d").abs() > 1e-9)
    assert cd.height == 0, f"{cd.height} filas cambiaron el LT del CD, que no debe moverse"

    # Y por lo mismo, el LT EFECTIVO de una fila abastecida por CD tampoco cambia.
    por_cd = j.filter(pl.col("abastece_cd") == "Si").select(
        (pl.col("lt_efectivo_con") - pl.col("lt_efectivo")).alias("d")
    ).filter(pl.col("d").abs() > 1e-9)
    assert por_cd.height == 0, (
        f"{por_cd.height} filas de CD movieron su LT efectivo: la gestión se está "
        "sumando donde no corresponde"
    )

    # Las de compra directa sí: son las que gatillan la orden al proveedor.
    directas = j.filter(pl.col("abastece_cd") != "Si")
    if directas.height:
        d_dir = directas.select(
            (pl.col("lt_efectivo_con") - pl.col("lt_efectivo")).alias("d")
        ).filter((pl.col("d") - 1.0).abs() > 1e-9)
        assert d_dir.height == 0, f"{d_dir.height} filas de compra directa no subieron 1 día"


def test_rancagua_2_sigue_fusionada_en_rancagua(fuentes):
    """Rancagua 2 ES una sucursal distinta, pero el motor la fusiona a proposito.

    Se intento separarla el 18-ago-2026 y hace COMPRAR DE MAS. El sugerido solo
    crea filas para productos con demanda en la sucursal: Rancagua 2 vende 1.223
    lineas contra 20.330 de Rancagua, asi que de los 456 productos con stock en su
    bodega solo 7 quedaban con fila. Las otras 5.104 unidades desaparecian del
    modelo -stock real que nadie descuenta- y el sugerido total subia $4,3 millones.

    Separarla exige que el motor evalue una sucursal por su STOCK y no solo por su
    venta. Este test existe para que el dia que alguien lo intente de nuevo, falle
    aca y lea el motivo antes de publicar.
    """
    etapas = _calcular_etapas(fuentes)
    sucs = set(etapas["abc"]["sucursal_final"].unique().to_list())
    assert "RANCAGUA 2" not in sucs, (
        "Rancagua 2 aparece como sucursal propia. Si es intencional, hay que "
        "resolver antes el stock huerfano: ver parametros.FUSIONES_SUCURSAL"
    )
    from src.motor import parametros as P
    assert P.FUSIONES_SUCURSAL.get("RANCAGUA 2") == "RANCAGUA"


def test_ciclo_orden_cd_es_5(etapas):
    """Regla nueva (Marilyn, 24-jul): el ciclo de orden vía CD es 5, no 3.

    Se verifica desde la FÓRMULA, no contra el golden: para una fila abastecida por
    CD con desviación > 0, el stock de seguridad debe ser
    ROUND(Z · σ · √((LT_efectivo + 5) / 22)) — y NO el que daría con 3.
    """
    z_por_clase = {"A": 1.645, "B": 1.282, "C": 0.842, "D": 0.0}
    z_imp_cd = {"A": 1.282, "B": 1.036}
    ss = etapas["ss"].join(
        etapas["dem"].select(["producto_master", "sucursal_final", "desv_std_mensual"]),
        on=["producto_master", "sucursal_final"], how="left",
    )
    cd = ss.filter(
        (pl.col("abastece_cd") == "Si")
        & (pl.col("desv_std_mensual") > 0)
        & pl.col("stock_seguridad").is_not_null()
    )
    assert cd.height > 0, "el fixture no tiene filas abastecidas por CD para probar"

    # Se recorren TODAS (205 en el fixture), no una muestra. Antes eran `head(25)`
    # sobre el resultado de un join, cuyo orden polars no garantiza: de las 205
    # candidatas solo 16 distinguen CO=5 de CO=3, asi que segun que 25 salieran
    # primero el test pasaba o fallaba con el MISMO codigo. Era intermitente y no
    # avisaba de nada real. Recorrerlas todas es barato y ademas prueba mas.
    revisadas = 0
    for row in cd.iter_rows(named=True):
        es_cd_suc = row["sucursal_final"] == "CD REPUESTOS"
        clase = row["clasificacion_abc_agregada"] if es_cd_suc else row["clasificacion_abc"]
        if row["es_importado"] and clase in z_imp_cd:
            z = z_imp_cd[clase]
        else:
            z = z_por_clase.get(clase, 0.0)
        sigma = row["desv_std_mensual"]
        lt_ef = row["lt_efectivo"]
        esperado_5 = math.floor(z * sigma * math.sqrt((lt_ef + 5) / 22) + 0.5)
        esperado_3 = math.floor(z * sigma * math.sqrt((lt_ef + 3) / 22) + 0.5)
        assert row["stock_seguridad"] == esperado_5, (
            f"{row['producto_master']}/{row['sucursal_final']}: "
            f"SS={row['stock_seguridad']} pero con CO=5 deberia ser {esperado_5}"
        )
        # Cuando 5 y 3 dan distinto, confirmamos que se aplico el 5 (no el 3 viejo).
        if esperado_5 != esperado_3:
            assert row["stock_seguridad"] != esperado_3
            revisadas += 1
    assert revisadas > 0, "ninguna fila distingue CO=5 de CO=3; el test no prueba nada"


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
    # Safety stock: solo compra directa contra el DAX. Las de CD cambiaron por el
    # ciclo de orden 3->5 (ver _solo_directo) y las cubre test_ciclo_orden_cd_es_5.
    d_ss = _mismatch(etapas["ss"], _solo_directo(g, etapas), [("stock_seguridad", "StockSeguridad")], tol=0.5)
    assert d_ss.height == 0, f"safety stock difiere en {d_ss.height}: {d_ss.select(CLAVE).head(5).to_dicts()}"


def test_sugerido_paridad(etapas):
    # Solo compra directa contra el DAX: el sugerido de las filas de CD se movio con
    # el ciclo de orden 3->5 (ver _solo_directo / test_ciclo_orden_cd_es_5).
    g = _solo_directo(_golden("golden_sugerido.csv"), etapas)
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
    # Solo compra directa contra el DAX: traslado y compra neta de las filas de CD
    # se movieron con el ciclo de orden 3->5 (ver _solo_directo).
    g = _solo_directo(_golden("golden_traslados.csv"), etapas)
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
    # Solo compra directa: el lateral depende del sugerido, que en las filas de CD
    # cambio con el ciclo de orden 3->5 (ver _solo_directo).
    g = _solo_directo(_golden("golden_traslados.csv"), etapas)
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
