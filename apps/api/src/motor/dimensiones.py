"""Las tablas "chicas y estables" que hasta ahora venían congeladas del Power BI.

Réplica de cuatro tablas calculadas del modelo. Con este módulo el motor deja de
necesitar los CSV congelados de `data/paridad` y, con eso, deja de depender del BI:

    Dim Sucursal           -> DATATABLE fija dentro del modelo (no viene de ninguna
                              fuente: alguien la escribió a mano). Se copia acá.
    Dim Producto           -> Categoria (listado maestro), Descripcion (ventas),
                              Unidad de Medida y FILTRO1_Final (reglas derivadas).
    Mapeo Producto Master  -> grupos de reemplazo, desde la Hoja2 del "BASE NUEVO MIX".
    importados             -> los productos que aparecen en el seguimiento importado.

Cada función replica el DAX correspondiente; los comentarios marcan dónde el DAX
hace algo que no es obvio, porque ahí es donde se rompe la paridad si alguien
"mejora" la regla sin mirar el modelo.
"""
from __future__ import annotations

from datetime import date

import polars as pl

# --------------------------------------------------------------------------- #
# Dim Sucursal
# --------------------------------------------------------------------------- #
# Copia literal del DATATABLE de 'Dim Sucursal'. No sale de ninguna fuente: en el
# modelo son 53 filas escritas a mano. Region alimenta el LT del CD a la sucursal
# (RM = 1 día, resto = 2) y EsOperativa distingue bodega virtual de sucursal.
_DIM_SUCURSAL_FILAS: tuple[tuple[str, str, str | None, str | None, str, bool], ...] = (
    ("LA FLORIDA", "La Florida", "SUC010", "RM", "Comercial", True),
    ("CHILLAN", "Chillán", "SUC020", "Nuble", "Comercial", True),
    ("CHILLAN VIEJO", "Chillán Viejo", "SUC030", "Nuble", "Comercial", True),
    ("COQUIMBO", "Coquimbo", "SUC040", "Coquimbo", "Comercial", True),
    ("CURICO", "Curicó", "SUC050", "Maule", "Comercial", True),
    ("DIEZ DE JULIO", "Diez de Julio", "SUC060", "RM", "Comercial", True),
    ("LINDEROS", "Linderos", "SUC070", "RM", "Comercial", True),
    ("LIRA", "Lira", "SUC080", "RM", "Comercial", True),
    ("OVALLE MALL", "Ovalle Mall", "SUC090", "Coquimbo", "Comercial", True),
    ("OVALLE 2", "Ovalle (2)", "SUC100", "Coquimbo", "Comercial", True),
    ("LO BLANCO", "Lo Blanco", "SUC110", "RM", "Comercial", True),
    ("PLACILLA", "Placilla", "SUC120", "OHiggins", "Comercial", True),
    ("RANCAGUA", "Rancagua", "SUC130", "OHiggins", "Comercial", True),
    ("SAN FERNANDO", "San Fernando", "SUC140", "OHiggins", "Comercial", True),
    ("TALCA", "Talca", "SUC150", "Maule", "Comercial", True),
    ("TALCA 2", "Talca (2)", "SUC160", "Maule", "Comercial", True),
    ("AUTOSHOPPING", "Autoshopping", "SUC170", "RM", "Comercial", True),
    ("WEB", "Web", "SUC180", "RM", "Comercial", True),
    ("RANCAGUA USADOS", "Rancagua Usados", "SUC190", "OHiggins", "Comercial", True),
    ("CASA MATRIZ", "Casa Matriz", "SUC200", "RM", "CD", True),
    ("OVALLE 3", "Ovalle (3)", "SUC210", "Coquimbo", "Comercial", True),
    ("CORONEL", "Coronel", "SUC220", "BioBio", "Comercial", True),
    ("MALL PLAZA NORTE", "Mall Plaza Norte", "SUC230", "RM", "Comercial", True),
    ("BRASIL 18", "Brasil 18", "SUC250", "RM", "Comercial", True),
    ("CONCEPCION", "Concepción", "SUC260", "BioBio", "Comercial", True),
    ("GRAN AVENIDA", "Gran Avenida", "SUC270", "RM", "Comercial", True),
    ("CD REPUESTOS", "Centro Distribución Repuestos", "SUC280", "RM", "CD", True),
    ("LA SERENA", "La Serena", "SUC290", "Coquimbo", "Comercial", True),
    ("MAIPU", "Maipú", "SUC300", "RM", "Comercial", True),
    ("RANCAGUA 2", "Rancagua 2", "SUC310", "OHiggins", "Comercial", True),
    ("TALCA 3", "Talca 3", "SUC320", "Maule", "Comercial", True),
    ("MALL PLAZA VESPUCIO", "Mall Plaza Vespucio", "SUC330", "RM", "Comercial", True),
    ("MALL PLAZA NORTE 2", "Mall Plaza Norte 2", "SUC340", "RM", "Comercial", True),
    ("MALL PLAZA SUR", "Mall Plaza Sur", "SUC350", "RM", "Comercial", True),
    ("OFICINAS CENTRALES", "Oficinas Centrales", "SUC360", "RM", "CD", True),
    ("VICUNA MACKENNA", "Vicuña Mackenna", "SUC370", "RM", "Comercial", True),
    ("AUTOPARK", "Autopark", "SUC380", "RM", "Comercial", True),
    ("FLOTA", "Flota", "SUC390", "RM", "Comercial", True),
    ("CURICO 2", "Curicó 2", "SUC400", "Maule", "Comercial", True),
    ("MALL PLAZA EGANA", "Mall Plaza Eñaga", "SUC420", "RM", "Comercial", True),
    ("CANAL DIGITAL", "Canal Digital", "SUC430", "RM", "Comercial", True),
    ("OVALLE", "Ovalle", None, "Coquimbo", "Comercial", True),
    ("BODEGA DANADOS", "Bodega Dañados", None, None, "Virtual", False),
    ("BODEGA DEVOLUCION", "Bodega Devolución", None, None, "Virtual", False),
    ("BODEGA ML", "Bodega Mercado Libre", None, None, "Virtual", False),
    ("BODEGA SCRAP", "Bodega Scrap", None, None, "Virtual", False),
    ("BODEGA IMPORTACION", "Bodega Importación", None, None, "Virtual", False),
    ("COMEX", "Comex", None, None, "Virtual", False),
    ("IMPORTACION MOTOS", "Importación Motos", None, None, "Virtual", False),
    ("PE X REGULARIZAR", "PE por Regularizar", None, None, "Virtual", False),
    ("PE FALTANTE", "PE Faltante", None, None, "Virtual", False),
    ("TRANSITO", "Tránsito", None, None, "Virtual", False),
    ("DESCONOCIDO", "Sin Asignar", None, None, "Revisar", False),
)


