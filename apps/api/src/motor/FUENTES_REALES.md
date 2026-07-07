# Fuentes crudas reales — evaluación para independizar el motor del Power BI

Estado: el motor tiene **paridad 100%** contra el modelo, pero hoy lee de
`data/paridad/` (CSV extraídos del propio Power BI). Para reemplazar el Power BI
hay que alimentar las mismas entradas desde los **crudos reales** (SharePoint + SQL).
Este documento es la evaluación de esa conexión: qué fuente alimenta cada entrada,
qué columnas se necesitan, y las brechas. **No conecta nada** (requiere credenciales
y decisiones del usuario); es el plano para hacerlo cuando se retome.

Fuente de verdad del modelado: `REFERENCIA_MODELO.md` (cadena DAX/M) + las particiones
M del `.pbix` ya inspeccionadas.

---

## Mapa: entrada del motor → fuente cruda real

Cada entrada de `pipeline.cargar_fuentes()` y su origen real. "Columnas" = las que
el motor consume hoy (headers de los CSV de paridad).

| Entrada del motor | Columnas que usa | Fuente cruda real | Tipo |
|---|---|---|---|
| `ventas_12m` | Producto, SUCURSAL, TipoVenta, Fecha, CantidadAjustada, Fuente | **Curifor**: SQL `Tmp_ProdMensualPostVta` (E01, fecha≥2018) + histórico. **Frontera**: `Informe Gestión Producción REP ST GAR D&P`. En SharePoint `respaldoBBDD` como Excel anuales (`2018.xlsx`…). | SQL + Excel |
| `mapeo_master` | Producto, Producto_Master | Mix reemplazos `BASE NUEVO MIX 2026_1.xlsx` (Andrés) | Excel |
| `dim_producto` | Producto, Categoria (+ **Descripcion, FILTRO1_Final, Unidad de Medida** para el contrato) | Catálogo `Listado Maestro Repuestos.xlsx` | Excel |
| `dim_sucursal` | SucursalID, Nombre, Region, EsOperativa | Tabla de configuración (casi estática) | config/Excel |
| `seguimiento` | Producto, SucursalID, RazonSocial, FechaOC, NOC, Origen, Motivo | **SQL `Tmp_SeguimientoCompraNacional`** (nacional) + `…curifor importado` + `…frontera` (Excel) | SQL + Excel |
| `seguimiento_transito` | + Cantidad, EstadoOC, EstadoDoc, FechaDoc | mismo seguimiento (todas las columnas) | SQL + Excel |
| `stock` (`stock_bodegas`) | Producto, SucursalID, Stock (+ **Costo** para costo_unitario) | `Stock bodegas.xlsx` (SharePoint `AbastecimientoyLogstica-DataBI`) | Excel |
| `stock_frontera` | Producto, SucursalID, Stock | `Stock bodegas Frontera.xlsx` | Excel |
| `lt_proveedor` | Razón Social Proveedor, Lead Time Dias | **DERIVADO** (lo calcula el modelo desde el seguimiento) | ⚠ derivado |
| `lt_proveedor_sucursal` | + SucursalID, N Muestras | **DERIVADO** (idem, por sucursal) | ⚠ derivado |
| `importados` | Producto | `distinct` de la tabla de seguimiento importado | Excel |

---

## SQL del seguimiento (lo que planteaste: datos frescos vs SharePoint)

**Confirmado desde la partición M del `.pbix`:** el seguimiento nacional sale de
SQL Server, no del Excel de SharePoint. Por eso el SharePoint puede estar
desactualizado respecto a lo que ve la plataforma vía Power BI.

- Servidor: `10.50.15.2`
- Base: `BDFlexline`
- Tabla: `Tmp_SeguimientoCompraNacional` (nacional). Importado y Frontera llegan por Excel aparte.
- Ventas Curifor: misma instancia, `Tmp_ProdMensualPostVta` (Empresa `E01`, fecha ≥ 31-12-2018).

### Evaluación de conexión (sin ejecutar)

