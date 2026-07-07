# Motor de cálculo del sugerido (reemplazo del Power BI)

Reimplementa en Python el modelo DAX de "Sugerido de compras" de Curifor, con
**paridad exacta** validada contra el modelo (18.948/18.948 filas, 0 discrepancias).
El objetivo es que la plataforma deje de depender del Power BI: mismas entradas
crudas, misma salida (el CSV con el contrato de columnas de la plataforma).

## Las 5 etapas (cada una con paridad 100% demostrada)

1. **`clasificacion_abc.py`** — clase ABC local y agregada por frecuencia de venta
   (meses con venta en ventanas 3/6/12m). Genera también las filas sintéticas del
   CD (compra centralizada).
2. **`demanda.py`** — demanda mensual y desviación estándar winsorizadas
   (mediana + 1.4826·MAD); ventana 6m (A/B) o 12m (C/D); CD consolidado.
3. **`lead_time.py`** — proveedor, lead time (por sucursal / global / fallback 8),
   abastecimiento CD, LT efectivo. **`safety_stock.py`** — stock de seguridad
   (Z_clase × σ × √((LT_ef+CO)/22)).
4. **`sugerido.py`** — sugerido = MAX(0, DD·(CO+LT_ef)+SS−SA−ST), necesidad bruta,
   punto de pedido, stock activo y en tránsito.
5. **`traslados.py`** — reparto del stock del CD por prioridad, compra neta,
   "comprar en el CD", traslado lateral entre sucursales.

`parametros.py` centraliza las constantes de negocio (réplica del modelo auditado).

## Pipeline end-to-end

```python
from datetime import date
from src.motor import pipeline

fuentes = pipeline.cargar_fuentes("data/paridad")          # dict de DataFrames
df = pipeline.ejecutar(fuentes, fin_mes_cerrado=date(2026, 7, 1), hoy=date(2026, 7, 6))
pipeline.exportar_csv(df, "sugerido_motor.csv")            # CSV con el contrato de la plataforma
```

`exportar_csv` produce las **53 columnas** que hoy entrega la extracción DAX de la
sync (mismos nombres), listo para el `excel_loader` de la plataforma. Columnas hoy
vacías por falta de fuente cruda (Descripcion, Costo Unitario, etc.): ver el
docstring de `pipeline.py` y `FUENTES_REALES.md`.

## Tests de regresión

```bash
cd apps/api && python -m pytest tests_motor -q      # 8 tests, ~2s
```

Corren el motor sobre 110 productos master congelados en `tests_motor/fixtures/`
(subconjunto de `data/paridad` que cubre todas las ramas) y exigen paridad exacta
contra los goldens en las 5 etapas + el contrato de columnas + el roundtrip del
export. Regenerar fixtures: `python -m tests_motor.regenerar_fixtures`.

## Documentos

- **`REFERENCIA_MODELO.md`** — la lógica DAX/M del modelo original (fuente de verdad).
- **`FUENTES_REALES.md`** — plano para conectar los crudos reales (SQL del seguimiento
  + Excel de SharePoint), análisis de brechas y orden de trabajo. Estado: pendiente.

## Estado

- ✅ Las 5 etapas + pipeline + export con paridad 100% y tests de regresión.
- ⏳ Conectar fuentes crudas reales (ver `FUENTES_REALES.md`): la brecha principal es
  calcular el lead time desde el seguimiento (hoy se consume la tabla derivada del
  modelo). Graph/SharePoint quedó diferido al final.