def dim_sucursal() -> pl.DataFrame:
    """'Dim Sucursal' del modelo, con el mismo esquema que el snapshot congelado."""
    cols = ["SucursalID", "Nombre", "CodigoLocal", "Region", "Tipo", "EsOperativa"]
    df = pl.DataFrame(
        {c: [fila[i] for fila in _DIM_SUCURSAL_FILAS] for i, c in enumerate(cols)},
        schema={
            "SucursalID": pl.Utf8, "Nombre": pl.Utf8, "CodigoLocal": pl.Utf8,
            "Region": pl.Utf8, "Tipo": pl.Utf8, "EsOperativa": pl.Boolean,
        },
    )
    return df.select(["SucursalID", "Nombre", "Region", "Tipo", "EsOperativa", "CodigoLocal"])


# --------------------------------------------------------------------------- #
# Dim Producto
# --------------------------------------------------------------------------- #
# 'Dim Producto'[FILTRO1]: SWITCH de rubro -> familia comercial (53 rubros, tabla
# MapeoRubro de Abastecimiento). Un rubro que no está acá queda en blanco.
MAPEO_RUBRO: dict[int, str] = {
    10: "NO REPRESENTADOS", 11: "NO REPRESENTADOS", 12: "NO REPRESENTADOS",
    13: "NO REPRESENTADOS", 14: "NO REPRESENTADOS", 15: "FORD", 17: "FORD",
    18: "FORD", 19: "FORD", 20: "FORD", 21: "LUBRICANTES", 22: "LUBRICANTES",
    23: "LUBRICANTES", 24: "NO REPRESENTADOS", 25: "FORD", 26: "LUBRICANTES",
    28: "NO REPRESENTADOS", 29: "NO REPRESENTADOS", 32: "NO REPRESENTADOS",
    33: "OTROS RUBROS", 34: "BMW", 35: "BMW", 36: "BMW", 37: "NO REPRESENTADOS",
    38: "NO REPRESENTADOS", 39: "NO REPRESENTADOS", 40: "OTROS RUBROS",
    41: "LUBRICANTES", 58: "OTROS RUBROS", 61: "FILTROS VARIOS",
    69: "GILDEMEISTER LIVIANOS", 70: "CHEVROLET", 71: "NO REPRESENTADOS",
    72: "IVECO", 74: "NO REPRESENTADOS", 75: "OMODA", 80: "ACCESORIOS",
    81: "OTROS RUBROS", 83: "GILDEMEISTER LIVIANOS", 84: "NO REPRESENTADOS",
    86: "GILDEMEISTER LIVIANOS", 87: "NO REPRESENTADOS", 88: "NO REPRESENTADOS",
    89: "NO REPRESENTADOS", 90: "NO REPRESENTADOS", 91: "NO REPRESENTADOS",
    92: "NO REPRESENTADOS", 93: "NO REPRESENTADOS", 94: "GILDEMEISTER LIVIANOS",
    95: "GILDEMEISTER LIVIANOS", 96: "GILDEMEISTER LIVIANOS",
    98: "NO REPRESENTADOS", 99: "NO REPRESENTADOS", 100: "NO REPRESENTADOS",
    102: "OTROS NEGOCIOS",
}


