# Referencia del modelo DAX/M (extraída del Power BI original)

Fuente de verdad para replicar el cálculo con paridad. Extraído vía MCP del
`.pbix` "Sugerido de compras" (jul-2026). No re-consultar el modelo salvo que
algo aquí quede dudoso.

## Cadena de ventas (→ `Ventas Unificadas`)

**Curifor** (tabla `Planilla Post_venta`, origen M):
- Lee de **SQL Server** `10.50.15.2` / `BDFlexline`, tabla `Tmp_ProdMensualPostVta`,
  `Empresa = 'E01'` y `fecha >= '31-12-2018'`. (En SharePoint esto llega como
  export Excel — el `2018.xlsx` etc.)
- Se anexa la tabla histórica `Produccion Post Venta Historico (2)`.
- Join `Local` → `Dim_Locales (2)[DESCRIPCION]` para resolver **SUCURSAL** (la
  columna SUCURSAL cruda se reemplaza por la descripción del local).
- Join `Tipo-Venta` → `AREA DE VENTA[AREA VENTA]`.
- **Filtro final: `tipoproducto IN {"REPUESTOS","REPUESTO"}`** (¡solo repuestos!).

**Frontera** (tabla `Informe Gestión Producción REP ST GAR D&P`):
- Filtra `Docto-Emitido = "Emitido"` y `Documento IN {"CARGO INTERNO","FACTURA ST",
  "NOTA CREDITO ST","REFACTURACION C/RS","REFACTURACION ST"}`.
- Mapea SUCURSAL: `02 LINDEROS→LINDEROS, 03 PLACILLA→PLACILLA, 05 RANCAGUA→RANCAGUA,
  07 CURICO→CURICO, 10 CHILLAN VIEJO→CHILLAN VIEJO` (resto sin cambio).

**`Ventas Unificadas`** = `UNION(Curifor, Frontera)` con columna `Fuente`
("Curifor"/"Frontera"). Columnas: Fuente, Periodo, Fecha, Producto, Tipo-Venta,
SUCURSAL, tipoDocto, Cantidad, Neto, Total Neta, Costo Neto, Marca, etc.

## CantidadAjustada (columna calculada, exacta)

```
CantidadAjustada =
  IF( tipoDocto IN {"NC CLIENTE S/T","NC-ELECTR REPTO","NC SEGURO S/T",
                    "NC LIQ FACT","NC-ELECTR GD_FAC"},
      -ABS(Cantidad),
       ABS(Cantidad) )
```
Las NC restan; todo lo demás suma en valor absoluto (incluye CARGO INTERNO,
GARANTIAS, etc.). Es la cantidad que usa TODO el cálculo de demanda/ABC.

## VentasLimpias (en la partición de `Sugerido por Sucursal`)

Sobre `Ventas Unificadas`, con:
- `Producto` no vacío y `SUCURSAL_FINAL` no vacío.
- `Fecha < primer día del mes actual` (solo meses cerrados).
- `SUCURSAL_FINAL NOT IN` las 9 excluidas (ver parametros.SUCURSALES_EXCLUIDAS).
- `Producto_Master NOT IN` los 6 productos excluidos (parametros.PRODUCTOS_EXCLUIDOS).
- `Producto NOT IN` productos de categoría COLISION/CAMPAÑAS
  (`Dim Producto[Categoria]`; requiere el catálogo/stock que trae Categoria).

**SUCURSAL_FINAL**: sobre cada fila de Ventas Unificadas,
1. si `SUCURSAL == "LINDEROS"` y `Tipo-Venta == "VTA MOVIL"` → `"LINDEROS VTA MOVIL"`;
2. si `SUCURSAL == "RANCAGUA 2"` → `"RANCAGUA"`;
3. si el resultado ∈ {CANAL DIGITAL, OFICINAS CENTRALES, LINDEROS VTA MOVIL} → `"CD REPUESTOS"`.

**Producto_Master**: `COALESCE(Mapeo Producto Master[Producto_Master], Producto)`
(agrupa el producto en su master del grupo de reemplazo).

## Notas de fuentes crudas (SharePoint)

- Ventas Curifor: exports de `Tmp_ProdMensualPostVta` (parece por año: `2018.xlsx`…).
  Traen `tipoproducto` para el filtro REPUESTOS y `Local`/`SUCURSAL`.
- Ventas Frontera: proviene de `Informe Gestión Producción REP ST GAR D&P`
  (fuente aparte; confirmar su archivo en SharePoint).
- Stock: `Stock bodegas.xlsx` + `Stock bodegas Frontera.xlsx` (header directo,
  trae Categoria, Costo, Reemplazo, Bodega).
- Seguimiento de compras: `Curifor - Seguimiento Compras.xlsx` (+ Importado +
  Frontera). Título en fila 1, headers en fila 2 (a confirmar el header exacto).
- Mix reemplazos: `BASE NUEVO MIX 2026_1.xlsx` (tabla pivote Local×Producto×Periodo).
- Catálogo: `Listado Maestro Repuestos.xlsx` (título en fila 1; trae Categoria).
