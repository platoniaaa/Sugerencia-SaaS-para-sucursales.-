"""Carga del Excel/CSV exportado del Power BI hacia la tabla `sugerido`.

Tolerante a las cabeceras: normaliza (minusculas, sin acentos, sin espacios) y mapea
contra alias conocidos. Vacia la tabla y reinserta todo (snapshot completo).
"""
from __future__ import annotations

import csv
import io
import unicodedata
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import DimProducto, DimSucursal, Sugerido

settings = get_settings()

# --- Normalizacion de cabeceras -------------------------------------------------

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    for ch in ("?", "(", ")", "%", "$"):
        s = s.replace(ch, "")
    for ch in (" ", "-", "/", "."):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


# Mapa: nombre_normalizado_en_archivo -> campo del modelo.
# Se incluyen alias frecuentes del export del BI.
HEADER_ALIASES: dict[str, str] = {
    "producto": "producto",
    "codigo": "producto",
    "codigo_producto": "producto",
    "descripcion": "descripcion",
    "descripcion_corta": "descripcion",
    "sucursal_id": "sucursal_id",
    "sucursalid": "sucursal_id",
    "sucursal": "sucursal_id",
    "id_sucursal": "sucursal_id",
    "nombre_sucursal": "nombre_sucursal",
    "clasificacion_abc": "clasificacion_abc",
    "abc": "clasificacion_abc",
    "proveedor": "proveedor",
    "filtro1_final": "filtro1_final",
    "filtro1": "filtro1_final",
    "marca": "filtro1_final",
    "tipo_origen": "tipo_origen",
    "es_importado": "es_importado",
    "unidad_medida": "unidad_medida",
    "unidad_de_medida": "unidad_medida",
    "lead_time_dias": "lead_time_dias",
    "lt_efectivo": "lt_efectivo",
    "lt_cd_a_sucursal_dias": "lt_cd_a_sucursal_dias",
    "lt_origen": "lt_origen",
    "abastece_cd": "abastece_cd",
    "prioridad_cd": "prioridad_cd",
    "comprar_en_el_cd": "comprar_en_el_cd",
    "tiene_stock_cd": "tiene_stock_cd",
    "demanda_mensual": "demanda_mensual",
    "demanda_diaria": "demanda_diaria",
    "desv_std_mensual": "desv_std_mensual",
    "stock_seguridad": "stock_seguridad",
    "stock_de_seguridad": "stock_seguridad",
    "punto_de_pedido": "punto_de_pedido",
    "costo_unitario": "costo_unitario",
    "pedir": "pedir",
    "reemplazos": "reemplazos",
    "sugerido_suc": "sugerido_suc",
    "stock_activo_suc": "stock_activo_suc",
    "stock_en_transito_suc": "stock_en_transito_suc",
    "stock_en_cd": "stock_en_cd",
    "sugerido_traslado": "sugerido_traslado",
    "sugerido_compra_neto": "sugerido_compra_neto",
    "total_sugerido_suc": "total_sugerido_suc",
    "total_valor_sugerido_clp": "total_valor_sugerido_clp",
    "total_valor_sugerido_suc_clp": "total_valor_sugerido_clp",
    "valor_sugerido_suc_clp": "total_valor_sugerido_clp",
    "valor_sugerido_clp": "total_valor_sugerido_clp",
    "pedir_flag": "pedir_flag",
    # Nombres tal como aparecen en el VISUAL de Power BI (medidas):
    "total_sugerido": "total_sugerido_suc",
    "stock_activo": "stock_activo_suc",
    "stock_en_transito": "stock_en_transito_suc",
    "comprar_en_cd": "comprar_en_el_cd",
}

# Tipos por campo para castear valores del archivo.
INT_FIELDS = {
    "lead_time_dias", "lt_efectivo", "lt_cd_a_sucursal_dias", "prioridad_cd",
    "stock_seguridad", "punto_de_pedido",
}
FLOAT_FIELDS = {
    "demanda_mensual", "demanda_diaria", "desv_std_mensual", "costo_unitario",
    "sugerido_suc", "stock_activo_suc", "stock_en_transito_suc", "stock_en_cd",
    "sugerido_traslado", "sugerido_compra_neto", "total_sugerido_suc",
    "total_valor_sugerido_clp",
}
BOOL_FIELDS = {"es_importado", "tiene_stock_cd"}


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace("%", "")
    # Formato chileno: miles con punto, decimal con coma -> normalizar.
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(v: Any) -> int | None:
    f = _to_float(v)
    return int(round(f)) if f is not None else None


def _to_bool(v: Any) -> bool | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("si", "sí", "true", "verdadero", "1", "x"):
        return True
    if s in ("no", "false", "falso", "0"):
        return False
    return None


def _cast(field: str, value: Any) -> Any:
    if field in INT_FIELDS:
        return _to_int(value)
    if field in FLOAT_FIELDS:
        return _to_float(value)
    if field in BOOL_FIELDS:
        return _to_bool(value)
    # texto
    if value is None:
        return None
    return str(value).strip() or None


# --- Lectura de archivos --------------------------------------------------------

def _rows_from_xlsx(content: bytes) -> tuple[list[str], list[list[Any]]]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    headers = [str(h) if h is not None else "" for h in next(rows)]
    data = [list(r) for r in rows]
    wb.close()
    return headers, data