def _rubro() -> pl.Expr:
    """'Dim Producto'[Rubro]: de la familia del stock ("RUBRO N"), si no del
    prefijo numérico del código ("70 2723982" -> 70)."""
    fam = pl.col("familia_stock").cast(pl.Utf8)
    desde_stock = (
        pl.when(fam.is_not_null() & fam.str.contains("RUBRO "))
        .then(fam.str.replace("RUBRO ", "", literal=True).str.strip_chars().cast(pl.Int64, strict=False))
        .otherwise(None)
    )
    # Solo hay prefijo si el código trae un espacio; si no, no hay rubro.
    prefijo = pl.col("Producto").str.extract(r"^(\d+)\s", 1).cast(pl.Int64, strict=False)
    return pl.coalesce(desde_stock, prefijo).alias("rubro")


def _unidad_de_medida() -> pl.Expr:
    """'Dim Producto'[Unidad de Medida]: marcas explícitas en la descripción, o
    sufijo TML en el código. UNIDAD por defecto.

    OJO: el orden del SWITCH importa. "(500ML)" entra por la segunda rama -tiene
    "ML)" y "("- aunque no diga "(ML)" literal."""
    desc = pl.col("descripcion").fill_null("").str.to_uppercase()
    cod = pl.col("Producto").fill_null("").str.to_uppercase()
    return (
        pl.when(desc.str.contains("(ML)", literal=True)).then(pl.lit("ML"))
        .when(desc.str.contains("ML)", literal=True) & desc.str.contains("(", literal=True)).then(pl.lit("ML"))
        .when(cod.str.ends_with("TML")).then(pl.lit("ML"))
        .when(desc.str.contains("(LT)", literal=True)).then(pl.lit("LITRO"))
        .when(desc.str.contains("(KG)", literal=True)).then(pl.lit("KG"))
        .when(desc.str.contains("(GR)", literal=True)).then(pl.lit("GR"))
        .otherwise(pl.lit("UNIDAD"))
        .alias("unidad_de_medida")
    )


def _es_brilliance() -> pl.Expr:
    """Código tipo "1234567-XXXX": 7 dígitos, guion en la posición 8."""
    return pl.col("Producto").str.contains(r"^\d{7}-")


