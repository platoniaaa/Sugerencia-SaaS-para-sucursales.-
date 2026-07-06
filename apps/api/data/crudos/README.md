# Datos crudos del motor (descarga manual desde SharePoint)

Mientras no esté conectado el acceso automático (Graph API, Fase 6), el motor
lee los Excel/CSV desde ESTA carpeta. Nada de aquí se sube a git (solo este
README).

## Qué descargar y de dónde

| Fuente | Biblioteca SharePoint | Qué es |
|---|---|---|
| Ventas | `RespaldosBBDD` → Documentos compartidos | Ventas transaccionales Curifor + Frontera (histórico) |
| Stock bodegas Curifor | `AbastecimientoyLogstica-DataBI` → Data BI/Datos | Stock por producto × bodega |
| Stock bodegas Frontera | `AbastecimientoyLogstica-DataBI` → Data BI/Datos | Ídem, filial Frontera |
| Seguimiento Curifor nacional | `AbastecimientoyLogstica-DataBI` → Data BI/Datos | Órdenes de compra nacionales (fechas OC/PE, estado, motivo) |
| Seguimiento Curifor importado | `AbastecimientoyLogstica-DataBI` → Data BI/Datos | Órdenes/embarques importados |
| Seguimiento Frontera | `AbastecimientoyLogstica-DataBI` → Data BI/Datos | OCs de Frontera |
| Mix de reemplazos | (planilla "mix andres") | Grupos de reemplazo producto → master |
| Dim sucursal | (donde exista; puede exportarse del modelo una vez) | Sucursal, nombre, región |
| Catálogo | (lista de productos maestro) | Producto, descripción, categoría, unidad |

Deja los archivos con su nombre original (los patrones de `src/motor/fuentes.py`
los reconocen por nombre aproximado). Si un archivo no es reconocido, corre:

```powershell
cd apps/api
.venv\Scripts\python.exe -m src.motor.fuentes
```

para ver el inventario (qué fuente encontró qué archivo y qué columnas trae) y
ajustar los patrones en `FUENTES` si hace falta.

## Golden snapshot (referencia de paridad)

`data/golden/` guarda el `sugerido` congelado que produce el Power BI actual:

```powershell
.venv\Scripts\python.exe -m src.motor.golden
```

Los tests de paridad comparan el output del motor contra ese CSV.
