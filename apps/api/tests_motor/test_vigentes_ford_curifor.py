"""Combinar las dos listas de reemplazos de FORD.

Las dos las produce el mismo extractor de WINGS, con el mismo formato, pero sobre
listas de entrada distintas:

- **la lista de FORD** (39.622 codigos): cubre el catalogo del proveedor. De los
  9.805 codigos FORD que Curifor stockea, solo trae 4.488.
- **la lista de Curifor** (`Vigentes ford*.xlsx`): corre sobre stock + pautas, asi
  que trae los otros. Medido el 22-08-2026: 899 con vigente y cadena, 1.918 con la
  direccion inversa, +861 avisos publicables.

Se COMBINAN, no se reemplazan: hacen falta las dos. La de FORD alimenta ademas la
equivalencia de SKU del portal, que tiene que ser completa; la de Curifor trae los
reemplazos de lo que efectivamente se vende.
"""
from datetime import date

import polars as pl

from src.motor.dimensiones import ampliar_mapeo_con_ford
from src.motor.lectores_excel import (
    ESQUEMA_REEMPLAZOS_FORD,
    combinar_reemplazos_ford,
)


def _reem(**kw):
    base = {
        "clave_precio": None, "sku_ford": None, "clave_vigente": None,
        "sku_vigente": None, "cadena": None, "reemplaza_a": [],
        "estado_reemplazo": None, "sucesor_confirmado": False, "aviso": None,
        "extraido_en": None,
    }
    base.update(kw)
    return base


def _frame(filas):
    return pl.DataFrame(filas, schema=dict(ESQUEMA_REEMPLAZOS_FORD))


VENTAS_VACIAS = pl.DataFrame(
    {"Producto": [], "Fecha": [], "Cantidad": []},
    schema={"Producto": pl.Utf8, "Fecha": pl.Date, "Cantidad": pl.Float64},
)
FIN = date(2026, 8, 1)


# --- La combinacion --------------------------------------------------------------

def test_la_lista_de_curifor_manda_en_el_vigente():
    """Es la que se consulto hoy; la de FORD puede tener quince dias."""
    ford = _frame([_reem(clave_precio="MB3Z19N619C", clave_vigente="OTRO",
                         sucesor_confirmado=False)])
    curifor = _frame([_reem(clave_precio="MB3Z19N619C", clave_vigente="MB3Z19N619A",
                            sku_vigente="MB3Z/19N619/A/", sucesor_confirmado=True,
                            cadena="MB3Z/19N619/C/ > MB3Z/19N619/A/")])

    f = combinar_reemplazos_ford(ford, curifor).to_dicts()[0]

    assert f["clave_vigente"] == "MB3Z19N619A"
    assert f["cadena"] == "MB3Z/19N619/C/ > MB3Z/19N619/A/"
    assert f["sucesor_confirmado"] is True


def test_conserva_el_reemplaza_a_de_la_lista_de_ford():
    """La regresion que este test existe para atajar.

    Se midio el 22-08-2026 con las dos listas reales: conservar el valor de la
    lista de FORD no pierde ni un par, y salva 40 que solo tiene ella. De los 23
    codigos donde eso pasa, 22 son codigos que el portal no encontro en la corrida
    de Curifor: el valor viejo es el unico dato que hay.
    """
    ford = _frame([_reem(clave_precio="BK3Z9601B",
                         reemplaza_a=["1945831", "1881895"])])
    curifor = _frame([_reem(clave_precio="BK3Z9601B", sku_ford="BK3Z/9601/B/")])

    out = combinar_reemplazos_ford(ford, curifor)

    assert out.height == 1
    assert out.to_dicts()[0]["reemplaza_a"] == ["1945831", "1881895"]


def test_curifor_borra_un_sucesor_que_la_lista_de_ford_declaraba_de_mas():
    """Caso real: la lista de FORD daba `7C3Z9601A -> 7C3Z9601C` con estado "Sin
    candidato vigente"; al consultarlo, el codigo estaba vigente. Gana lo que se
    miro hoy, pero la direccion inversa se conserva igual."""
    ford = _frame([_reem(clave_precio="7C3Z9601A", clave_vigente="7C3Z9601C",
                         estado_reemplazo="Sin candidato vigente",
                         reemplaza_a=["AL3Z9601A"])])
    curifor = _frame([_reem(clave_precio="7C3Z9601A", sku_ford="7C3Z/9601/A/")])

    f = combinar_reemplazos_ford(ford, curifor).to_dicts()[0]

    assert f["clave_vigente"] is None
    assert f["reemplaza_a"] == ["AL3Z9601A"]


