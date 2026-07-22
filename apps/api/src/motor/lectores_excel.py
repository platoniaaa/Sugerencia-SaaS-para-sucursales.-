"""Lectores de los reportes de Flexline exportados a Excel (los que viven en SharePoint).

Puente entre los archivos que el usuario deja en SharePoint y el esquema CRUDO que
esperan las funciones de `conectores.sql_flexline` (que ya replican, y tienen
testeadas, las transformaciones del modelo). Con estos lectores el motor **no
necesita el SQL de Flexline**: alcanza con los Excel.

    Excel de SharePoint  ->  [este modulo]  ->  crudo con nombres del conector
                         ->  normalizar_seguimiento_* / normalizar_ventas_*  ->  motor

Particularidades de estos reportes (verificadas contra los archivos reales del
20-jul-2026):

- La fila de encabezados **no esta fija**: el reporte trae un titulo y filtros
  arriba (importado: fila 9; frontera: fila 8; ventas: fila 0). Por eso se
  DETECTA buscando la primera fila que contenga las columnas obligatorias, en vez
  de hardcodear un numero que se rompe al primer cambio de plantilla.
- La columna A viene vacia (los datos empiezan en la B).
- Las fechas de los seguimientos son texto `dd/mm/aaaa`; las de ventas son
  datetime real. Se aceptan ambos.
"""
from __future__ import annotations

import datetime as dt
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path

import polars as pl

# Filas que se escanean buscando los encabezados antes de darse por vencido.
MAX_FILAS_ESCANEO = 40


def _norm(s: object) -> str:
    """Nombre de columna comparable: sin tildes, sin simbolos, minusculas.

    Asi `N° Orden de Compra`, `N Orden de Compra` y `n° orden de compra` son lo
    mismo, que es como cambian estos reportes entre exportaciones."""
    if s is None:
        return ""
    txt = unicodedata.normalize("NFKD", str(s).strip().lower())
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return "".join(c for c in txt if c.isalnum())


def _indice_de(origen: object, exactos: dict[str, int], normalizados: dict[str, int]) -> int | None:
    """Indice de la columna `origen`, prefiriendo la coincidencia LITERAL.

    Hay reportes con dos columnas distintas que normalizan igual: el respaldo de
    ventas trae `tipoproducto` (REPUESTO / REPUESTOS / MO_ST) y `Tipo Producto`
    (CAMION, RUBRO 70, SERVICIO TECNICO), y no significan lo mismo. Resolviendo
    solo por nombre normalizado ganaba la ultima y el filtro de repuestos se
    aplicaba sobre la columna equivocada: un aceite con 1.158 ventas quedaba
    fuera del sugerido porque su `Tipo Producto` decia CAMION.
    """
    j = exactos.get(str(origen).strip())
    return j if j is not None else normalizados.get(_norm(origen))


def _abrir_hoja(ruta: str | Path, hoja: str | None = None):
    import openpyxl  # import perezoso: solo se necesita al leer Excel

    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    if hoja is not None and hoja in wb.sheetnames:
        return wb, wb[hoja]
    return wb, wb[wb.sheetnames[0]]


