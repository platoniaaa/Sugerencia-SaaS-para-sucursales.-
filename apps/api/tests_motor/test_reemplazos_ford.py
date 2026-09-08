"""Cadena de reemplazo de la lista FORD (extraccion WINGS, desde ago-2026).

FORD publica que codigo descontinuado fue sustituido por cual vigente, en las dos
direcciones (`Reemplazado_Por` y `Reemplaza_A`). Con eso el motor puede agrupar
stock y demanda del viejo con el nuevo, que hasta ahora solo salia del "mix andres".

El mix MANDA: se midio contra los datos reales el 07-08-2026 que mezclar los pares
de FORD dentro del mix hacia que 41 productos hoy agrupados DEJARAN de estarlo y 4
cambiaran de master. Respetandolo: 896 productos entran a un grupo, 0 se pierden.
"""
from datetime import date

import polars as pl
from openpyxl import Workbook

from src.motor.dimensiones import ampliar_mapeo_con_ford
from src.motor.lectores_excel import leer_reemplazos_ford

CABECERAS = [
    "PartNumber", "Precio_Publico", "Reemplazado_Por", "Cadena_Reemplazo",
    "Reemplaza_A", "Estado_Reemplazo", "Reemplazo_Aviso",
]


def _xlsx(ruta, filas, cabeceras=CABECERAS):
    wb = Workbook()
    ws = wb.active
    ws.title = "Precios"
    ws.append(cabeceras)
    for f in filas:
        ws.append(f)
    wb.save(ruta)


def _reem(**kw):
    """Fila del frame que devuelve el lector, con lo minimo para agrupar."""
    base = {
        "clave_precio": None, "sku_ford": None, "clave_vigente": None,
        "sku_vigente": None, "cadena": None, "reemplaza_a": [],
        "estado_reemplazo": None, "sucesor_confirmado": False, "aviso": None,
    }
    base.update(kw)
    return base


def _frame(filas):
    return pl.DataFrame(filas, schema={
        "clave_precio": pl.Utf8, "sku_ford": pl.Utf8, "clave_vigente": pl.Utf8,
        "sku_vigente": pl.Utf8, "cadena": pl.Utf8, "reemplaza_a": pl.List(pl.Utf8),
        "estado_reemplazo": pl.Utf8, "sucesor_confirmado": pl.Boolean,
        "aviso": pl.Utf8,
    })


VENTAS_VACIAS = pl.DataFrame(
    {"Producto": [], "Fecha": [], "Cantidad": []},
    schema={"Producto": pl.Utf8, "Fecha": pl.Date, "Cantidad": pl.Float64},
)
FIN = date(2026, 8, 1)


# --- El lector -------------------------------------------------------------------

def test_lee_las_dos_direcciones_y_normaliza_las_claves(tmp_path):
    ruta = tmp_path / "ford.xlsx"
    _xlsx(ruta, [
        ["KK3Z/3504/BR/", 100, "KK3Z/3504/U/", "KK3Z/3504/BR/ > KK3Z/3504/U/",
         None, "Encontrado", None],
        ["AB3Z/1A380/B/", 200, None, None, "AB3Z/1A380/A/; AB3Z/1A380/AA/", None, None],
    ])
    df = leer_reemplazos_ford(ruta)
    a, b = df.sort("clave_precio").to_dicts()

    assert a["clave_precio"] == "AB3Z1A380B"
    assert a["reemplaza_a"] == ["AB3Z1A380A", "AB3Z1A380AA"]
    assert a["clave_vigente"] is None

    assert b["clave_precio"] == "KK3Z3504BR"
    assert b["clave_vigente"] == "KK3Z3504U"      # las barras se van
    assert b["cadena"] == "KK3Z/3504/BR/ > KK3Z/3504/U/"


def test_sin_candidato_vigente_deja_el_sucesor_sin_confirmar(tmp_path):
    """FORD sabe que fue reemplazada pero no resolvio el sucesor (999 de 1.070).

    No es solo que falte el precio: tampoco esta verificado si FORD realmente no
    tiene sucesor o si el codigo consultado se armo mal. Por eso el flag gobierna
    tanto el precio como la agrupacion."""
    ruta = tmp_path / "ford.xlsx"
    _xlsx(ruta, [
        ["A/1/", 100, "B/1/", None, None, "Encontrado", None],
        ["C/1/", 100, "D/1/", None, None, "Sin candidato vigente", "revisar a mano"],
    ])
    df = leer_reemplazos_ford(ruta).sort("clave_precio")
    assert df["sucesor_confirmado"].to_list() == [True, False]
    assert df.to_dicts()[1]["aviso"] == "revisar a mano"


