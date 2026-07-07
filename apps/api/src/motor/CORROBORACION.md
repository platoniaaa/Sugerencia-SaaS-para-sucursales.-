# Corroboración del motor contra el Power BI (07-jul-2026)

Verificación independiente y exhaustiva antes de decidir el corte del Power BI.
Método: se extrajo el output **fresco y completo** de `'Sugerido por Sucursal'`
(las 53 columnas: todas las columnas + las 11 medidas) del Power BI abierto, y se
comparó **columna por columna** contra la salida del motor (`pipeline.contrato`)
corrido sobre los mismos insumos. 18.948 filas.

## Resultado: el motor reproduce el Power BI exactamente

- **Paridad de filas**: 18.948 vs 18.948, mismas llaves (producto × sucursal),
  0 filas de más o de menos.
- **Escalares de cabecera: coinciden al dígito.**

  | Total | Power BI | Motor |
  |---|---|---|
  | Suma Sugerido Suc | 1.443.688 | 1.443.688 |
  | Suma Sugerido Traslado | 62 | 62 |
  | Suma Sugerido Compra Neto | 1.443.688 | 1.443.688 |
  | Suma Stock de Seguridad | 1.075.639 | 1.075.639 |
  | Suma Stock Activo | 4.349.920 | 4.349.920 |
  | Suma Stock en Tránsito | 933 | 933 |

- **Todas las columnas calculadas: 100%** (byte a byte sobre los mismos datos):
  ABC local y agregada, Proveedor, Lead Time, LT Origen, LT CD, LT Efectivo,
  Abastece CD, Prioridad CD, Demanda Mensual/Diaria, Desv Std, Stock de Seguridad,
  Es Importado, Tiene Stock CD, Sucursales Origen CD, Reemplazos, Pedir, Tipo Origen,
  Punto de Pedido, **Total/Sugerido Suc**, Stock en CD, Sugerido Traslado,
  Compra Neto, Comprar en el CD, Traslado lateral, y los 11 stocks por bodega.

Como el motor corrido sobre los insumos guardados reproduce el output FRESCO del
modelo, queda descartado que los insumos estuvieran desactualizados (si el modelo
hubiera cambiado, no cuadraría).

## Diferencias observadas (ninguna es error de cálculo)

1. **BLANK vs 0 (representación).** El Power BI emite BLANK (vacío) donde el valor
   es 0 en: meses con venta 3m/6m/12m, `stock_activo_suc`, `stock_en_transito_suc`.
   El motor emite `0`. Semánticamente idéntico (lo prueba que las sumas coinciden
   al dígito). Tratando BLANK=0, las 5 columnas dan 100%. Es cosmético; si se quiere
   drop-in byte-idéntico, el motor puede emitir null cuando 0 en esas columnas.

2. **Empresa: 49 filas (0,26%) — alcance de datos, no lógica.** El modelo calcula
   Empresa (Solo Curifor / Solo Frontera / Ambas) sobre **toda la historia de ventas
   (desde 2018)**. El insumo de prueba `ventas_12m.csv` tiene solo 12 meses, así que
   49 combos que vendieron por ambos canales pero solo uno dentro de los últimos 12
   meses quedan como "Solo X" en el motor y "Ambas" en el modelo. La lógica del motor
   es idéntica; se resuelve alimentándolo con la historia completa (la fuente real la
   tiene). ABC y demanda no se ven afectados: ventanas ≤12m que el motor filtra solo.

3. **5 columnas de metadata/valor vacías (brechas conocidas).** El motor las deja en
   blanco porque su fuente cruda aún no está conectada (ver `FUENTES_REALES.md`):
   - `Descripcion`, `FILTRO1_Final` (marca), `Unidad de Medida` → catálogo maestro.
   - `Costo Unitario` y `total_valor_sugerido_clp` → columna Costo de Stock Bodegas.
   No afectan el sugerido en unidades; sí el KPI de valor en CLP.

## Checklist para cortar la dependencia del Power BI

Ninguno es un error del motor; son de conexión de datos:

1. **Alimentar el motor con la historia completa de ventas** (no solo 12m) → cierra
   Empresa. Trivial una vez conectada la fuente real.
2. **Conectar catálogo maestro + columna Costo** → llena las 5 columnas de metadata/valor.
3. **(Opcional) Emitir null en vez de 0** en meses/stock activo/tránsito para un CSV
   byte-idéntico al del Power BI.
4. **Etapa lead-time-desde-seguimiento** (ver `FUENTES_REALES.md`): hoy el motor
   consume la tabla de lead time que deriva el modelo; para independencia total hay
   que calcularla desde el seguimiento.

Con (1) y (2) resueltos, el motor produce el mismo CSV que hoy entrega el Power BI,
y la plataforma puede alimentarse de él sin cambios (mismo contrato de 53 columnas).