def leer_reporte(
    ruta: str | Path,
    columnas: Mapping[str, str],
    *,
    hoja: str | None = None,
    obligatorias: Iterable[str] | None = None,
) -> pl.DataFrame:
    """Lee un reporte de Flexline y devuelve solo las columnas pedidas, renombradas.

    `columnas` mapea nombre_destino -> nombre tal como aparece en el Excel. Las que
    no esten en el archivo salen como nulo (los tres seguimientos no traen las
    mismas columnas y el esquema del motor tiene que cuadrar igual).

    `obligatorias` son los nombres DESTINO que deben existir si o si; se usan para
    reconocer la fila de encabezados y para fallar temprano con un mensaje claro
    si el reporte cambio de formato. Por defecto, todas las de `columnas`.
    """
    ruta = Path(ruta)
    requeridas = [columnas[d] for d in (obligatorias if obligatorias is not None else columnas)]
    wb, ws = _abrir_hoja(ruta, hoja)
    try:
        filas = ws.iter_rows(values_only=True)
        indices: dict[str, int] | None = None
        for i, fila in enumerate(filas):
            if i >= MAX_FILAS_ESCANEO:
                break
            # Dos mapas: por nombre literal y por nombre normalizado. `setdefault`
            # para que gane la PRIMERA y no la ultima; el literal manda (ver
            # `_indice_de`: hay reportes con columnas que normalizan igual).
            exactos: dict[str, int] = {}
            normalizados: dict[str, int] = {}
            for j, v in enumerate(fila):
                if v is None:
                    continue
                exactos.setdefault(str(v).strip(), j)
                normalizados.setdefault(_norm(v), j)
            if all(_indice_de(o, exactos, normalizados) is not None for o in requeridas):
                indices = {
                    destino: j
                    for destino, origen in columnas.items()
                    if (j := _indice_de(origen, exactos, normalizados)) is not None
                }
                break
        if indices is None:
            raise ValueError(
                f"No se encontro la fila de encabezados en {ruta.name} "
                f"(se revisaron {MAX_FILAS_ESCANEO} filas). Faltan columnas como "
                f"{sorted(columnas[d] for d in (obligatorias or columnas))}."
            )

        datos: dict[str, list] = {destino: [] for destino in columnas}
        ancho_max = max(indices.values()) if indices else 0
        for fila in filas:  # el iterador sigue DESPUES del header
            if fila is None or len(fila) <= ancho_max:
                continue
            # Fila de relleno/subtotal: sin la primera columna obligatoria no hay dato.
            if all(fila[j] is None for j in indices.values()):
                continue
            for destino in columnas:
                j = indices.get(destino)
                datos[destino].append(None if j is None else fila[j])
    finally:
        wb.close()

    # Todo a texto: openpyxl mezcla int/str/datetime en una misma columna segun la
    # celda, y polars no puede inferir un tipo para eso. El casteo lo hace cada
    # lector segun lo que la columna significa.
    #
    # Con `.strip()`: los reportes traen codigos con espacios al final ("15 MXD1454M ")
    # y en el modelo eso NO crea un producto aparte -DAX compara texto ignorando el
    # relleno final-, pero en polars si. Sin recortar salian filas duplicadas por
    # producto-sucursal y esas copias no encontraban catalogo ni costo: 66 filas
    # sin Descripcion, Unidad de Medida ni FILTRO1_Final.
    return pl.DataFrame(
        {
            destino: [None if v is None else (v.isoformat() if isinstance(v, (dt.datetime, dt.date)) else str(v).strip())
                      for v in valores]
            for destino, valores in datos.items()
        },
        schema={destino: pl.Utf8 for destino in columnas},
    )


def _a_fecha(col: str) -> pl.Expr:
    """-> Date desde `dd/mm/aaaa`, ISO, o el serial numerico de Excel.

    Los respaldos anuales de ventas NO vienen todos igual: el de 2026 trae la
    fecha como datetime y el de 2025 como serial de Excel (45684 = 27-ene-2025).
    Sin el tercer camino el serial se leia como el texto "45684", no matcheaba
    ningun formato y el archivo entero quedaba con Fecha nula **en silencio**:
    198.032 ventas, medio ano de la ventana de demanda, perdidas sin un error.
    """
    c = pl.col(col).cast(pl.Utf8, strict=False).str.strip_chars()
    serial = pl.col(col).cast(pl.Float64, strict=False)
    return pl.coalesce(
        c.str.to_date("%d/%m/%Y", strict=False),
        c.str.to_date("%Y-%m-%d", strict=False),
        c.str.head(10).str.to_date("%Y-%m-%d", strict=False),
        # Serial de Excel: el origen es 30-dic-1899 por el bug del 1900 bisiesto.
        # El rango acota a fechas plausibles (1954-2119) para no convertir por
        # accidente un numero que no era una fecha.
        pl.when(serial.is_between(20000, 80000))
        .then(pl.lit(dt.date(1899, 12, 30)) + pl.duration(days=serial.cast(pl.Int64)))
        .otherwise(None),
    ).alias(col)


