# Prompt para Claude Code — Plataforma "Sugerido de Compras"

> **Cómo usar este prompt**: pegalo entero en el chat de Claude Code (claude.ai/code o la extensión de VSCode) cuando abras una carpeta vacía nueva. Claude Code va a crear todo el proyecto y armar la estructura. Después, podés iterar con preguntas más específicas.

---

## Contexto y misión

Vamos a construir **una plataforma web SaaS llamada "Sugerido de Compras"**. Es un sistema de recomendación de reposición de inventario para empresas con múltiples sucursales y catálogos grandes de productos. El cliente inicial (cliente cero) es **Curifor S.A.**, una cadena chilena de auto-partes con ~16 sucursales y ~16.000 SKUs. El objetivo final es comercializar la plataforma a otras empresas similares (importadoras, distribuidoras, ferreterías, repuestos en general).

Soy **Francisco**, analista de datos de Curifor. Construí todo el modelo de negocio actual en Power BI Desktop (modelo `Sugerido de compras.pbix`) con apoyo de Claude. Conozco DAX/M bien pero **no soy desarrollador full-stack experimentado** — necesito que me guíes mucho en el código.

El proyecto tiene **5 fases planificadas**. En este prompt arrancamos la **Fase 0 (MVP) y dejamos la arquitectura preparada para las fases siguientes**.

---

## Fases del proyecto (roadmap general)

| Fase | Objetivo |
|---|---|
| **0 — MVP solo Curifor (ESTA FASE)** | Replicar el BI como web app: tabla principal de sugerido, vista detalle por producto, export Excel, agregar sugerencias manuales. Los cálculos del sugerido NO se hacen acá — los datos vienen pre-calculados desde un CSV/Parquet exportado del Power BI |
| 1 — Reglas configurables | Reimplementar la lógica de cálculo del sugerido en Python (pandas/duckdb), con TODOS los parámetros configurables por la UI |
| 2 — Multi-tenant + onboarding | Cualquier empresa carga sus CSV de ventas/stock/compras y configura sus reglas |
| 3 — Chatbot de entrevista (IA) | Un agente conversacional (Claude API) entrevista al usuario y configura las reglas automáticamente |
| 4 — Compra asistida → automática | Generar PDFs/Excel de orden por proveedor (asistida). Después API a portales B2B (automática) |

**En este prompt SOLO hacemos la fase 0**, pero diseñá la arquitectura pensando en las siguientes.

---

## Stack tecnológico requerido

- **Backend**: Python 3.11+ con FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic (migraciones)
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui
- **Base de datos**: PostgreSQL 15+ (transaccional) + DuckDB embebido en Python (para análisis rápido sobre archivos parquet)
- **Auth (placeholder en Fase 0)**: usar Clerk o NextAuth con un usuario admin hardcodeado. Multi-tenant se construye en Fase 2.
- **Visualizaciones**: Recharts para gráficos, AG Grid Community para tabla principal (porque maneja 50k+ filas con virtualización, filtros, sort)
- **Excel**: `openpyxl` para export
- **Testing**: pytest (backend), Vitest (frontend)
- **Lenguaje de la UI**: **Español** (es-CL). Mensajes, labels, fechas en formato chileno.
- **Estructura monorepo**: usá `pnpm` workspaces con dos carpetas: `apps/api/` (backend) y `apps/web/` (frontend), más `packages/` compartido si hace falta

---

## Estructura de datos (el modelo de negocio)

El modelo del Power BI calcula sugerencias de compra por **Producto × Sucursal**. Cada fila tiene:

### Tabla principal `sugerido` (snapshot del BI)

