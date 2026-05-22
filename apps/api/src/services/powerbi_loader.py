"""Ingesta automatica desde Power BI Service via la API REST `executeQueries` (DAX).

Flujo: autentica con un service principal (app registrada en Entra ID) -> corre una
consulta DAX sobre el dataset publicado -> recibe la tabla del sugerido como JSON ->
la carga en la tabla `sugerido` reutilizando la logica de `excel_loader`.

Requisitos: dataset publicado en el Power BI Service, licencia Pro, y el service
principal con acceso al workspace. Limite de la API: 100.000 filas por consulta
(por eso la DAX por defecto filtra pedir="Si").
"""
from __future__ import annotations

import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from . import excel_loader

settings = get_settings()

_AUTHORITY = "https://login.microsoftonline.com"
_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
_API = "https://api.powerbi.com/v1.0/myorg"

# Las columnas en executeQueries vienen como "Tabla[Columna]", "'Tabla'[Columna]"
# o "[Medida]". Esta expresion extrae solo el nombre de la columna/medida.
_COL_RE = re.compile(r"\[(?P<col>[^\[\]]+)\]\s*$")


def _nombre_columna(clave: str) -> str:
    m = _COL_RE.search(clave.strip())
    return m.group("col") if m else clave.strip()


def transformar(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convierte las claves 'Tabla[Columna]' que devuelve Power BI a 'Columna'.

    Es la parte testeable sin red.
    """
    return [{_nombre_columna(k): v for k, v in row.items()} for row in rows]


def _token() -> str:
    url = f"{_AUTHORITY}/{settings.powerbi_tenant_id}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.powerbi_client_id,
        "client_secret": settings.powerbi_client_secret,
        "scope": _SCOPE,
    }
    r = httpx.post(url, data=data, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"No se pudo autenticar con Entra ID ({r.status_code}): {r.text[:300]}")
    return r.json()["access_token"]


def _execute_queries(token: str, dax: str) -> list[dict[str, Any]]:
    url = (
        f"{_API}/groups/{settings.powerbi_group_id}"
        f"/datasets/{settings.powerbi_dataset_id}/executeQueries"
    )
    body = {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}}
    r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"Power BI executeQueries fallo ({r.status_code}): {r.text[:500]}")
    payload = r.json()
    try:
        return payload["results"][0]["tables"][0]["rows"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Respuesta inesperada de Power BI: {payload}") from e


def sync(db: Session, dax: str | None = None) -> dict:
    """Trae la tabla del sugerido desde Power BI y reemplaza el snapshot local."""
    if not settings.powerbi_configurado:
        raise RuntimeError(
            "Power BI no esta configurado. Define POWERBI_TENANT_ID, POWERBI_CLIENT_ID, "
            "POWERBI_CLIENT_SECRET, POWERBI_GROUP_ID y POWERBI_DATASET_ID en .env"
        )
    token = _token()
    rows = _execute_queries(token, dax or settings.powerbi_dax_query)
    registros = transformar(rows)
    filas, detectadas, ignoradas = excel_loader.procesar_registros(registros)
    resultado = excel_loader.persistir_filas(db, filas, detectadas, ignoradas)
    resultado["origen"] = "powerbi"
    resultado["filas_recibidas"] = len(rows)
    if len(rows) >= 100_000:
        resultado["advertencias"].append(
            "Se recibieron 100.000 filas (limite de la API). Ajusta la consulta DAX "
            "para filtrar o paginar; podrian faltar datos."
        )
    return resultado
