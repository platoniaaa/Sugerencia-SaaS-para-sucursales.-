# ADR 0002 — Carga de datos por subida de Excel/CSV

**Estado:** Aceptado · **Fecha:** 2026-05-21

## Contexto

En Fase 0 los calculos del sugerido NO se reimplementan: el resultado ya existe en el
Power BI de Curifor. Hay que llevar ese resultado a la web app. Francisco actualiza los
datos a diario y no es desarrollador.

## Decision

La fuente de datos de Fase 0 es **un archivo Excel/CSV que el usuario sube** desde la app
(endpoint `POST /api/admin/cargar-sugerido` + pantalla `/cargar`).

- Se exporta del Power BI ("Sugerido por Sucursal") y se sube.
- El backend parsea con `openpyxl`, mapea cabeceras de forma tolerante (acentos, may/min),
  vacia la tabla `sugerido` y reinserta.
- Se documenta como mejora de Fase 1 leer desde una **Google Sheet en vivo** (la idea de
  Francisco de "una hoja en linea que actualizo diariamente"), evitando el paso de subida.

## Consecuencias

- (+) Camino mas corto a la demo, sin autenticacion a servicios externos.
- (+) Funciona offline.
- (-) Es un paso manual diario (subir). La Google Sheet en vivo lo elimina mas adelante.
- El parser tolera columnas extra/faltantes y reporta advertencias, para no romperse ante
  cambios menores del export del BI.