| Campo | Tipo | Descripción |
|---|---|---|
| `producto` | string | Código del producto (ej. `20 BXO5W30AA`) |
| `descripcion` | string | Descripción corta (ej. `ACEITE 5W30 LITRO RA`) |
| `sucursal_id` | string | ID de sucursal (ej. `LINDEROS`, `RANCAGUA`, `CD REPUESTOS`) |
| `nombre_sucursal` | string | Nombre legible (ej. `Linderos`, `Rancagua`) |
| `clasificacion_abc` | char(1) | `A`, `B`, o `C` |
| `proveedor` | string nullable | Razón social del proveedor real |
| `lead_time_dias` | int | Lead time efectivo en días |
| `lt_efectivo` | int | LT considerando si abastece desde CD o directo |
| `lt_cd_a_sucursal_dias` | int | LT del CD a la sucursal |
| `lt_origen` | string | `Por sucursal`, `Global proveedor`, o `Fallback 8 dias` |
| `abastece_cd` | string | `Si` o `No` — si el producto se abastece desde el CD |
| `prioridad_cd` | int | Prioridad de reparto desde CD (1=más cerca) |
| `demanda_mensual` | decimal | Promedio mensual de ventas |
| `demanda_diaria` | decimal | Demanda mensual ÷ 22 |
| `desv_std_mensual` | decimal | σ mensual para stock seguridad |
| `stock_seguridad` | int | Stock de seguridad = CEILING(1.65 × σ × √((LT+CO)/22), 1) |
| `costo_unitario` | decimal nullable | Costo unitario del producto |
| `pedir` | string | `Si` o `No` — flag de si genera sugerencia |
| `punto_de_pedido` | int | `CEILING(DD × LT + SS, 1)` |
| `es_importado` | bool | TRUE si proveedor importado |
| `tiene_stock_cd` | bool | TRUE si hay stock en el CD |
| `unidad_medida` | string | `UNIDAD`, `LITRO`, etc. |
| `tipo_origen` | string | `Nacional`, `Importado`, `Frontera` |
| `filtro1_final` | string | Marca/segmento (ej. `FORD`, `BOSCH`) |
| `reemplazos` | string nullable | Códigos de productos equivalentes separados por coma |
| `comprar_en_el_cd` | string | `Si` o `No` |

### Medidas (calculadas dinámicamente en el dashboard, NO en la tabla)

| Medida | Descripción |
|---|---|
| `sugerido_suc` | Sugerido de unidades a comprar = `CEILING(DD×(CO+LT) + SS − SA − ST, 1)` |
| `stock_activo_suc` | Stock activo en bodegas de la sucursal (suma del grupo de reemplazos) |
| `stock_en_transito_suc` | Stock con OC pendiente |
| `stock_en_cd` | Stock disponible en CD REPUESTOS |
| `sugerido_traslado` | Unidades cubribles con traslado desde CD respetando ranking |
| `sugerido_compra_neto` | Sugerido total − Traslado posible |
| `total_sugerido_suc` | `sugerido_traslado + sugerido_compra_neto` (lo que finalmente se pide) |
| `total_valor_sugerido_clp` | `total_sugerido_suc × costo_unitario` |
| `pedir_flag` | Si/No basado en `total_sugerido_suc > 0` |

### Fórmulas fundamentales (para Fase 1 cuando se reimplementen)

```python
# Parámetros (configurables en Fase 1, hardcodeados en Fase 0 para Curifor)
Z = 1.65               # Nivel de servicio (95%)
CO = 5                 # Ciclo de orden en días hábiles
DIAS_HABILES_MES = 22

# Cálculos
demanda_diaria = demanda_mensual / DIAS_HABILES_MES
proteccion_meses = (lt_efectivo + CO) / DIAS_HABILES_MES
stock_seguridad = ceil(Z * desv_std_mensual * sqrt(proteccion_meses))
punto_de_pedido = ceil(demanda_diaria * lt_efectivo + stock_seguridad)
stock_optimo = ceil(demanda_diaria * (CO + lt_efectivo) + stock_seguridad)
sugerido = max(0, ceil(demanda_diaria * (CO + lt_efectivo) + stock_seguridad - stock_activo - stock_transito))
```

### Tabla `sugerencias_manuales` (nueva, para fase 0)

Sugerencias agregadas manualmente por el usuario por encima de las del sistema.

| Campo | Tipo |
|---|---|
| `id` | UUID PK |
| `producto` | string FK lógica |
| `sucursal_id` | string FK lógica |
| `unidades` | int |
| `motivo` | text nullable |
| `creado_por` | string (user email) |
| `creado_en` | timestamp |
| `aprobado` | bool default false |
| `usado_en_compra` | bool default false |

### Tabla `dim_producto` (catálogo)

Producto, descripción, marca (`filtro1_final`), unidad de medida, costo unitario, proveedor preferido, es importado.

### Tabla `dim_sucursal`