def test_una_lista_vieja_sin_las_columnas_no_rompe(tmp_path):
    """Antes de ago-2026 la lista no traia reemplazos: el motor no puede caerse."""
    ruta = tmp_path / "ford.xlsx"
    _xlsx(ruta, [["A/1/", 100]], cabeceras=["PartNumber", "Precio_Publico"])
    df = leer_reemplazos_ford(ruta)
    assert df.is_empty()
    assert "clave_vigente" in df.columns


# --- La agrupacion ---------------------------------------------------------------

def _mapeo(pares):
    return pl.DataFrame(
        {"Producto": [p for p, _ in pares], "Producto_Master": [m for _, m in pares]},
        schema={"Producto": pl.Utf8, "Producto_Master": pl.Utf8},
    )


def test_agrupa_el_viejo_con_el_vigente():
    reem = _frame([_reem(clave_precio="AB3Z1A380B", reemplaza_a=["AB3Z1A380A"])])
    out = ampliar_mapeo_con_ford(
        _mapeo([]), reem, ["25 AB3Z1A380B", "25 AB3Z1A380A"], VENTAS_VACIAS, FIN
    )
    assert dict(out.rows()) == {
        "25 AB3Z1A380B": "25 AB3Z1A380B",
        "25 AB3Z1A380A": "25 AB3Z1A380B",
    }


def test_ford_le_gana_al_mix_cuando_los_dos_reclaman_el_codigo():
    """FORD manda: el mix agrupa equivalentes, pero no sabe cual sigue vivo.

    Esto estuvo al reves hasta el 24-08-2026, y por una razon medida: con la lista
    ESTATICA de FORD, invertirlo dejaba 41 productos sin grupo. Lo que cambio no es
    el criterio sino la fuente -ahora se consulta el portal por los codigos que
    Curifor tiene- y remedido con esos datos son 6 sueltos contra 20 que entran.

    Con el mix mandando, el grupo terminaba colgando de un codigo descontinuado y
    la orden de compra salia con ese numero.
    """
    mapeo = _mapeo([("25 AAA", "25 AAA"), ("25 BBB", "25 AAA")])
    # FORD dice que 25 CCC reemplazo a 25 BBB, y esa respuesta gana.
    reem = _frame([_reem(clave_precio="CCC", reemplaza_a=["BBB"])])
    out = ampliar_mapeo_con_ford(
        mapeo, reem, ["25 AAA", "25 BBB", "25 CCC"], VENTAS_VACIAS, FIN
    )
    m = dict(out.rows())
    assert m["25 BBB"] == "25 CCC"
    assert m["25 CCC"] == "25 CCC"
    # Y lo que FORD no nombra sigue como lo dejo el mix.
    assert m["25 AAA"] == "25 AAA"


def test_un_producto_reclamado_por_dos_grupos_queda_fuera_de_los_dos():
    reem = _frame([
        _reem(clave_precio="AAA", reemplaza_a=["ZZZ"]),
        _reem(clave_precio="BBB", reemplaza_a=["ZZZ"]),
    ])
    out = ampliar_mapeo_con_ford(
        _mapeo([]), reem, ["25 AAA", "25 BBB", "25 ZZZ"], VENTAS_VACIAS, FIN
    )
    assert "25 ZZZ" not in dict(out.rows())


