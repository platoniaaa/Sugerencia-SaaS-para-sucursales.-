# Sugerido de Compras

Plataforma web para **sugerir la reposicion de inventario** por producto y sucursal.
Replica como aplicacion web el modelo que hoy vive en Power BI. Cliente cero: **Curifor S.A.**
(auto-partes, ~16 sucursales, ~16.000 SKUs).

> **Fase 0 (MVP)** — esta version. Los calculos del sugerido NO se hacen aca: los datos
> vienen **pre-calculados desde el Power BI**. Tu exportas la tabla a Excel/CSV y la subes
> a la app desde el boton **"Cargar datos"**. La app los muestra, los filtra, los exporta y
> te deja agregar sugerencias manuales.

## Que necesitas instalado

- **Node.js 20+** y **npm** (ya instalados)
- **Python 3.11+** (corre en 3.14)

No necesitas Docker ni PostgreSQL: la Fase 0 usa **SQLite** (un archivo local, automatico).

## Como correrlo (Windows / PowerShell)

```powershell
# 1) Una sola vez: instala todo y siembra datos de ejemplo
./setup.ps1

# 2) Cada vez que quieras usarlo: levanta backend + frontend
./dev.ps1
```

Luego abre:

| URL | Que es |
|---|---|
| http://localhost:3000 | Dashboard principal (lo que ve la Mary) |
| http://localhost:3000/cargar | Subir tu Excel del sugerido |
| http://localhost:8000/docs | Documentacion del backend (API) |

> Si PowerShell bloquea los scripts, ejecuta una vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Cargar tus datos reales

1. En Power BI, exporta la tabla **"Sugerido por Sucursal"** a Excel o CSV.
2. En la app, anda a **"Cargar datos"** y sube el archivo.
   - O por linea de comando:
     `curl -F "file=@sugerido.xlsx" http://localhost:8000/api/admin/cargar-sugerido`
3. El dashboard se actualiza con tus datos.

## Estructura del proyecto

```
apps/
  api/   -> Backend (Python + FastAPI + SQLite)
  web/   -> Frontend (Next.js + Tailwind + AG Grid)
packages/
  shared-types/  -> Tipos TypeScript compartidos
docs/adr/  -> Decisiones de arquitectura (por que SQLite, etc.)
docker-compose.yml  -> PostgreSQL, solo para el futuro
```

## Roadmap (fases siguientes)

| Fase | Objetivo |
|---|---|
| **0 (esta)** | Replicar el BI como web: tabla, filtros, KPIs, detalle, export Excel, sugerencias manuales. Datos via upload. |
| 1 | Recalcular el sugerido en Python con parametros configurables. Fuente de datos opcional: Google Sheet en vivo. |
| 2 | Multi-tenant: cualquier empresa carga sus datos y configura sus reglas. |
| 3 | Chatbot (Claude API) que entrevista al usuario y configura las reglas. |
| 4 | Generar ordenes de compra por proveedor (Excel/PDF, luego API a portales B2B). |

Ver `docs/adr/` para las decisiones tecnicas.
