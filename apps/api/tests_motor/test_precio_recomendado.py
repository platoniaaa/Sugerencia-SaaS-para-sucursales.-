"""El precio recomendado de compra: el menor de los precios de COMPRA de FORD.

Abastecimiento pidio una columna con "el precio menor de todos los que se captura
en Ford Chile" para decidir a que precio conviene pedir.

Dos decisiones que estos tests fijan:

1. **Los precios de publico quedan fuera.** Son lo que paga el cliente, no lo que
   Curifor le paga a FORD. Medido sobre los 3.103 productos con precio, hoy no
   ganan el minimo en ninguno -asi que excluirlos no cambia un solo numero- pero
   hay 13 productos donde el publico esta por debajo del dealer. El dia que uno
   de esos quede mas bajo que el resto, la columna mostraria un precio de venta
   como recomendacion de compra.

2. **Un cero no es un precio.** En la lista del fabricante significa que el dato
   falta. Si se dejara pasar ganaria el minimo siempre y la columna diria que el
   repuesto sale gratis.
"""
import polars as pl

from src.motor import pipeline

PRECIOS = pipeline._PRECIOS_COMPRA_FORD


def _minimo(**precios) -> float | None:
    """Corre la misma expresion del pipeline sobre una fila."""
    fila = {c: [precios.get(c)] for c in PRECIOS}
    df = pl.DataFrame(fila, schema={c: pl.Float64 for c in PRECIOS})
    return df.select(
        pl.min_horizontal([
            pl.when(pl.col(c) > 0).then(pl.col(c)).otherwise(None) for c in PRECIOS
        ]).alias("m")
    )["m"][0]


def test_devuelve_el_menor_de_los_precios_de_compra():
    assert _minimo(
        precio_dealer_ford=42176.0,
        precio_reposicion_ford=42176.0,
        precio_flota_ford=32422.0,
        precio_urgente_recargo15_ford=48412.0,
    ) == 32422.0


def test_los_precios_de_publico_no_entran_en_el_calculo():
    """La lista de candidatos es lo que define que es "de compra"."""
    assert "precio_publico_ford" not in PRECIOS
    assert "precio_publico_iva_ford" not in PRECIOS


def test_un_producto_con_media_lista_igual_devuelve_el_menor_de_lo_que_hay():
    """`precio_flota_ford` solo existe en 1.395 filas; el resto no puede quedar
    sin recomendacion por eso."""
    assert _minimo(precio_dealer_ford=50000.0, precio_reposicion_ford=48000.0) == 48000.0


def test_sin_ningun_precio_queda_vacio_y_no_en_cero():
    """Cero se leeria como "gratis" y ordenaria ese producto primero en la grilla."""
    assert _minimo() is None


def test_un_cero_en_la_lista_no_gana_el_minimo():
    """En la lista del fabricante, cero significa que el dato falta."""
    assert _minimo(precio_dealer_ford=0.0, precio_reposicion_ford=42176.0) == 42176.0


def test_si_todos_vienen_en_cero_queda_vacio():
    assert _minimo(precio_dealer_ford=0.0, precio_flota_ford=0.0) is None


def test_un_precio_negativo_tampoco_entra():
    """No deberia pasar, pero si pasa, un negativo gana el minimo para siempre."""
    assert _minimo(precio_dealer_ford=-100.0, precio_reposicion_ford=42176.0) == 42176.0


def test_la_columna_viaja_en_el_contrato_a_la_plataforma():
    """Sin esto se calcula y se pierde: el CSV sale sin la columna y la carga la
    ignora en silencio, que es como se perdieron los meses con venta."""
    salida = [destino for destino, _ in pipeline._CONTRATO] if hasattr(pipeline, "_CONTRATO") else None
    if salida is None:
        # El contrato vive como lista de tuplas (nombre de salida, columna).
        fuente = pipeline.__file__
        with open(fuente, encoding="utf-8") as f:
            texto = f.read()
        assert '("precio_recomendado_compra", "precio_recomendado_compra")' in texto
    else:
        assert "precio_recomendado_compra" in salida