def _a_entero(col: str) -> pl.Expr:
    return pl.col(col).cast(pl.Float64, strict=False).cast(pl.Int64).alias(col)


# --------------------------------------------------------------------------- #
# Seguimientos de compra
# --------------------------------------------------------------------------- #
# Nombre destino -> nombre en el Excel. Los destinos son los que espera
# `sql_flexline.normalizar_seguimiento*` (mismo esquema que trae el SQL).
COLUMNAS_SEGUIMIENTO_NACIONAL = {
    "Producto": "Producto",
    # El reporte trae TRES columnas de local: "Sucursal", "Código Local" y "Nombre
    # Local", y no son lo mismo. El modelo deriva SucursalID de "Sucursal"; usar
    # "Código Local" mandaba 6.964 ordenes a DESCONOCIDO (contra 1.093) y repartia
    # las de un mismo local entre varias sucursales, lo que descuadraba el lead
    # time por proveedor-sucursal.
    "Sucursal": "Sucursal",
    "RazonSocial": "Razón Social Proveedor",
    "Motivo": "Motivo Compra",
    "FechaOC": "Fecha Orden de Compra",
    "NOC": "N° Orden de Compra",
    "Cantidad": "Cantidad",
    "EstadoOC": "Estado Orden de Compra",
    "EstadoDoc": "Estado Documento Base",
    "FechaDoc": "Fecha Documento Base",
    "FechaPE": "Fecha Documento P/E",
}

COLUMNAS_SEGUIMIENTO_IMPORTADO = {
    "Producto": "Producto",
    # El importado trae [Sucursal] casi siempre en blanco -> DESCONOCIDO. Es el
    # comportamiento del modelo (solo aporta al fallback global de proveedor); NO
    # usar "Código Local", que aca viene con el NOMBRE y no con el codigo SUC0XX.
    "Sucursal": "Sucursal",
    "RazonSocial": "Razón Social Proveedor",
    "Motivo": "Motivo Compra",
    "FechaOC": "Fecha Orden de Compra",
    "NOC": "N° Orden de Compra",
    "Cantidad": "Cantidad",
    "EstadoDoc": "Estado Documento Base",
    "FechaDoc": "Fecha Documento Base",
    # El importado no tiene "Fecha Documento P/E": la recepcion de la importacion
    # es el equivalente (es la fecha en que la mercaderia queda disponible).
    "FechaPE": "Fecha Documento Recepción",
    "EstadoOC": "Estado Documento Recepción",
}

COLUMNAS_SEGUIMIENTO_FRONTERA = {
    "Producto": "Producto",
    "NombreLocal": "Nombre Local",
    "RazonSocial": "Razón Social Proveedor",
    "Cantidad": "Cantidad",
    "EstadoDoc": "Estado Documento Base",
    "FechaDoc": "Fecha Documento Base",
    # Frontera no trae OC como tal: el documento base ES la orden de compra.
    "FechaOC": "Fecha Documento Base",
    "NOC": "N° Documento Base",
    "FechaPE": "Fecha Recepción",
}

_FECHAS_SEGUIMIENTO = ("FechaOC", "FechaDoc", "FechaPE")


def _leer_seguimiento(ruta: str | Path, columnas: Mapping[str, str]) -> pl.DataFrame:
    df = leer_reporte(
        ruta, columnas, obligatorias=[d for d in ("Producto", "Cantidad") if d in columnas]
    )
    return df.with_columns(
        [_a_fecha(c) for c in _FECHAS_SEGUIMIENTO if c in df.columns]
        + [_a_entero("Cantidad")]
    )


def leer_seguimiento_nacional_excel(ruta: str | Path) -> pl.DataFrame:
    """'Seguimiento de Compras' de Curifor nacional (el que hoy sale del SQL)."""
    return _leer_seguimiento(ruta, COLUMNAS_SEGUIMIENTO_NACIONAL)


