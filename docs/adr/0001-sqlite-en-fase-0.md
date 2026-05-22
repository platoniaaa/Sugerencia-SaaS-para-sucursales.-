# ADR 0001 — SQLite en Fase 0 (en vez de PostgreSQL + Docker)

**Estado:** Aceptado · **Fecha:** 2026-05-21

## Contexto

El diseno original pedia PostgreSQL corriendo en Docker. El equipo de Francisco
(usuario unico en Fase 0) **no tiene Docker ni Postgres instalados**, y el objetivo
inmediato es mostrarle una demo a la jefa de Abastecimiento lo antes posible.

## Decision

Usar **SQLite** como almacen en Fase 0, accedido via SQLAlchemy 2.0.

- Es un solo archivo (`apps/api/data/sugerido.db`), cero instalacion.
- SQLAlchemy mantiene el codigo agnostico: cambiar a Postgres es cambiar `DATABASE_URL`.
- El `docker-compose.yml` con Postgres queda en el repo para cuando se escale (Fase 2).

## Consecuencias

- (+) Arranca en cualquier maquina con solo Python + Node.
- (+) Migrar a Postgres no requiere reescribir modelos (mismo ORM).
- (-) SQLite no es concurrente para multiples escritores; suficiente para 1 usuario.
- (-) Se evita `COPY` masivo de Postgres; la carga del Excel usa inserts por lote
  (suficiente para ~16.000 filas).