- **Driver**: es SQL Server. Dos caminos en Python:
  - `pyodbc` + ODBC Driver 17/18 for SQL Server (el estándar; requiere instalar el driver en el host).
  - `pytds` (puro Python, sin driver del sistema) — útil si el motor corre en Linux/contenedor (GitHub Actions) sin ODBC.
- **Red**: `10.50.15.2` es IP privada de la LAN de Curifor. Desde el PC de la oficina hay acceso directo; desde la nube (Render/Actions) **no** hay ruta a esa IP sin VPN/túnel. Implicancia: la extracción del seguimiento fresco debe correr **dentro de la red de Curifor** (el mismo lugar que hoy corre la sync del Power BI), y desde ahí empujar a la nube — igual que el patrón actual `push_to_cloud`.
- **Credenciales**: faltan (usuario/clave de `BDFlexline`, o autenticación integrada de Windows). Las tiene el admin del ERP Flexline. No van al repo: `.env` / secreto del host.
- **Consulta**: `SELECT` de solo lectura sobre la tabla `Tmp_*` (son tablas temporales/staging que el ERP refresca). Verificar con el admin cada cuánto se refrescan esas `Tmp_` (si es intradía, el seguimiento fresco tiene sentido; si es diario, empata con la sync actual).

### Las TRES fuentes SQL confirmadas (desde las particiones M del modelo)

Todas en `Sql.Database("10.50.15.2", "BDFlexline", ...)`:

| Fuente | Tabla / query | Empresa | Notas |
|---|---|---|---|
| Seguimiento nacional | `Tmp_SeguimientoCompraNacional` | E01 | trae `[Fecha Orden de Compra]` y `[Fecha Documento P/E]` → insumo del lead time |
| Ventas Curifor | `Tmp_ProdMensualPostVta` (fecha ≥ 2018-12-31) | E01 | + anexa histórico `Produccion Post Venta Historico (2)` |
| Ventas Frontera | query `Informe Gestión ...` (CASE de SUCURSAL en SQL) | E07 | el SQL ya devuelve SUCURSAL mapeado |

**Ojo — el seguimiento de FRONTERA NO es SQL:** es un Excel de SharePoint
(`AbastecimientoyLogstica-DataBI/.../Frontera - Seguimiento de Compras.xlsx`). Lo SQL
en Frontera son las **ventas** (E07). El seguimiento importado es otra fuente aparte.

**SucursalID** (seguimiento): no viene del SQL, lo deriva el modelo con un SWITCH
sobre el código de local (`SUC020`→CHILLAN, `SUC070`→LINDEROS, `SUC280`→CD REPUESTOS,
…). Replicado en `conectores/sql_flexline.SUCURSAL_ID_MAP`.

### Conector implementado (07-jul-2026): `conectores/sql_flexline.py`

Módulo listo para credenciales, **no ejecutado** (necesita creds del ERP + `pip install
python-tds` + correr en la LAN de Curifor). Contiene:
- Los queries SQL verbatim (seguimiento nacional acotado a lo que usa el motor; ventas Curifor).
- Las transformaciones puras que el modelo hace después (mapeo SucursalID, tag Origen
  "Curifor Nacional", CantidadAjustada con la lista de NC, filtro tipoproducto=repuestos),
  **verificadas con tests offline** (`tests_motor/test_conector_sql.py`, datos sintéticos).
- `conectar()` (credenciales por env `FLEXLINE_SQL_USER`/`FLEXLINE_SQL_PASSWORD`),
  `leer_seguimiento()`, `leer_ventas_curifor()`.

Pendiente para completarlo: (1) pegar el query E07 completo de Frontera (`VENTAS_FRONTERA_QUERY`
= None hoy); (2) anexar el histórico de ventas Curifor; (3) unir seguimiento importado +
Frontera-Excel; (4) un `SELECT TOP 10` real para confirmar dtypes de fecha/números.

---

## Brechas (lo que NO es mecánico)