Sucursal_id, nombre, región, abastece_desde_cd, prioridad_cd.

---

## Pantallas a construir en la Fase 0

### 1. **Dashboard principal** (`/`)

Pantalla principal con la tabla de sugerido. Inspirada en el dashboard actual de Power BI (ver imagen adjunta en el chat).

**Sección superior — filtros tipo "slicer"** (todos opcionales, combinables):
- Búsqueda libre de producto (autocomplete sobre `producto` + `descripcion`)
- Multi-select de `nombre_sucursal`
- Multi-select de `clasificacion_abc` (A, B, C)
- Multi-select de `filtro1_final` (FORD, BOSCH, etc.)
- Toggle `pedir = Si` (default ON)
- Multi-select de `tipo_origen` (Nacional / Importado / Frontera)
- Búsqueda de `proveedor`

**Sección de KPIs (cards en fila)**:
- Total Sugerido (suma de `total_sugerido_suc`)
- Valor Total CLP (suma de `total_valor_sugerido_clp`), formato `$ 1.234 mill` o `$1.234.567`
- # Productos a Comprar
- # Proveedores a Contactar

**Tabla principal (centro)**:

Usar AG Grid Community con virtualización. Columnas por defecto visibles:
- `producto` (sticky left)
- `descripcion` (sticky left)
- `clasificacion_abc`
- `nombre_sucursal`
- `total_sugerido_suc` (sticky right, formato numérico)

Columnas disponibles (ocultas por defecto, mostrables vía menú "Configurar columnas"):
- Todas las demás de la tabla `sugerido` + las medidas dinámicas

**Funcionalidades de la tabla**:
- Click en una fila abre vista de detalle (`/producto/[producto]?sucursal=[sucursal_id]`)
- Botón "Configurar columnas" arriba a la derecha (modal con checkboxes; persistir en localStorage por ahora)
- Botón "Exportar a Excel" (genera .xlsx con las columnas visibles y los filtros aplicados; nombre archivo `sugerido_YYYYMMDD.xlsx`)
- Botón "Agregar sugerencia manual" arriba a la derecha → abre modal

### 2. **Vista detalle de producto** (`/producto/[producto]?sucursal=[sucursal_id]`)

Pantalla rica para un producto en una sucursal específica. Layout:

**Header**:
- Producto code grande + descripción
- Badge de clasificación ABC (color: A=verde, B=amarillo, C=gris)
- Badge de proveedor
- Botón "Volver al dashboard"

**Grid de 3 columnas con cards**:

Columna 1 — *Demanda*:
- Demanda Mensual (con tooltip: "Promedio de los últimos 4 o 6 meses según clasificación")
- Demanda Diaria
- Desv Std Mensual
- Pequeño gráfico de ventas mensuales últimos 6 meses (si los datos están — opcional Fase 0)

Columna 2 — *Stock*:
- Stock Activo Suc (con barra de progreso vs Stock Óptimo)
- Stock en Tránsito Suc
- Stock en CD
- Stock de Seguridad
- Punto de Pedido

Columna 3 — *Lead Time y Compra*:
- Lead Time Días (con `lt_origen` como tooltip)
- LT Efectivo
- Abastece CD: Sí/No
- Prioridad CD
- Costo Unitario
- Valor del Sugerido CLP

**Sección de Sugerido (banner grande abajo)**:
- Sugerido Total: NN unidades — bien grande
- Desglose: "X unidades por traslado desde CD + Y unidades por compra al proveedor"
- Si tiene reemplazos: mostrar lista expandible con códigos del grupo

**Sección de Sugerencias manuales del usuario**:
- Lista de sugerencias manuales creadas para este producto/sucursal
- Botón "Agregar sugerencia manual" (mismo modal del dashboard)

### 3. **Modal "Agregar sugerencia manual"**

Form:
- Producto (autocomplete; pre-llenado si vienen desde vista detalle)
- Sucursal (dropdown; pre-llenado)
- Unidades adicionales (int positivo)
- Motivo (textarea opcional)
- Botón guardar

Después de guardar, refrescar la tabla / vista actual.

---

## Backend — endpoints API mínimos (FastAPI)

### Configuración
- `GET /api/health` — healthcheck