def calcular_dim_producto(
    ventas: pl.DataFrame,
    listado_maestro: pl.DataFrame,
    stock: pl.DataFrame,
    productos_frontera: list[str] | None = None,
) -> pl.DataFrame:
    """'Dim Producto': Producto, Categoria, Descripcion, FILTRO1_Final, UnidadMedida.

    - `ventas`: crudo de ventas con Producto, Descripcion Producto (la descripción
      del modelo sale de las VENTAS, no del listado maestro).
    - `listado_maestro`: 'Listado Maestro Repuestos' (Producto, Categoria).
    - `stock`: 'Stock Bodegas' con Producto y Familia, para el rubro "RUBRO N".
    - `productos_frontera`: productos vistos en stock/ventas/seguimiento de Frontera;
      los que además no tienen rubro se marcan CHEVROLET.
    """
    prod = (
        ventas.filter(pl.col("Producto").is_not_null())
        .group_by("Producto")
        # MINX del DAX: la primera descripción no nula en orden alfabético.
        #
        # OJO, diferencia CONOCIDA y a favor del motor: el modelo hace este mínimo
        # sobre las ventas de 2018 en adelante, y ahí hay descripciones viejas que
        # empiezan con "&", "%" o "(Z)". Como esos símbolos ordenan antes que las
        # letras, el modelo termina mostrando "& JUNTA" o "%* F.DECANT(FS1241)8".
        # El motor mira los años que carga (los que usa la demanda) y toma la
        # limpia: "JUNTA". Mismo producto, descripción mejor.
        .agg(pl.col("Descripcion Producto").drop_nulls().min().alias("descripcion"))
    )

    fam = (
        stock.filter(pl.col("Familia").is_not_null())
        .group_by("Producto")
        .agg(pl.col("Familia").max().alias("familia_stock"))
        if "Familia" in stock.columns
        else pl.DataFrame(schema={"Producto": pl.Utf8, "familia_stock": pl.Utf8})
    )
    cols_maestro = ["Producto", pl.col("Categoria").alias("categoria")]
    if "Glosa" in listado_maestro.columns:
        # Respaldo de descripción para los productos que no traen una en las ventas
        # del período cargado (el modelo los deja en blanco).
        cols_maestro.append(pl.col("Glosa").alias("glosa"))
    cat = (
        listado_maestro.filter(pl.col("Producto").is_not_null())
        .unique(subset=["Producto"], keep="first")
        .select(cols_maestro)
    )

    d = prod.join(fam, on="Producto", how="left").join(cat, on="Producto", how="left")
    if "glosa" in d.columns:
        d = d.with_columns(pl.coalesce("descripcion", "glosa").alias("descripcion"))
    d = d.with_columns(_rubro()).with_columns(
        pl.col("rubro").replace_strict(MAPEO_RUBRO, default=None, return_dtype=pl.Utf8).alias("filtro1"),
        _unidad_de_medida(),
    )

    en_frontera = pl.col("Producto").is_in(productos_frontera or [])
    return d.with_columns(
        pl.when(_es_brilliance()).then(pl.lit("GILDEMEISTER LIVIANOS"))
        .when(pl.col("rubro").is_null() & en_frontera).then(pl.lit("CHEVROLET"))
        .otherwise(pl.col("filtro1"))
        .alias("filtro1_final")
    ).select([
        "Producto",
        pl.col("categoria").alias("Categoria"),
        pl.col("descripcion").alias("Descripcion"),
        pl.col("filtro1_final").alias("FILTRO1_Final"),
        pl.col("unidad_de_medida").alias("UnidadMedida"),
    ])


