"""Se publica una fila por MIEMBRO del grupo, no una por codigo consultado a FORD.

El portal solo devuelve la ficha del codigo que se le pregunta. Los codigos que
esa pieza reemplazo vienen adentro, en `Reemplaza_A`, y no traen ficha propia:
al 23-08-2026 eran 3.713 codigos de los 4.364 nombrados.

Publicar solo el codigo consultado deja a esos 3.713 sin fila, y la plataforma
-que busca por codigo- no tiene donde mirar:

  - el autocomplete no avisa que el codigo esta dado de baja, y la sugerencia
    manual se guarda como si estuviera vivo;
  - la ficha del grupo los deja FUERA del total, porque `cuenta_en_el_total` mira
    el `agrupado` de la fila del codigo. Eran 602 fichas con un total que no
    cuadraba contra el sugerido -justo lo que `agrupado` existe para evitar.

Estos tests fijan que la direccion inversa se publique, y hasta donde llega: se
afirma el sucesor, NO se inventa la cadena.
"""
import polars as pl

from src.jobs.correr_motor_real import filas_de_reemplazos
from src.motor.lectores_excel import (
    ESQUEMA_REEMPLAZOS_FORD,
    combinar_reemplazos_ford,
)


def _reem(filas: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(filas, schema=ESQUEMA_REEMPLAZOS_FORD)


# `B` es el vigente y FORD dice que reemplazo a `A`. Solo `B` fue consultado, asi
# que solo `B` trae ficha: es el caso normal, no el raro.
SOLO_EL_VIGENTE = _reem([{
    "clave_precio": "B", "sku_ford": "B/100/", "clave_vigente": None,
    "sku_vigente": None, "cadena": None, "reemplaza_a": ["A"],
    "estado_reemplazo": "Encontrado", "sucesor_confirmado": True,
    "aviso": None, "extraido_en": "2026-08-22 16:17:53",
}])
POR_CLAVE = {"A": "25 A", "B": "25 B"}


def _por_producto(filas: list[dict]) -> dict[str, dict]:
    return {f["producto"]: f for f in filas}


def test_el_codigo_dado_de_baja_recibe_su_propia_fila():
    """Sin esto el comprador escribe el codigo viejo y nadie le dice nada."""
    filas = filas_de_reemplazos(SOLO_EL_VIGENTE, POR_CLAVE, {})

    a = _por_producto(filas).get("25 A")
    assert a is not None, "el codigo reemplazado quedo sin fila: nadie lo va a avisar"
    assert a["reemplazado_por"] == "25 B"
    assert a["reemplazado_por_ford"] == "B/100/"


def test_no_se_inventa_la_cadena_del_codigo_viejo():
    """El camino completo solo lo da el portal para el codigo que consulto.

    Armarla a mano seria mostrarle al comprador un dato de FORD que FORD nunca
    dijo. Preferimos la columna vacia.
    """
    a = _por_producto(filas_de_reemplazos(SOLO_EL_VIGENTE, POR_CLAVE, {}))["25 A"]

    assert a["cadena"] is None


def test_el_sucesor_de_la_direccion_inversa_va_confirmado():
    """FORD lo nombro: no es el caso "Sin candidato vigente"."""
    a = _por_producto(filas_de_reemplazos(SOLO_EL_VIGENTE, POR_CLAVE, {}))["25 A"]

    assert a["sucesor_confirmado"] is True


def test_agrupado_sale_del_mapeo_del_motor_y_no_de_lo_que_dice_ford():
    """Es la distincion completa de la tabla: FORD declara, el motor agrupa.

    Si `agrupado` viniera de FORD, el total de la ficha sumaria codigos que el
    sugerido cuenta por separado y el comprador confiaria en un numero que no
    cuadra con lo que va a comprar.
    """
    juntos = filas_de_reemplazos(SOLO_EL_VIGENTE, POR_CLAVE, {"25 A": "M", "25 B": "M"})
    aparte = filas_de_reemplazos(SOLO_EL_VIGENTE, POR_CLAVE, {"25 A": "M1", "25 B": "M2"})

    assert _por_producto(juntos)["25 A"]["agrupado"] is True
    assert _por_producto(aparte)["25 A"]["agrupado"] is False


def test_la_ficha_propia_le_gana_a_la_inversa():
    """Lo scrapeado manda: trae la cadena, el aviso y el estado reales."""
    con_ficha_propia = _reem([
        {"clave_precio": "B", "sku_ford": "B/100/", "clave_vigente": None,
         "sku_vigente": None, "cadena": None, "reemplaza_a": ["A"],
         "estado_reemplazo": "Encontrado", "sucesor_confirmado": True,
         "aviso": None, "extraido_en": "2026-08-22 16:17:53"},
        {"clave_precio": "A", "sku_ford": "A/100/", "clave_vigente": "B",
         "sku_vigente": "B/100/", "cadena": "A/100/ > B/100/", "reemplaza_a": [],
         "estado_reemplazo": "Encontrado", "sucesor_confirmado": True,
         "aviso": "revisar a mano", "extraido_en": "2026-08-22 16:17:53"},
    ])

    filas = filas_de_reemplazos(con_ficha_propia, POR_CLAVE, {})

    a = _por_producto(filas)["25 A"]
    assert a["cadena"] == "A/100/ > B/100/"
    assert a["aviso"] == "revisar a mano"


def test_un_codigo_no_puede_salir_dos_veces():
    """La plataforma no tiene clave unica por producto.

    Si se colaran dos filas del mismo codigo, `por_producto` se quedaria con
    cualquiera de las dos y la ficha diria un vigente distinto en cada corrida.
    """
    dos_lo_reclaman = _reem([
        {"clave_precio": "C", "sku_ford": "C/100/", "clave_vigente": None,
         "sku_vigente": None, "cadena": None, "reemplaza_a": ["A"],
         "estado_reemplazo": "Encontrado", "sucesor_confirmado": True,
         "aviso": None, "extraido_en": "2026-08-22 16:17:53"},
        {"clave_precio": "B", "sku_ford": "B/100/", "clave_vigente": None,
         "sku_vigente": None, "cadena": None, "reemplaza_a": ["A"],
         "estado_reemplazo": "Encontrado", "sucesor_confirmado": True,
         "aviso": None, "extraido_en": "2026-08-22 16:17:53"},
    ])
    por_clave = {"A": "25 A", "B": "25 B", "C": "25 C"}

    filas = filas_de_reemplazos(dos_lo_reclaman, por_clave, {})

    productos = [f["producto"] for f in filas]
    assert productos.count("25 A") == 1
    # Y gana siempre el mismo: alfabetico, no el orden en que vino el archivo.
    assert _por_producto(filas)["25 A"]["reemplazado_por"] == "25 B"


def test_un_codigo_que_curifor_no_tiene_no_se_publica():
    """La tabla es para mostrar en pantalla; un codigo ajeno no se puede mostrar.

    Y si al filtrar queda una fila que no dice nada -sin sucesor y sin ningun
    predecesor que Curifor tenga- tampoco se publica: seria una fila muda
    ocupando lugar en la foto.
    """
    filas = filas_de_reemplazos(SOLO_EL_VIGENTE, {"B": "25 B"}, {})

    assert filas == []


# --- El mismo repuesto, partido de dos formas -----------------------------------
# `8A61/A03195AE5/YY/` y `8A61/A03195/AE/5YY` son el mismo numero de parte con el
# slash en otro lugar, y dan la misma `clave_precio`. El traductor consulta las dos
# particiones cuando no esta seguro, asi que el portal devuelve las dos fichas.


def _fila(sku, clave, **kw):
    base = {
        "clave_precio": clave, "sku_ford": sku, "clave_vigente": None,
        "sku_vigente": None, "cadena": None, "reemplaza_a": [],
        "estado_reemplazo": "Encontrado", "sucesor_confirmado": True,
        "aviso": None, "extraido_en": "2026-08-22 17:16:50",
    }
    return {**base, **kw}


def test_dos_particiones_del_mismo_codigo_dejan_una_sola_fila():
    """Dos filas del mismo codigo dejan a la plataforma quedandose con cualquiera.

    No hay clave unica por producto: `por_producto` arma un dict y gana la ultima
    que entro. En `AB3917D698AC3ZH` una de las dos traia el vigente y la otra no,
    o sea que el aviso al comprador aparecia segun el orden de insercion.
    """
    wings = _reem([
        _fila("8A61/A03195AE5/YY/", "X"),
        _fila("8A61/A03195/AE/5YY", "X", sku_vigente="Z/1/", clave_vigente="Z1"),
    ])

    out = combinar_reemplazos_ford(_reem([]), wings)

    assert out.height == 1
    # Gana la que resolvio sucesor: es la que tiene algo que avisar.
    assert out["sku_vigente"].to_list() == ["Z/1/"]


def test_una_clave_repetida_no_multiplica_la_fila_del_otro_lado():
    """El cruce es un `left join` por clave: repetirla a la derecha duplica.

    Es la trampa clasica del join, y aca se paga caro porque el resultado se
    publica tal cual.
    """
    lista = _reem([
        _fila("A/1/", "X", reemplaza_a=["V1"]),
        _fila("A/1//", "X", reemplaza_a=["V1"]),
    ])
    wings = _reem([_fila("A/1/", "X", sku_vigente="Z/1/", clave_vigente="Z1")])

    out = combinar_reemplazos_ford(lista, wings)

    assert out.height == 1
    # Y no se pierde la direccion inversa, que solo trae la lista de precios.
    assert out["reemplaza_a"].to_list() == [["V1"]]


# --- El vigente no puede estar el mismo dado de baja -----------------------------
# La columna se llama "el codigo vigente" y con ella se compra. Al 24-08-2026 eran
# 140 filas de 4.230 apuntando a un intermedio de la cadena.


def test_el_vigente_se_resuelve_hasta_el_final_de_la_cadena():
    """A -> B -> C: la fila de A tiene que decir C, no B.

    Lo levanto Abastecimiento con `17 2005485`, que decia que su vigente era
    `17 GK2Z9365A` cuando ese codigo tambien estaba descontinuado.
    """
    tres = _reem([
        _fila("A/1/", "A", sku_vigente="B/1/", clave_vigente="B"),
        _fila("B/1/", "B", sku_vigente="C/1/", clave_vigente="C"),
        _fila("C/1/", "C", reemplaza_a=["B"]),
    ])
    por_clave = {"A": "25 A", "B": "25 B", "C": "25 C"}

    filas = _por_producto(filas_de_reemplazos(tres, por_clave, {}))

    assert filas["25 A"]["reemplazado_por"] == "25 C"
    assert filas["25 B"]["reemplazado_por"] == "25 C"


def test_un_codigo_no_se_reemplaza_a_si_mismo():
    """Pasa cuando dos numeros de parte caen en la misma clave del maestro.

    `18 GN1Z8419AC` salia apuntandose a si mismo.
    """
    solo = _reem([_fila("X/1/", "X", sku_vigente="X/1/B", clave_vigente="X")])

    filas = _por_producto(filas_de_reemplazos(solo, {"X": "18 X"}, {}))

    assert filas["18 X"]["reemplazado_por"] is None
    assert "de si mismo" in filas["18 X"]["aviso"]


def test_un_ciclo_no_cuelga_y_queda_avisado():
    """`19 1S7Z6375D` y `19 1S7Z6375E` se reemplazan mutuamente.

    Seguir la cadena a ciegas seria un bucle infinito. Se corta, se deja el dato
    como esta y se avisa: no hay forma de saber cual de los dos manda.
    """
    ciclo = _reem([
        _fila("D/1/", "D", sku_vigente="E/1/", clave_vigente="E"),
        _fila("E/1/", "E", sku_vigente="D/1/", clave_vigente="D"),
    ])

    filas = _por_producto(filas_de_reemplazos(ciclo, {"D": "19 D", "E": "19 E"}, {}))

    assert "vuelve sobre si misma" in filas["19 D"]["aviso"]
    assert "vuelve sobre si misma" in filas["19 E"]["aviso"]
