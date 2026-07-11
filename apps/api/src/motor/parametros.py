"""Constantes de negocio del motor de sugerido.

Replican EXACTAMENTE las del modelo DAX "Sugerido de compras" (auditado jul-2026).
No cambiar sin validar contra el golden snapshot: la meta de la v1 es paridad.
Cualquier regla nueva se conversa con Abastecimiento (Mary) antes de tocarla aquí.
"""
from __future__ import annotations

# --- Identificadores canónicos -------------------------------------------------

CD_ID = "CD REPUESTOS"  # SIEMPRE con espacio (el guion bajo fue un bug histórico)

# --- Limpieza de ventas (VentasLimpias) ----------------------------------------

# Sucursales que NO participan del sugerido (cerradas o fuera de alcance).
SUCURSALES_EXCLUIDAS = {
    "LA FLORIDA", "LIRA", "LO BLANCO",
    "MALL PLAZA NORTE", "MALL PLAZA SUR", "MALL PLAZA VESPUCIO",
    "OVALLE (3)", "GRAN AVENIDA", "COQUIMBO",
}

# Sucursales "especiales" cuya venta se consolida en la fila del CD
# (no son filas propias del sugerido).
ESPECIALES_CD = {"CANAL DIGITAL", "OFICINAS CENTRALES", "LINDEROS VTA MOVIL"}

# Productos/conceptos no comprables excluidos de la demanda.
PRODUCTOS_EXCLUIDOS = {
    "D&P REPTO-TALLER(T)", "D&P REPTO-TALLER(R)", "MEC INSUMOS-PESADOS",
    "INCENTIVOS RPTOS", "APLICA-DED-REPTO", "13 BH1X70005AA",
}

# Categorías de producto excluidas (incluye el mojibake histórico de CAMPAÑAS
# que viene así desde la fuente).
CATEGORIAS_EXCLUIDAS = {"COLISION", "CAMPAÑAS", "CAMPAÃ‘AS"}

# Tipos de documento que son nota de crédito (restan en CantidadAjustada).
NC_STD = {
    "NC CLIENTE S/T", "NC-ELECTR REPTO", "NC SEGURO S/T",
    "NC LIQ FACT", "NC-ELECTR GD_FAC",
}

# Normalización de sucursal (SUCURSAL_FINAL), en este orden:
# 1) LINDEROS con Tipo-Venta "VTA MOVIL" -> "LINDEROS VTA MOVIL"
# 2) fusiones directas de sucursal
# 3) si el resultado cae en ESPECIALES_CD -> CD_ID
FUSIONES_SUCURSAL = {
    "RANCAGUA 2": "RANCAGUA",
}
TIPO_VENTA_MOVIL = "VTA MOVIL"
SUCURSAL_LINDEROS = "LINDEROS"
SUCURSAL_LINDEROS_MOVIL = "LINDEROS VTA MOVIL"

# --- Clasificación ABC (por FRECUENCIA de venta, no Pareto) ---------------------

# Ventanas en meses para contar meses-con-venta.
VENTANA_M3, VENTANA_M6, VENTANA_M12 = 3, 6, 12


def clasificar_abc(m3: int, m6: int, m12: int) -> str:
    """SWITCH exacto del modelo DAX (aplica igual a clase local y agregada)."""
    if m6 >= 5:
        return "A"
    if m6 == 4:
        return "B"
    if m6 == 3 and m3 >= 2:
        return "C"
    if m12 > 6 and m6 == 3 and m3 < 2:
        return "C"
    return "D"


# Ventana de demanda según clase: A/B miran 6 meses, C/D miran 12.
def ventana_demanda_meses(clase: str) -> int:
    return 12 if clase in ("C", "D") else 6


# --- Demanda / winsorización ----------------------------------------------------

# Tope de winsorización: mediana + K * 1.4826 * MAD.
# K=3 desde jul-2026 (antes 1). k=1 recortaba demasiado: en productos con venta
# lumpy (picos legítimos ~1 de cada 3 meses) casi borraba los picos reales; k=3
# solo tapa el extremo. Decisión de Abastecimiento, aplicada también en el DAX.
# OJO PARIDAD: el golden snapshot se congeló con k=1 -> re-congelar contra el
# modelo nuevo o los tests de demanda/safety-stock fallarán (esperado, no es bug).
WINSOR_K = 3.0
WINSOR_ESCALA_MAD = 1.4826

# Días hábiles por mes: divisor de la demanda diaria (hardcodeado en el DAX).
DIAS_HABILES_MES = 22

# --- Ciclo de orden y lead time -------------------------------------------------

CICLO_ORDEN_DIAS = 5          # compra directa al proveedor
CICLO_ORDEN_DIAS_CD = 3       # cuando la sucursal se abastece del CD
LT_FALLBACK_DIAS = 8          # sin proveedor o sin historial de OC