# --------------------------------------------------------------------------- #
# Mapeo Producto Master (grupos de reemplazo)
# --------------------------------------------------------------------------- #
def calcular_mapeo_master(
    mix: pl.DataFrame, ventas: pl.DataFrame, fin_mes_cerrado: date
) -> pl.DataFrame:
    """'Mapeo Producto Master' desde la Hoja2 del "BASE NUEVO MIX".

    Réplica del DAX, que es más cuidadoso de lo que parece. En orden:

    1. Master = producto del mix con al menos un Reem1/2/3.
    2. Se descartan los masters que TAMBIÉN figuran como reemplazo de otro
       (`Conflictos`): si A reemplaza a B y B reemplaza a C, el grupo es ambiguo.
    3. Se descartan los masters cuyo reemplazo comparten con otro master
       (`ReemsCompartidos`): un producto no puede pertenecer a dos grupos.
    4. El master FINAL del grupo no es el del mix: es el miembro que más vendió en
       los últimos 6 meses cerrados. Si empatan, gana el master original.
    """
    ini6 = _mes_menos(fin_mes_cerrado, 6)
    reems = ["Reem1", "Reem2", "Reem3"]
    m = mix.with_columns([
        pl.col(c).cast(pl.Utf8).str.strip_chars().replace("", None) for c in [*reems, "Producto"]
    ]).filter(pl.col("Producto").is_not_null())

    tiene_reem = pl.any_horizontal([pl.col(c).is_not_null() for c in reems])
    masters = m.filter(tiene_reem).select("Producto").unique()
    reem_set = pl.concat(
        [m.filter(pl.col(c).is_not_null()).select(pl.col(c).alias("Producto")) for c in reems]
    ).unique()

    sin_conflicto = masters.join(reem_set, on="Producto", how="anti")

    pares = pl.concat([
        m.join(sin_conflicto, on="Producto", how="semi")
        .filter(pl.col(c).is_not_null())
        .select([pl.col("Producto").alias("master"), pl.col(c).alias("reem")])
        for c in reems
    ]).unique()

    compartidos = (
        pares.group_by("reem").agg(pl.col("master").n_unique().alias("n"))
        .filter(pl.col("n") > 1).select("reem")
    )
    masters_malos = pares.join(compartidos, on="reem", how="semi").select(
        pl.col("master").alias("Producto")
    ).unique()
    finales = sin_conflicto.join(masters_malos, on="Producto", how="anti")

    # El grupo incluye al master y a sus reemplazos.
    grupo = pl.concat([
        finales.select([pl.col("Producto").alias("master_orig"), pl.col("Producto")]),
        pares.join(finales, left_on="master", right_on="Producto", how="semi").select([
            pl.col("master").alias("master_orig"), pl.col("reem").alias("Producto")
        ]),
    ]).unique()

    v = (
        ventas.filter((pl.col("Fecha") >= ini6) & (pl.col("Fecha") < fin_mes_cerrado))
        .group_by("Producto").agg(pl.col("Cantidad").sum().alias("ventas"))
    )
    g = grupo.join(v, on="Producto", how="left").with_columns(
        pl.col("ventas").fill_null(0),
        # Desempate del DAX: TOPN por ([Producto] = master) DESC -> gana el master.
        (pl.col("Producto") == pl.col("master_orig")).cast(pl.Int8).alias("es_master"),
    )
    elegido = (
        g.sort(["ventas", "es_master", "Producto"], descending=[True, True, True])
        .group_by("master_orig").agg(pl.col("Producto").first().alias("Producto_Master"))
    )
    return (
        grupo.join(elegido, on="master_orig", how="left")
        .select(["Producto", "Producto_Master"]).unique(subset=["Producto"], keep="first")
    )


def _mes_menos(fin_mes_cerrado: date, meses: int) -> date:
    """Primer día del mes que está `meses` ventanas atrás del último mes cerrado."""
    total = (fin_mes_cerrado.year * 12 + fin_mes_cerrado.month - 1) - 1 - (meses - 1)
    return date(total // 12, total % 12 + 1, 1)


# --------------------------------------------------------------------------- #
# Importados
# --------------------------------------------------------------------------- #
def calcular_importados(seguimiento_importado: pl.DataFrame) -> pl.DataFrame:
    """Productos que aparecen en 'Seguimiento Compras curifor importado'.

    Es la misma definición del DAX (`ProductosImportados`): estar en ese reporte
    ES ser importado, sin más condición."""
    return (
        seguimiento_importado.filter(pl.col("Producto").is_not_null())
        .select("Producto").unique().sort("Producto")
    )
