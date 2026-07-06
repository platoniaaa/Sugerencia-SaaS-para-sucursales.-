"""Motor de cálculo del sugerido de compras (reemplaza el modelo DAX de Power BI).

Lee datos crudos (ventas, stock, seguimiento de compras) y produce la tabla
`sugerido` con las mismas columnas que hoy entrega el Power BI. El objetivo de
esta primera versión es PARIDAD EXACTA con el modelo DAX; las constantes de
negocio viven en `parametros.py` y replican las del modelo auditado.
"""
