# Sincronización automática desde Power BI

La app puede traer la tabla del sugerido **directo desde el Power BI Service** (sin exportar
Excel) usando la API REST `executeQueries` con una consulta DAX. Esto alimenta:

- El botón **"Sincronizar con Power BI"** en la pantalla `Cargar datos`.
- El job programable `python -m src.jobs.sync_powerbi` (para correr cada mañana en automático).

Si las variables `POWERBI_*` no están configuradas, la app funciona igual cargando por Excel/CSV.

## Requisitos

- El modelo debe estar **publicado en el Power BI Service** (app.powerbi.com), no solo en Desktop.
- Licencia **Power BI Pro** (o PPU/Premium).
- Un **service principal** (app registrada en Entra ID) con acceso al workspace.

## Pasos (los hace un admin de Microsoft 365)

1. **Registrar la app en Entra ID** (portal.azure.com → Microsoft Entra ID → App registrations →
   New registration). Anotar **Directory (tenant) ID** y **Application (client) ID**.
2. **Crear un secreto**: en la app → Certificates & secrets → New client secret. Copiar el
   **Value** (es el `POWERBI_CLIENT_SECRET`; solo se ve una vez).
3. **Permitir service principals en Power BI**: en app.powerbi.com → Configuración de administrador
   → "Allow service principals to use Power BI APIs" → habilitar (idealmente para un grupo de
   seguridad que contenga la app).
4. **Dar acceso al workspace**: en el workspace de Power BI → Access → agregar la app (el service
   principal) como **Member** o **Contributor**.
5. **Obtener los IDs del workspace y dataset**: abrir el dataset en el Service; la URL trae
   `groups/<GROUP_ID>/datasets/<DATASET_ID>`. (También se pueden listar con la API.)

## Configurar la app

En el archivo `.env` de la raíz:

```
POWERBI_TENANT_ID=<tenant id>
POWERBI_CLIENT_ID=<client id>
POWERBI_CLIENT_SECRET=<secret value>
POWERBI_GROUP_ID=<workspace id>
POWERBI_DATASET_ID=<dataset id>
POWERBI_DAX_QUERY=EVALUATE FILTER('Sugerido por Sucursal', 'Sugerido por Sucursal'[pedir] = "Si")
```

> Ajusta el nombre de la tabla en la consulta DAX si en tu modelo se llama distinto.
> La API devuelve **máximo 100.000 filas por consulta**: por eso la consulta por defecto filtra
> `pedir = "Si"`. Si necesitas más, hay que paginar o filtrar más.

## Probar

- Manual (UI): pantalla **Cargar datos** → "Sincronizar ahora".
- Manual (consola): `./scripts/sync_powerbi.ps1`
- Verificar config: `GET http://localhost:8000/api/admin/powerbi/estado` → `{"configurado": true}`

## Programar la sincronización diaria (Windows)

Programador de tareas de Windows → Crear tarea básica:
- Desencadenador: diario, a la hora que quieras (ej. 07:00).
- Acción: iniciar un programa →
  - Programa: `powershell.exe`
  - Argumentos: `-ExecutionPolicy Bypass -File "C:\ruta\al\proyecto\scripts\sync_powerbi.ps1"`

En la nube (producción): el mismo job como cron en GitHub Actions, Azure Container Apps Job, etc.

## Seguridad

- El `POWERBI_CLIENT_SECRET` es sensible: en producción guardarlo en un secreto (Azure Key Vault,
  variables del entorno del host), nunca en el repositorio.
- El service principal solo necesita acceso de lectura al workspace del sugerido.
