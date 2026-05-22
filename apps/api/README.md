# Backend — Sugerido de Compras (API)

FastAPI + SQLAlchemy 2.0 + SQLite. Sirve los datos del sugerido (pre-calculados desde el
Power BI) y las sugerencias manuales.

## Correr solo el backend

```powershell
# desde apps/api, con el venv activado
.\.venv\Scripts\Activate.ps1
uvicorn src.main:app --reload --port 8000
```

Docs interactivas: http://localhost:8000/docs

## Sembrar datos de ejemplo

```powershell
python -m src.seeds.fake_data
```

## Tests

```powershell
pytest
```

## Endpoints principales

| Metodo | Ruta | Descripcion |
|---|---|---|
| GET | `/api/health` | Healthcheck |
| GET | `/api/sugerido` | Listado con filtros, orden y paginacion |
| GET | `/api/sugerido/kpis` | KPIs agregados segun filtros |
| GET | `/api/sugerido/{producto}/{sucursal_id}` | Detalle |
| POST | `/api/sugerido/export-excel` | Genera .xlsx con filtros + columnas |
| GET/POST/PATCH/DELETE | `/api/sugerencias-manuales` | CRUD sugerencias manuales |
| GET | `/api/productos`, `/api/productos/{producto}`, `/api/sucursales` | Catalogo |
| POST | `/api/admin/cargar-sugerido` | Sube Excel/CSV y reemplaza la tabla `sugerido` |

## Carga de datos reales

```powershell
curl -F "file=@sugerido.xlsx" http://localhost:8000/api/admin/cargar-sugerido
```

El parser tolera variaciones en las cabeceras (acentos, may/min, espacios). Ver
`src/services/excel_loader.py` para el mapeo de columnas.

## Estructura

```
src/
  main.py          # app FastAPI + CORS + routers
  config.py        # settings desde .env
  db.py            # engine, sesion, create_all
  models/          # tablas SQLAlchemy (sugerido, sugerencia_manual, dims)
  schemas/         # contratos Pydantic v2
  routers/         # endpoints
  services/        # sugerido_service, excel_loader, excel_export
  seeds/           # datos de ejemplo
tests/             # pytest (1+ por endpoint)
```
