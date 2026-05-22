# @sugerido/shared-types

Paquete reservado para los tipos TypeScript compartidos entre `apps/web` y futuras apps.

**Fase 0:** los tipos viven en `apps/web/lib/types.ts` (espejo manual de los schemas
Pydantic del backend).

**Plan (Fase 1+):** generar estos tipos automaticamente desde el JSON Schema que expone
FastAPI (`/openapi.json`) usando una herramienta como `openapi-typescript`, para que el
contrato backend↔frontend no se desincronice.