def leer_seguimiento_importado_excel(ruta: str | Path) -> pl.DataFrame:
    """'Seguimiento Compras' de importaciones (O/C IMPORTACION)."""
    return _leer_seguimiento(ruta, COLUMNAS_SEGUIMIENTO_IMPORTADO)


def leer_seguimiento_frontera_excel(ruta: str | Path) -> pl.DataFrame:
    """'Seguimiento de Compras' de Frontera."""
    return _leer_seguimiento(ruta, COLUMNAS_SEGUIMIENTO_FRONTERA)


# --------------------------------------------------------------------------- #
# Ventas (respaldos anuales de SharePoint)
# --------------------------------------------------------------------------- #
# Las columnas crudas que consume `normalizar_ventas_curifor`.
COLUMNAS_VENTAS = {
    "Producto": "Producto",
    "SUCURSAL": "SUCURSAL",
    "Tipo-Venta": "Tipo-Venta",
    "Fecha": "Fecha",
    "Cantidad": "Cantidad",
    "tipoDocto": "tipoDocto",
    "tipoproducto": "tipoproducto",
    "Empresa": "Empresa",
}

# Valor canonico que espera el filtro de repuestos del conector.
_TIPOPRODUCTO_REPUESTOS = "REPUESTOS"


def _tipoproducto_canonico() -> pl.Expr:
    """`4Repuesto` (respaldo Excel) -> `REPUESTOS` (lo que devuelve el SQL).

    El respaldo anual clasifica con un prefijo de orden (`1M.O.`, `3Insumo`,
    `4Repuesto`, `5 Adicional`) que el SQL no tiene. Sin esta equivalencia el
    filtro de repuestos del conector no matchea NADA y las ventas salen vacias."""
    return (
        pl.when(pl.col("tipoproducto").str.to_lowercase().str.contains("repuesto"))
        .then(pl.lit(_TIPOPRODUCTO_REPUESTOS))
        .otherwise(pl.col("tipoproducto"))
        .alias("tipoproducto")
    )


def _sucursal_sin_prefijo() -> pl.Expr:
    """`08 TALCA` -> `TALCA`. El respaldo trae la sucursal con el prefijo de orden
    del informe; el modelo la resuelve via Dim_Locales y el sugerido usa el nombre
    pelado. Los valores sin prefijo (`DIEZ DE JULIO (2)`) quedan igual."""
    return (
        pl.col("SUCURSAL")
        .str.replace(r"^\d{1,2}\s+", "")
        .alias("SUCURSAL")
    )


def leer_ventas_excel(rutas: str | Path | Iterable[str | Path]) -> pl.DataFrame:
    """Respaldos anuales de ventas -> crudo de `normalizar_ventas_curifor`.

    Acepta una ruta o varias (los respaldos vienen partidos por ano: `2024.xlsx`,
    `2020 2023.xlsx`, ...) y las concatena. Ademas de tipar Fecha y Cantidad,
    traduce al vocabulario del SQL las dos columnas donde el respaldo Excel usa
    otro formato (`tipoproducto` y `SUCURSAL`), para que las reglas del modelo
    ya implementadas en `sql_flexline` apliquen sin cambios.
    """
    if isinstance(rutas, (str, Path)):
        rutas = [rutas]
    frames = []
    for ruta in rutas:
        df = leer_reporte(
            ruta, COLUMNAS_VENTAS, obligatorias=["Producto", "Cantidad", "tipoDocto", "tipoproducto"]
        )
        frames.append(
            df.with_columns(
                _a_fecha("Fecha"),
                _a_entero("Cantidad"),
                _tipoproducto_canonico(),
                _sucursal_sin_prefijo(),
            )
        )
    if not frames:
        raise ValueError("leer_ventas_excel necesita al menos un archivo")
    return frames[0] if len(frames) == 1 else pl.concat(frames, how="vertical_relaxed")
