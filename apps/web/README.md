# Frontend — Sugerido de Compras (web)

Next.js 14 (App Router) + TypeScript + Tailwind + AG Grid Community. UI en español-Chile.

## Correr solo el frontend

```powershell
npm run dev --workspace apps/web
# o desde la raiz:  npm run dev:web
```

Abre http://localhost:3000. Necesita el backend corriendo en http://localhost:8000
(configurable en `.env.local` → `NEXT_PUBLIC_API_URL`).

## Tests

```powershell
npm run test --workspace apps/web
```

## Estructura

```
app/
  layout.tsx                    # header + tipografia (IBM Plex)
  page.tsx                      # Dashboard: filtros, KPIs, tabla, export, modales
  producto/[producto]/page.tsx  # Vista detalle de un producto/sucursal
  cargar/page.tsx               # Subir Excel/CSV del sugerido
components/
  ui/            # primitivas estilo shadcn (button, card, dialog, input, badge, multiselect)
  kpi-cards.tsx
  filtros-sugerido.tsx
  tabla-sugerido.tsx            # AG Grid con virtualizacion
  configurar-columnas.tsx       # modal, persiste en localStorage
  modal-sugerencia-manual.tsx
  vista-detalle-producto.tsx
lib/
  api-client.ts   # llamadas al backend
  formato.ts      # CLP / fechas chilenas
  columnas.ts     # definicion de columnas de la tabla
  types.ts        # tipos espejo de los schemas del backend
```

## Notas

- La tabla usa AG Grid Community (virtualiza miles de filas). Las columnas visibles se
  guardan en `localStorage` (`sugerido_columnas_visibles`).
- El grafico de ventas mensuales del detalle quedo fuera de Fase 0 porque el snapshot del
  BI no trae historico mensual; se agrega cuando ese dato exista (ver roadmap).