def _rows_from_csv(content: bytes) -> tuple[list[str], list[list[Any]]]:
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        class _D(csv.excel):
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
        dialect = _D()
    reader = csv.reader(io.StringIO(text), dialect)
    all_rows = list(reader)
    if not all_rows:
        return [], []
    return all_rows[0], all_rows[1:]


# --- Carga principal ------------------------------------------------------------

def procesar_registros(
    registros: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Dada una lista de registros (dicts {cabecera_cruda: valor}), normaliza las
    cabeceras, las mapea a campos del modelo y castea los valores.

    Es la logica compartida entre la carga por Excel/CSV y la carga desde Power BI.
    Devuelve (filas_mapeadas, columnas_detectadas, columnas_ignoradas).
    """
    mapping: dict[str, str] = {}
    detectadas: list[str] = []
    ignoradas: list[str] = []
    vistos: set[str] = set()
    for reg in registros:
        for h in reg.keys():
            if h in vistos:
                continue
            vistos.add(h)
            field = HEADER_ALIASES.get(_norm(h))
            if field:
                mapping[h] = field
                detectadas.append(f"{h} -> {field}")
            elif h:
                ignoradas.append(h)

    filas: list[dict[str, Any]] = []
    for reg in registros:
        valores: dict[str, Any] = {}
        for h, field in mapping.items():
            if h in reg:
                valores[field] = _cast(field, reg[h])
        filas.append(valores)
    return filas, detectadas, ignoradas


def persistir_filas(
    db: Session,
    filas: list[dict[str, Any]],
    detectadas: list[str],
    ignoradas: list[str],
) -> dict:
    """Reemplaza el snapshot de `sugerido` (y los catalogos) con las filas dadas.

    Cada fila es un dict {campo_modelo: valor_casteado}. Debe incluir al menos
    `producto` y `sucursal_id`.
    """
    campos = set().union(*[f.keys() for f in filas]) if filas else set()
    if "producto" not in campos:
        raise ValueError("No se encontro la columna 'producto' en los datos.")
    if "sucursal_id" not in campos:
        raise ValueError("No se encontro la columna de sucursal en los datos.")

    advertencias: list[str] = []
    if ignoradas:
        advertencias.append("Columnas ignoradas (sin mapeo): " + ", ".join(ignoradas[:20]))

    tenant = settings.default_tenant_id

    # Reemplazo total (snapshot): vaciar y reinsertar.
    db.execute(delete(Sugerido).where(Sugerido.tenant_id == tenant))

    registros_sugerido: list[dict[str, Any]] = []
    productos_vistos: dict[str, dict] = {}
    sucursales_vistas: dict[str, dict] = {}
    saltadas = 0

    for valores in filas:
        if not valores.get("producto") or not valores.get("sucursal_id"):
            saltadas += 1
            continue
        registros_sugerido.append({**valores, "tenant_id": tenant})

        p = valores["producto"]
        if p not in productos_vistos:
            productos_vistos[p] = {
                "producto": p,
                "tenant_id": tenant,
                "descripcion": valores.get("descripcion"),
                "filtro1_final": valores.get("filtro1_final"),
                "unidad_medida": valores.get("unidad_medida"),
                "costo_unitario": valores.get("costo_unitario"),
                "proveedor": valores.get("proveedor"),
                "es_importado": valores.get("es_importado"),
            }
        s = valores["sucursal_id"]
        if s not in sucursales_vistas:
            sucursales_vistas[s] = {
                "sucursal_id": s,
                "tenant_id": tenant,
                "nombre": valores.get("nombre_sucursal"),
                "abastece_desde_cd": valores.get("abastece_cd"),
                "prioridad_cd": valores.get("prioridad_cd"),
            }

    # Inserts en multi-fila (un INSERT con muchas VALUES por lote). Con pg8000 esto es
    # MUCHO mas rapido que executemany (que iria fila por fila por la red). chunk=500
    # mantiene los parametros por debajo del limite de Postgres (~65k).
    def _bulk(model, registros: list[dict], chunk: int = 500) -> None:
        for i in range(0, len(registros), chunk):
            lote = registros[i : i + chunk]
            if lote:
                db.execute(insert(model).values(lote))

    _bulk(Sugerido, registros_sugerido)
    db.execute(delete(DimProducto).where(DimProducto.tenant_id == tenant))
    db.execute(delete(DimSucursal).where(DimSucursal.tenant_id == tenant))
    _bulk(DimProducto, list(productos_vistos.values()))
    _bulk(DimSucursal, list(sucursales_vistas.values()))
    db.commit()

    if saltadas:
        advertencias.append(f"{saltadas} fila(s) sin producto/sucursal fueron omitidas.")

    return {
        "filas_cargadas": len(registros_sugerido),
        "productos": len(productos_vistos),
        "sucursales": len(sucursales_vistas),
        "columnas_detectadas": detectadas,
        "advertencias": advertencias,
    }


def cargar_sugerido(db: Session, filename: str, content: bytes) -> dict:
    """Parsea el archivo Excel/CSV y reemplaza el contenido de la tabla `sugerido`."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        headers, data = _rows_from_csv(content)
    elif name.endswith((".xlsx", ".xlsm")):
        headers, data = _rows_from_xlsx(content)
    else:
        raise ValueError("Formato no soportado. Usa .xlsx o .csv")

    registros = [dict(zip(headers, raw)) for raw in data]
    filas, detectadas, ignoradas = procesar_registros(registros)
    return persistir_filas(db, filas, detectadas, ignoradas)