def test_en_una_cadena_encadenada_solo_sobrevive_el_primer_grupo():
    """A agrupa a B y B agrupa a C: el grupo de B se cae y C queda suelto.

    Es la misma regla del DAX que ya aplica `calcular_mapeo_master`: un master que
    TAMBIEN figura como reemplazo de otro se descarta (`sin_conflicto`), porque el
    grupo seria ambiguo. Se replica aca a proposito para que las dos fuentes de
    reemplazos se comporten igual y no haya que explicar dos reglas distintas.
    """
    reem = _frame([
        _reem(clave_precio="AAA", reemplaza_a=["BBB"]),
        _reem(clave_precio="BBB", reemplaza_a=["CCC"]),
    ])
    out = ampliar_mapeo_con_ford(
        _mapeo([]), reem, ["25 AAA", "25 BBB", "25 CCC"], VENTAS_VACIAS, FIN
    )
    assert dict(out.rows()) == {"25 AAA": "25 AAA", "25 BBB": "25 AAA"}
    assert "25 CCC" not in dict(out.rows())


def test_el_master_del_grupo_es_el_vigente_aunque_venda_menos():
    """La orden de compra tiene que salir con el codigo que FORD sigue fabricando.

    Antes el master se elegia por venta de 6 meses. El codigo viejo casi siempre
    vende mas -lleva anos en catalogo-, asi que el grupo quedaba representado por
    una pieza descontinuada y se compraba esa. Paso en produccion con
    25 MB3Z19N619C (Chillan, 5 unidades, $111.137) teniendo vigente el
    19 MB3Z19N619A.

    Elegir por ventas sigue siendo correcto en el mix, donde los codigos de un
    grupo son equivalentes y ninguno esta muerto. Aca no: FORD ya dijo cual sigue
    vivo.
    """
    reem = _frame([_reem(clave_precio="NUEVO1", reemplaza_a=["VIEJO1"])])
    ventas = pl.DataFrame({
        "Producto": ["25 NUEVO1", "25 VIEJO1"],
        "Fecha": [date(2026, 5, 1), date(2026, 5, 1)],
        "Cantidad": [3.0, 40.0],  # el viejo vende 13 veces mas
    })
    out = ampliar_mapeo_con_ford(
        _mapeo([]), reem, ["25 NUEVO1", "25 VIEJO1"], ventas, FIN
    )
    assert set(dict(out.rows()).values()) == {"25 NUEVO1"}


def test_el_viejo_sigue_en_el_grupo_para_que_su_stock_cuente():
    """Cambia QUE se compra, no que se agrupa.

    El stock y la demanda del codigo viejo se siguen sumando al grupo: eso es lo
    que hace que primero se consuma lo que hay en bodega y recien al cruzar el
    punto de pedido se compre, ya con el codigo vigente. Si el viejo saliera del
    grupo, su stock dejaria de contar y se compraria de mas.
    """
    reem = _frame([_reem(clave_precio="NUEVO1", reemplaza_a=["VIEJO1", "VIEJO2"])])
    out = ampliar_mapeo_con_ford(
        _mapeo([]), reem, ["25 NUEVO1", "25 VIEJO1", "25 VIEJO2"], VENTAS_VACIAS, FIN
    )
    d = dict(out.rows())
    assert d == {"25 NUEVO1": "25 NUEVO1", "25 VIEJO1": "25 NUEVO1", "25 VIEJO2": "25 NUEVO1"}


def test_el_sucesor_confirmado_tambien_manda_como_master():
    """La otra direccion de la lista: el codigo consultado esta descontinuado y
    FORD nombra su sucesor. El master tiene que ser el sucesor."""
    reem = _frame([_reem(clave_precio="VIEJO1", clave_vigente="NUEVO1",
                         sucesor_confirmado=True)])
    ventas = pl.DataFrame({
        "Producto": ["25 VIEJO1"],
        "Fecha": [date(2026, 5, 1)],
        "Cantidad": [99.0],
    })
    out = ampliar_mapeo_con_ford(
        _mapeo([]), reem, ["25 NUEVO1", "25 VIEJO1"], ventas, FIN
    )
    assert set(dict(out.rows()).values()) == {"25 NUEVO1"}


def test_codigos_que_curifor_no_tiene_se_ignoran():
    reem = _frame([_reem(clave_precio="AAA", reemplaza_a=["NOEXISTE"])])
    out = ampliar_mapeo_con_ford(_mapeo([]), reem, ["25 AAA"], VENTAS_VACIAS, FIN)
    assert out.is_empty()


def test_sin_reemplazos_devuelve_el_mapeo_igual():
    mapeo = _mapeo([("25 AAA", "25 AAA")])
    out = ampliar_mapeo_con_ford(mapeo, _frame([]), ["25 AAA"], VENTAS_VACIAS, FIN)
    assert out.to_dicts() == mapeo.to_dicts()


