"""En un codigo que FORD y el mix reclaman, gana FORD.

Hasta el 24-08-2026 era al reves. El mix de Andres agrupa equivalentes -piezas que
sirven para lo mismo- pero no sabe cual sigue en produccion; eso solo lo dice el
portal. Con el mix mandando, el grupo terminaba colgando del codigo que FORD ya
habia dado de baja y la orden de compra salia con ese numero.

Caso real del 24-08-2026: `19 CC1Z9365E` colgaba de `17 2499389`, que esta
descontinuado.

El cambio se midio antes de aplicarlo (ver el docstring de `ampliar_mapeo_con_ford`):
6 productos quedan sueltos y 20 entran a un grupo. Con la lista estatica anterior
los sueltos eran 41, y por eso la regla habia quedado al reves.
"""
from datetime import date

import polars as pl

from src.motor.dimensiones import ampliar_mapeo_con_ford
from src.motor.lectores_excel import ESQUEMA_REEMPLAZOS_FORD

FIN = date(2026, 8, 1)
SIN_VENTAS = pl.DataFrame(schema={"Producto": pl.Utf8, "Cantidad": pl.Float64,
                                  "Fecha": pl.Date})


def _mapeo(pares: list[tuple[str, str]]) -> pl.DataFrame:
    return pl.DataFrame(
        [{"Producto": p, "Producto_Master": m} for p, m in pares],
        schema={"Producto": pl.Utf8, "Producto_Master": pl.Utf8},
    )


def _reem(filas: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(filas, schema=ESQUEMA_REEMPLAZOS_FORD)


# FORD: `VIG` esta vigente y reemplazo a `OLD`.
FORD_DICE = _reem([{
    "clave_precio": "VIG", "sku_ford": "VIG/1/", "clave_vigente": None,
    "sku_vigente": None, "cadena": None, "reemplaza_a": ["OLD"],
    "estado_reemplazo": "Encontrado", "sucesor_confirmado": True,
    "aviso": None, "extraido_en": "2026-08-22 16:17:53",
}])
CONOCIDOS = ["25 VIG", "25 OLD"]
POR_CLAVE = {"VIG": "25 VIG", "OLD": "25 OLD"}


def _master_de(df: pl.DataFrame) -> dict[str, str]:
    return dict(df.select(["Producto", "Producto_Master"]).iter_rows())


def test_ford_le_gana_al_mix_cuando_los_dos_reclaman_el_codigo():
    """El mix ya tenia a OLD colgando de otra cosa; FORD dice que cuelga de VIG.

    Si esto se invierte, el grupo vuelve a quedar representado por un codigo que
    FORD no fabrica y la orden de compra sale con ese numero.
    """
    mix = _mapeo([("25 OLD", "25 OTRO"), ("25 OTRO", "25 OTRO")])

    out = ampliar_mapeo_con_ford(mix, FORD_DICE, CONOCIDOS, SIN_VENTAS, FIN)

    assert _master_de(out)["25 OLD"] == "25 VIG"


def test_el_mix_sigue_valiendo_donde_ford_no_dice_nada():
    """No es "FORD reemplaza al mix": es "FORD manda donde opina".

    El mix agrupa equivalentes que FORD nunca va a nombrar, y esos grupos tienen
    que sobrevivir intactos.
    """
    mix = _mapeo([("25 A", "25 B"), ("25 B", "25 B")])

    out = ampliar_mapeo_con_ford(mix, FORD_DICE, ["25 A", "25 B"], SIN_VENTAS, FIN)

    m = _master_de(out)
    assert m["25 A"] == "25 B"
    assert m["25 B"] == "25 B"


def test_el_master_del_grupo_de_ford_es_el_vigente():
    """Lo que hace que la orden de compra salga con el codigo correcto."""
    out = ampliar_mapeo_con_ford(_mapeo([]), FORD_DICE, CONOCIDOS, SIN_VENTAS, FIN)

    m = _master_de(out)
    assert m["25 OLD"] == "25 VIG"
    assert m["25 VIG"] == "25 VIG"


def test_un_sucesor_sin_confirmar_no_agrupa():
    """La salvaguarda que NO se toco: sin confirmar, se avisa pero no se junta.

    Agrupar con un codigo equivocado suma el stock de dos piezas distintas y deja
    de pedirse algo que si hace falta.
    """
    sin_confirmar = _reem([{
        "clave_precio": "OLD", "sku_ford": "OLD/1/", "clave_vigente": "VIG",
        "sku_vigente": "VIG/1/", "cadena": "OLD/1/ > VIG/1/", "reemplaza_a": [],
        "estado_reemplazo": "Sin candidato vigente", "sucesor_confirmado": False,
        "aviso": None, "extraido_en": "2026-08-22 16:17:53",
    }])

    out = ampliar_mapeo_con_ford(_mapeo([]), sin_confirmar, CONOCIDOS, SIN_VENTAS, FIN)

    assert "25 OLD" not in _master_de(out)