### Catálogo
- `GET /api/productos?q=&page=&limit=` — búsqueda paginada
- `GET /api/productos/{producto}` — detalle del catálogo
- `GET /api/sucursales` — listado

### Sugerido
- `GET /api/sugerido?filtros...&page=&limit=&sort=` — listado con filtros
- `GET /api/sugerido/kpis?filtros...` — KPIs agregados con los mismos filtros
- `GET /api/sugerido/{producto}/{sucursal_id}` — detalle de un producto/sucursal
- `POST /api/sugerido/export-excel` — devuelve un xlsx generado con los filtros del body

### Sugerencias manuales
- `GET /api/sugerencias-manuales?producto=&sucursal_id=`
- `POST /api/sugerencias-manuales`
- `PATCH /api/sugerencias-manuales/{id}` (aprobar, marcar como usada)
- `DELETE /api/sugerencias-manuales/{id}`

### Carga de datos (admin, Fase 0)
- `POST /api/admin/cargar-sugerido` — recibe CSV o Parquet del export del Power BI y carga en la tabla `sugerido`

---

## Carga inicial de datos para Fase 0

Como en Fase 0 NO reimplementamos los cálculos del sugerido, los datos vienen del Power BI:

1. El usuario (yo, Francisco) exporto la tabla `Sugerido por Sucursal` del Power BI a **CSV** (vía DAX Studio o el botón "Export data" del visual)
2. El backend tiene un comando CLI / endpoint admin `POST /api/admin/cargar-sugerido` que recibe el CSV
3. Hace `TRUNCATE` de la tabla `sugerido` y carga las filas nuevas con `COPY`
4. Recalcula índices

Dejar **un script seed** que genera 100 filas de datos fake para que la app arranque sin necesidad de cargar el CSV real.

---

## Estructura de carpetas esperada

```
sugerido-compras/
├── apps/
│   ├── api/                    # Backend FastAPI
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── db.py
│   │   │   ├── models/         # SQLAlchemy models
│   │   │   ├── schemas/        # Pydantic
│   │   │   ├── routers/
│   │   │   │   ├── sugerido.py
│   │   │   │   ├── productos.py
│   │   │   │   ├── sugerencias_manuales.py
│   │   │   │   └── admin.py
│   │   │   ├── services/
│   │   │   │   ├── sugerido_service.py
│   │   │   │   ├── excel_export.py
│   │   │   │   └── csv_loader.py
│   │   │   └── seeds/
│   │   │       └── fake_data.py
│   │   ├── alembic/            # Migraciones
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── web/                    # Frontend Next.js
│       ├── app/
│       │   ├── page.tsx                  # Dashboard principal
│       │   ├── producto/[producto]/page.tsx
│       │   ├── layout.tsx
│       │   └── globals.css
│       ├── components/
│       │   ├── ui/             # shadcn/ui
│       │   ├── tabla-sugerido.tsx
│       │   ├── filtros-sugerido.tsx
│       │   ├── kpi-cards.tsx
│       │   ├── modal-sugerencia-manual.tsx
│       │   └── vista-detalle-producto.tsx
│       ├── lib/
│       │   ├── api-client.ts
│       │   ├── formato.ts      # formatear CLP, fechas chilenas
│       │   └── types.ts
│       ├── package.json
│       └── README.md
├── packages/
│   └── shared-types/           # Tipos compartidos via Pydantic→JSON Schema→TS
├── docker-compose.yml          # Postgres local
├── pnpm-workspace.yaml
├── .env.example
└── README.md                   # Cómo correr todo localmente
```

---

## Reglas y convenciones para Claude Code