# --- Cálculo del lead time por proveedor desde el seguimiento (OC -> P/E) --------
# Réplica de las tablas 'Lead Time Proveedor' y 'Lead Time Proveedor Sucursal':
# por proveedor (y proveedor+sucursal) se toman los días OC->P/E de las OCs
# válidas, se descarta la cola con un percentil de corte (0.7 si predominan las
# OCs nacionales de reposición, 0.8 si no) y se promedian las que caen bajo el corte.
LT_TOPE_DIAS = 30             # nacionales/frontera: solo OCs con LT < 30 (importado sin tope)
LT_PCTIL_NAC = 0.7           # percentil de corte cuando nNac > nOtros
LT_PCTIL_OTROS = 0.8         # percentil de corte en caso contrario
ORIGEN_NACIONAL = "Curifor Nacional"
ORIGEN_IMPORTADO = "Curifor Importado"
SUCURSAL_DESCONOCIDA = "DESCONOCIDO"

# LT CD -> sucursal: por región (RM=1 día, resto=2), con casos especiales fijos.
LT_CD_RM = 1
LT_CD_RESTO = 2
LT_CD_ESPECIALES = {
    "TALCA (2)": 2,
    "DIEZ DE JULIO (2)": 1,
    "LINDEROS VTA MOVIL": 1,
}

# Lead time por proveedor: se excluyen las OCs con días > P90 del proveedor y se
# promedia el resto. Sin umbral mínimo de muestra (paridad con el modelo).
LT_PERCENTIL_OUTLIER = 0.90

# Tránsito: solo OC con estado Pendiente dentro de la ventana de vigencia.
TRANSITO_VENTANA_NACIONAL_DIAS = 30
TRANSITO_VENTANA_IMPORTADO_DIAS = 180

# Filtro base de motivo aplicado a Seguimiento de Compras en TODO el modelo:
# Origen <> "Curifor Nacional" OR Motivo == "reposicion" (SIEMPRE minúscula;
# en mayúscula devuelve cero en silencio — bug histórico documentado).
ORIGEN_CURIFOR_NACIONAL = "Curifor Nacional"
MOTIVO_REPOSICION = "reposicion"

# --- Safety stock ----------------------------------------------------------------

# Z por clase (hardcodeado en el DAX; el parámetro _NivelServicioZ NO se usa).
Z_POR_CLASE = {"A": 1.645, "B": 1.282, "C": 0.842, "D": 0.0}
# Importado abastecido por el CD usa Z reducido para A/B.
Z_IMPORTADO_CD = {"A": 1.282, "B": 1.036}


def z_para(clase: str, es_importado_cd: bool) -> float:
    if es_importado_cd and clase in Z_IMPORTADO_CD:
        return Z_IMPORTADO_CD[clase]
    return Z_POR_CLASE.get(clase, 0.0)


# --- Abastecimiento desde el CD (centralización parcial) -------------------------

# En sucursal normal: Abastece CD = "Si" cuando el producto es importado O cuando
# (clase local in {C,D} y clase agregada in {A,B}). En la fila del CD: "Si" solo
# si es importado. El sugerido directo solo calcula para clases A/B.
CLASES_QUE_COMPRAN = {"A", "B"}
CLASES_LOCAL_RUTEADAS_CD = {"C", "D"}
CLASES_AGG_QUE_CONSOLIDA_CD = {"A", "B"}

# Ranking de reparto del stock del CD (1 = primera en ser abastecida).
PRIORIDAD_CD = {
    "DIEZ DE JULIO (2)": 1,
    "BRASIL 18": 2,
    "LINDEROS": 3,
    "PLACILLA": 4,
    "RANCAGUA": 5,
    "RANCAGUA 2": 6,   # fusionada en RANCAGUA; se mantiene por paridad
    "CURICO": 7,
    "TALCA": 8,
    "TALCA (2)": 9,
    "CHILLAN": 10,
    "CHILLAN VIEJO": 11,
}
PRIORIDAD_CD_DEFAULT = 99

# Sucursales operativas de venta candidatas al traslado lateral, en el orden
# exacto de la medida "Traslado desde Otras Sucursales" (desempate estable).
SUCURSALES_OPERATIVAS = (
    "LINDEROS",
    "CURICO",
    "TALCA",
    "RANCAGUA",
    "DIEZ DE JULIO (2)",
    "CHILLAN",
    "BRASIL 18",
    "PLACILLA",
    "CHILLAN VIEJO",
    "TALCA (2)",
)

# --- Stock por bodega (columnas fijas del contrato de salida) --------------------

# Espejo de las columnas del modelo/plataforma: si se agrega una sucursal hay que
# tocar también models/sugerido.py, columnas.ts y excel_export.LABELS.
SUCURSALES_STOCK_COLUMNAS = {
    "LINDEROS": "stock_linderos",
    "CURICO": "stock_curico",
    "TALCA": "stock_talca",
    "RANCAGUA": "stock_rancagua",
    "DIEZ DE JULIO (2)": "stock_diez_de_julio_2",
    "CHILLAN": "stock_chillan",
    "CD REPUESTOS": "stock_cd_repuestos",
    "BRASIL 18": "stock_brasil_18",
    "PLACILLA": "stock_placilla",
    "CHILLAN VIEJO": "stock_chillan_viejo",
    "TALCA (2)": "stock_talca_2",
}