def test_un_sucesor_sin_confirmar_no_agrupa():
    """El caso de los 999 'Sin candidato vigente' (22 pares al 07-08-2026).

    Se muestran como aviso pero NO tocan el calculo: si el codigo del sucesor
    estuviera mal, agrupar sumaria el stock de dos piezas distintas y el sugerido
    dejaria de pedir algo que si hace falta. Decision de Ignacio Calderon el
    07-08-2026, hasta que se confirme de donde salen esos codigos.
    """
    reem = _frame([_reem(clave_precio="VIEJO3", clave_vigente="NUEVO3",
                         sucesor_confirmado=False)])
    out = ampliar_mapeo_con_ford(
        _mapeo([]), reem, ["25 VIEJO3", "25 NUEVO3"], VENTAS_VACIAS, FIN
    )
    assert out.is_empty()


def test_reemplaza_a_agrupa_aunque_el_sucesor_no_este_confirmado():
    """`Reemplaza_A` sale de la cadena del portal, no de consultar al sucesor:
    `Estado_Reemplazo` no le aplica y no tiene por que quedar fuera."""
    reem = _frame([_reem(clave_precio="NUEVO4", reemplaza_a=["VIEJO4"],
                         sucesor_confirmado=False)])
    out = ampliar_mapeo_con_ford(
        _mapeo([]), reem, ["25 NUEVO4", "25 VIEJO4"], VENTAS_VACIAS, FIN
    )
    assert out.height == 2


def test_la_direccion_reemplazado_por_tambien_agrupa():
    """`Reemplazado_Por` dice 'a mi me reemplaza X': el grupo es el mismo."""
    reem = _frame([_reem(clave_precio="VIEJO2", clave_vigente="NUEVO2",
                         sucesor_confirmado=True)])
    out = ampliar_mapeo_con_ford(
        _mapeo([]), reem, ["25 VIEJO2", "25 NUEVO2"], VENTAS_VACIAS, FIN
    )
    assert len(dict(out.rows())) == 2
    assert len(set(dict(out.rows()).values())) == 1   # los dos en el mismo grupo


def test_agrupar_y_avisar_usan_universos_distintos_a_proposito():
    """Un codigo sin venta ni stock NO entra al grupo, pero SI se avisa.

    Son dos preguntas distintas. Para agrupar solo sirven los codigos que el motor
    evalua: fusionar el stock de algo que no tiene ni venta ni stock no cambia una
    sola fila del sugerido. Para avisar es al reves — un codigo dado de baja que
    ademas no rota es el perfil exacto del codigo muerto, y es cuando mas sirve
    que la pantalla lo diga.

    Se separo despues de publicar 625 avisos en vez de 3.195 por usar el universo
    chico en los dos lados (10-08-2026).
    """
    reem = _frame([_reem(clave_precio="VIVO", reemplaza_a=["MUERTO"])])
    # Solo VIVO tiene movimiento; MUERTO existe en el catalogo pero no rota.
    evaluables = ["25 VIVO"]
    out = ampliar_mapeo_con_ford(_mapeo([]), reem, evaluables, VENTAS_VACIAS, FIN)
    assert out.is_empty(), "MUERTO no se evalua: no hay nada que agrupar"

    # Con el catalogo completo si se puede resolver el par para el aviso.
    catalogo = ["25 VIVO", "25 MUERTO"]
    out2 = ampliar_mapeo_con_ford(_mapeo([]), reem, catalogo, VENTAS_VACIAS, FIN)
    assert out2.height == 2


def test_mas_de_tres_reemplazos_no_se_truncan():
    """El mix solo admite Reem1/2/3; la lista de FORD trae cadenas mas largas y
    cortarlas partiria un grupo real en dos."""
    reem = _frame([_reem(clave_precio="NUEVO3", reemplaza_a=["V1", "V2", "V3", "V4"])])
    productos = ["25 NUEVO3", "25 V1", "25 V2", "25 V3", "25 V4"]
    out = ampliar_mapeo_con_ford(_mapeo([]), reem, productos, VENTAS_VACIAS, FIN)
    assert out.height == 5