1. **Lead time derivado (la brecha grande).** `lt_proveedor` y `lt_proveedor_sucursal`
   NO son crudos: el modelo los calcula desde el seguimiento (medida `LT Promedio
   Dias` = días entre Fecha OC y Fecha PE, excluyendo outliers > 30 días). Hoy el
   motor los consume como entrada. Para independizarse hay que **implementar esa
   agregación en el motor** (una etapa nueva: seguimiento → tabla de lead times).
   Bueno: tengo el golden (`lt_proveedor.csv` / `lt_proveedor_sucursal.csv`) para
   validar esa nueva etapa con paridad, igual que las otras cinco. Requiere extraer
   el DAX exacto de `LT Promedio Dias` / `Promedio Días OC a PE` del modelo.

2. **Columnas del contrato hoy vacías** (ver docstring de `pipeline.py`):
   - `Descripcion`, `FILTRO1_Final`, `Unidad de Medida` → del catálogo maestro
     (`Listado Maestro Repuestos.xlsx`); `dim_producto` de paridad solo trae Categoria.
   - `Costo Unitario` y `total_valor_sugerido_clp` → columna `Costo` de `Stock Bodegas`
     (no se extrajo). Con Costo, `total_valor_sugerido_clp = sugerido × costo`.

3. **`Tiene Stock CD`**: el modelo lo saca de `Stock Unificado`; el motor lo aproxima
   con Stock Bodegas+Frontera en CD > 0. Validar contra `Stock Unificado` real
   (o extraer esa tabla) cuando se conecten los crudos.

4. **CantidadAjustada**: es columna calculada del modelo (las NC restan; ver
   `REFERENCIA_MODELO.md`). Si las ventas llegan crudas del SQL/Excel, hay que
   **replicar ese cálculo** antes de entrar al motor (hoy `ventas_12m.csv` ya lo
   trae calculado). Regla conocida: `SUCURSAL_FINAL` y `Producto_Master` ya los
   aplica el motor en `preparar_ventas`; falta solo el signo de las NC.

---

## SharePoint (Graph API / Azure) — diferido al final (decisión del usuario)

Los Excel de stock/ventas/mix/catálogo viven en bibliotecas de SharePoint
(`respaldoBBDD`, `AbastecimientoyLogstica-DataBI`) que **no están sincronizadas
localmente**. Dos formas de leerlos programáticamente:

- **Microsoft Graph API** con el mismo service principal que ya documenta
  `docs/powerbi-sync.md` (Entra ID app registration). Permiso `Sites.Read.All` o
  `Files.Read.All`. Flujo: token client_credentials → `GET /sites/{host}:/sites/{lib}` →
  `/drive/root:/ruta/archivo.xlsx:/content` → leer con polars/openpyxl.
- **Sincronización local** de las bibliotecas (OneDrive) y leer del filesystem —
  más simple si el motor corre en el PC de la oficina (mismo patrón que la sync actual).

Como el motor debe correr **dentro de la red de Curifor** de todos modos (por el
SQL `10.50.15.2`), la sincronización local de SharePoint es probablemente el camino
más simple para la v1, dejando Graph para cuando se quiera correr 100% headless.

---

## Orden recomendado de trabajo (cuando se retome)

1. **Etapa lead-time-desde-seguimiento** en el motor (extraer DAX de `LT Promedio Dias`,
   implementar, validar contra el golden `lt_proveedor*.csv`). Elimina la última
   dependencia de una tabla derivada del modelo.
2. **Verificar nombres reales** de la tabla SQL del seguimiento (`SELECT TOP 10`) y del
   catálogo/stock Excel; completar las columnas de brecha (Costo, Descripcion, etc.).
3. **Adaptador de fuentes** `fuentes_reales.py`: una función por entrada que lee del
   crudo real y devuelve el mismo esquema que hoy espera `cargar_fuentes()`. Validar
   cada una comparando su salida contra el CSV de paridad correspondiente.
4. **Replicar CantidadAjustada** sobre las ventas crudas (signo de NC).
5. Recién entonces, **Graph/headless** si se quiere sacar el motor del PC de la oficina.

Cada paso es validable contra los goldens ya congelados en `tests_motor/fixtures/`,
así que la paridad se mantiene demostrable en todo el trayecto.