def test_las_filas_que_curifor_no_toca_quedan_intactas():
    ford = _frame([
        _reem(clave_precio="AAA", clave_vigente="BBB", sucesor_confirmado=True),
        _reem(clave_precio="CCC", reemplaza_a=["DDD"]),
    ])
    curifor = _frame([_reem(clave_precio="CCC", sku_ford="CCC")])

    out = combinar_reemplazos_ford(ford, curifor)

    assert out.height == 2
    aaa = out.filter(pl.col("clave_precio") == "AAA").to_dicts()[0]
    assert aaa["clave_vigente"] == "BBB" and aaa["sucesor_confirmado"] is True


def test_un_codigo_que_solo_conoce_curifor_se_agrega():
    """Es el aporte principal: 5.317 de los 9.805 no estan en la lista de FORD."""
    ford = _frame([_reem(clave_precio="AAA")])
    curifor = _frame([_reem(clave_precio="BR3Z8620S", clave_vigente="RB5Z8620D",
                            sucesor_confirmado=True)])

    out = combinar_reemplazos_ford(ford, curifor)

    assert sorted(out["clave_precio"].to_list()) == ["AAA", "BR3Z8620S"]


def test_sin_la_lista_de_curifor_todo_queda_igual():
    """Es el camino de todos los dias si la corrida semanal no alcanzo a correr."""
    ford = _frame([_reem(clave_precio="AAA", clave_vigente="BBB")])

    assert combinar_reemplazos_ford(ford, _frame([])).equals(ford)


def test_sin_la_lista_de_ford_sirve_la_de_curifor_sola():
    curifor = _frame([_reem(clave_precio="AAA", clave_vigente="BBB")])

    out = combinar_reemplazos_ford(_frame([]), curifor)

    assert out.height == 1
    assert list(out.schema) == list(ESQUEMA_REEMPLAZOS_FORD)


def test_cada_fila_conserva_la_fecha_de_SU_archivo():
    """Es lo que hace que la fecha sirva de algo.

    Los dos archivos se extraen por su lado: al 22-08-2026 la lista de FORD era
    del 5 al 7 de agosto y la de Curifor de ese mismo dia. Si al combinar la
    fecha se perdiera o se unificara, la plataforma mostraria "consultado hoy"
    sobre datos de hace tres semanas — que es justo lo que la columna viene a
    evitar.
    """
    ford = _frame([
        _reem(clave_precio="SOLO_FORD", clave_vigente="X",
              extraido_en="2026-08-05 23:20:26"),
        _reem(clave_precio="EN_LAS_DOS", clave_vigente="VIEJO",
              extraido_en="2026-08-05 23:20:26"),
    ])
    curifor = _frame([
        _reem(clave_precio="EN_LAS_DOS", clave_vigente="NUEVO",
              extraido_en="2026-08-22 18:24:47"),
        _reem(clave_precio="SOLO_CURIFOR", clave_vigente="Y",
              extraido_en="2026-08-22 18:24:47"),
    ])

    out = combinar_reemplazos_ford(ford, curifor)
    fechas = dict(out.select(["clave_precio", "extraido_en"]).iter_rows())

    assert fechas["SOLO_FORD"].startswith("2026-08-05")
    assert fechas["SOLO_CURIFOR"].startswith("2026-08-22")
    # La que esta en las dos se queda con la de Curifor, que es la que gana el
    # vigente: la fecha tiene que contar la misma historia que el dato.
    assert fechas["EN_LAS_DOS"].startswith("2026-08-22")


def test_la_combinacion_conserva_el_esquema():
    """Lo que hace posible mezclarlas. Si se desalinea, la mezcla falla en
    silencio: el motor pierde reemplazos y ningun test revienta."""
    ford = _frame([_reem(clave_precio="AAA", reemplaza_a=["ZZZ"])])
    curifor = _frame([_reem(clave_precio="BBB", clave_vigente="CCC")])

    out = combinar_reemplazos_ford(ford, curifor)

    assert list(out.schema) == list(ESQUEMA_REEMPLAZOS_FORD)
    assert out.schema == ford.schema


