# ADR 0003 — Stack tecnologico y monorepo

**Estado:** Aceptado · **Fecha:** 2026-05-21

## Contexto

El proyecto debe arrancar como MVP para un usuario, pero evolucionar a un SaaS multi-tenant
con chatbot IA y generacion de ordenes de compra.

## Decision

- **Backend:** Python + FastAPI + SQLAlchemy 2.0 + Pydantic v2. FastAPI da OpenAPI gratis
  (`/docs`), tipado fuerte y un camino natural a la logica de calculo de Fase 1 (pandas).
- **Frontend:** Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui. **AG Grid
  Community** para la tabla principal (virtualiza 30k+ filas con filtros/orden). **Recharts**
  para graficos.
- **Monorepo con npm workspaces** (`apps/web`, `packages/*`). El prompt sugeria pnpm; se usa
  npm porque ya esta instalado. `apps/api` es Python y se maneja con su propio venv.
- **DuckDB / pandas / Alembic:** se posponen. En Fase 0 no hay calculo pesado ni migraciones
  complejas; las tablas se crean con `Base.metadata.create_all`. Esto reduce el riesgo de
  ruedas (wheels) faltantes en Python 3.14 y simplifica el setup. Llegan en Fase 1.

## Consecuencias

- (+) Setup minimo, pocas dependencias nativas.
- (+) Arquitectura lista para las fases siguientes (servicios, tenant_id, parametros JSON).
- (-) Sin migraciones formales en Fase 0; al cambiar el esquema se recrea la DB local (los
  datos reales se vuelven a subir por Excel, asi que no es critico).