1. **No reimplementar cálculos en Fase 0**. Los datos vienen pre-calculados del CSV. Solo se calculan en frontend agregaciones simples (sumas de KPIs según filtros).
2. **Todo el código en inglés**, pero **toda la UI en español-Chile**. Comentarios pueden ir en español si la explicación es del dominio (ej. explicar qué es "stock de seguridad").
3. **Currency formatting chileno**: `$1.234.567` (sin decimales, miles con punto, símbolo CLP).
4. **Fechas formato chileno**: `dd-mm-aaaa` para display, ISO 8601 internamente.
5. **Tests mínimos**: al menos 1 test por endpoint del API; tests de smoke del frontend con Vitest. No buscar 100% coverage en Fase 0.
6. **Documentación**: cada carpeta importante con `README.md` explicando qué hace.
7. **Decisiones arquitectónicas**: dejar `docs/adr/` con Architecture Decision Records cortos (1 página max) para decisiones grandes (por qué Postgres + DuckDB, por qué Next.js, etc.).
8. **Diseño visual**: limpio, profesional, similar al dashboard de Power BI actual. Colores principales: gris claro de fondo, azul corporativo para acentos (`#1e40af`). Buena densidad de información (la persona de compras va a mirar 100s de filas).
9. **Accesibilidad mínima**: contraste WCAG AA, labels en inputs, navegación por teclado en la tabla.
10. **Performance**: tabla debe manejar ~30.000 filas sin lag. Paginar en servidor (50 filas por página default), o cargar todo y virtualizar con AG Grid (preferible si la performance lo permite).

---

## Lo primero que querría ver (sugerido de pasos)

1. Empezás creando la estructura del monorepo con `pnpm-workspace.yaml`, `docker-compose.yml` para Postgres local, `.env.example`, `.gitignore`, README raíz con instrucciones para correr todo.
2. Después backend: setup FastAPI mínimo, modelos SQLAlchemy de las tablas descritas, Alembic con primera migración, seed de datos fake (100 filas).
3. Después frontend: Next.js + Tailwind + shadcn/ui setup, layout básico, página `/` con tabla AG Grid conectada al API (aunque sea sin filtros todavía).
4. Iterar: filtros, KPIs, vista detalle, modal de sugerencia manual, export Excel, "configurar columnas".

**Importante**: al final de cada paso, indicame qué comandos correr para probar localmente (`pnpm dev`, `docker-compose up`, etc.) y qué deberíamos ver.

---

## Para tener en mente (no implementar ahora pero diseñar pensando en esto)

- En **Fase 1** vamos a reimplementar el cálculo del sugerido en Python. Diseñá los modelos de datos de modo que se pueda escribir un job que tome `ventas_unificadas`, `stock_bodegas`, `seguimiento_compras` y produzca la tabla `sugerido`.
- En **Fase 2** todo es multi-tenant: cada empresa tiene su propio dataset aislado. Agregá una columna `tenant_id` a todas las tablas de negocio (no usada en Fase 0 pero presente).
- En **Fase 3** un chatbot va a configurar reglas. Pensá los parámetros como un **JSON serializable** para que sea fácil que la IA los proponga.
- En **Fase 4** vamos a generar órdenes de compra por proveedor. Pensá tener una tabla `orden_compra_borrador` que agrupe `sugerencias` aprobadas por proveedor.

---

## Sobre Curifor (cliente cero)

- Auto-partes, ~16 sucursales en Chile (Linderos, Rancagua, Curicó, Talca, Chillán, etc.)
- ~16.000 SKUs activos, ~16.000 con sugerido (~$987M CLP de sugerencia mensual)
- Sucursales especiales: `CD REPUESTOS` (centro de distribución central), `OFICINAS CENTRALES`, `CANAL DIGITAL`, `LINDEROS VTA MOVIL`
- Productos importados (Ford, GM, etc.) y nacionales (Mahle, marcas locales)
- Proveedores principales: Ford Motor Company Chile, Mahle, Bosch, etc.
- Idioma: **español-Chile informal** ("la jefa", "dale", "ojo con", "está calzando")
- Usuaria principal: Marilyn "Mary" Ramos — jefa de Abastecimiento, no técnica, súper detallista

---

## Resultado esperado al cierre de Fase 0

Una app web local funcionando:
- `localhost:3000` → dashboard con tabla, KPIs, filtros, export Excel
- `localhost:3000/producto/20%20BXO5W30AA?sucursal=LINDEROS` → vista detalle
- `localhost:8000/docs` → docs OpenAPI del backend
- README explicando cómo levantar todo en cualquier máquina
- Datos seed cargados (100 productos × varias sucursales)
- Posibilidad de cargar CSV real con `curl -F file=@sugerido.csv localhost:8000/api/admin/cargar-sugerido`

Cuando esté listo, hacemos demo a la Mary y validamos qué nos falta antes de la Fase 1.

---

**Empezá. Hacé las preguntas que necesites antes de tirar código, pero arrancá con la estructura del monorepo primero.**