# --- De punta a punta: que el par termine agrupado --------------------------------

def _mapeo(pares=()):
    return pl.DataFrame(
        [{"Producto": p, "Producto_Master": m} for p, m in pares],
        schema={"Producto": pl.Utf8, "Producto_Master": pl.Utf8},
    )


def test_el_par_queda_bajo_el_codigo_vigente():
    """El caso que reporto Abastecimiento: la plataforma pedia `25 MB3Z19N619C`,
    dado de baja, teniendo `19 MB3Z19N619A` en el catalogo."""
    reem = _frame([_reem(clave_precio="MB3Z19N619C", clave_vigente="MB3Z19N619A",
                         sku_vigente="MB3Z/19N619/A/", sucesor_confirmado=True)])
    conocidos = ["25 MB3Z19N619C", "19 MB3Z19N619A"]

    out = ampliar_mapeo_con_ford(_mapeo(), reem, conocidos, VENTAS_VACIAS, FIN)

    masters = dict(out.select(["Producto", "Producto_Master"]).iter_rows())
    assert masters["25 MB3Z19N619C"] == "19 MB3Z19N619A"
    assert masters["19 MB3Z19N619A"] == "19 MB3Z19N619A"


def test_si_el_vigente_no_esta_en_curifor_no_se_agrupa_nada():
    """`25 MB3Z8620E` -> `MB3Z/8620/F/`, que no esta en el maestro (medido
    22-08-2026). El ERP no puede comprar un codigo que no conoce, asi que el viejo
    se queda como esta y el aviso lo da la plataforma con `reemplazado_por_ford`.
    No hay que programar el fallback: sale solo de que `por_clave` no lo encuentra."""
    reem = _frame([_reem(clave_precio="MB3Z8620E", clave_vigente="MB3Z8620F",
                         sku_vigente="MB3Z/8620/F/", sucesor_confirmado=True)])

    out = ampliar_mapeo_con_ford(_mapeo(), reem, ["25 MB3Z8620E"], VENTAS_VACIAS, FIN)

    assert out.is_empty()


def test_el_resultado_no_depende_del_orden_de_los_productos():
    """El motor tiene que dar lo mismo dos veces sobre la misma base.

    2.399 claves del maestro tienen mas de un codigo de Curifor: "25 CN1Z8620E" y
    "19 CN1Z8620E" son el mismo repuesto con distinto rubro y normalizan igual.
    `por_clave` se queda con uno, y hasta el 22-08-2026 ese uno dependia del orden
    en que llegaran los productos —que sale de un `.unique()` de polars y no es
    estable—. Dos corridas identicas daban 15 y 19 filas distintas, y un producto
    pedia $61.286 en una y $137.152 en la otra.
    """
    reem = _frame([_reem(clave_precio="CN1Z8620D", clave_vigente="CN1Z8620E",
                         sucesor_confirmado=True)])
    duplicados = ["25 CN1Z8620E", "19 CN1Z8620E", "15 CN1Z8620E", "25 CN1Z8620D"]

    resultados = [
        dict(
            ampliar_mapeo_con_ford(_mapeo(), reem, orden, VENTAS_VACIAS, FIN)
            .select(["Producto", "Producto_Master"]).iter_rows()
        )
        for orden in (duplicados, list(reversed(duplicados)), sorted(duplicados))
    ]

    assert resultados[0] == resultados[1] == resultados[2]
    assert resultados[0]["25 CN1Z8620D"] == "15 CN1Z8620E"


def test_el_mix_sigue_mandando_sobre_ford():
    """Un producto ya agrupado por el mix no lo toca FORD. Se midio el 07-08-2026
    que invertirlo rompia 41 grupos."""
    reem = _frame([_reem(clave_precio="MB3Z19N619C", clave_vigente="MB3Z19N619A",
                         sucesor_confirmado=True)])
    mix = _mapeo([("25 MB3Z19N619C", "OTRO MASTER"), ("OTRO MASTER", "OTRO MASTER")])

    out = ampliar_mapeo_con_ford(
        mix, reem, ["25 MB3Z19N619C", "19 MB3Z19N619A", "OTRO MASTER"],
        VENTAS_VACIAS, FIN,
    )

    masters = dict(out.select(["Producto", "Producto_Master"]).iter_rows())
    assert masters["25 MB3Z19N619C"] == "OTRO MASTER"
