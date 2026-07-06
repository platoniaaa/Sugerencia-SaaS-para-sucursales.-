// Definicion central de las columnas del sugerido: etiqueta, tipo y si se ven por defecto.
import type { SugeridoRow } from "./types";

export type TipoColumna = "texto" | "numero" | "decimal" | "clp" | "abc";

export interface DefColumna {
  key: keyof SugeridoRow;
  label: string;
  tipo: TipoColumna;
  visiblePorDefecto: boolean;
  pin?: "left" | "right";
}

export const COLUMNAS: DefColumna[] = [
  { key: "producto", label: "Producto", tipo: "texto", visiblePorDefecto: true, pin: "left" },
  { key: "descripcion", label: "Descripcion", tipo: "texto", visiblePorDefecto: true, pin: "left" },
  { key: "clasificacion_abc", label: "ABC", tipo: "abc", visiblePorDefecto: true },
  { key: "nombre_sucursal", label: "Sucursal", tipo: "texto", visiblePorDefecto: true },
  { key: "total_sugerido_suc", label: "Total Sugerido", tipo: "numero", visiblePorDefecto: true, pin: "right" },
  // Ocultas por defecto:
  { key: "empresa", label: "Empresa", tipo: "texto", visiblePorDefecto: false },
  { key: "proveedor", label: "Proveedor", tipo: "texto", visiblePorDefecto: false },
  { key: "filtro1_final", label: "Marca", tipo: "texto", visiblePorDefecto: false },
  { key: "tipo_origen", label: "Tipo Origen", tipo: "texto", visiblePorDefecto: false },
  { key: "total_valor_sugerido_clp", label: "Valor Total CLP", tipo: "clp", visiblePorDefecto: false },
  { key: "sugerido_traslado", label: "Sug. Traslado", tipo: "numero", visiblePorDefecto: false },
  { key: "sugerido_compra_neto", label: "Sug. Compra Neto", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_activo_suc", label: "Stock Activo", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_en_transito_suc", label: "Stock Transito", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_en_cd", label: "Stock CD", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_seguridad", label: "Stock Seguridad", tipo: "numero", visiblePorDefecto: false },
  { key: "punto_de_pedido", label: "Punto de Pedido", tipo: "numero", visiblePorDefecto: false },
  { key: "demanda_mensual", label: "Demanda Mensual", tipo: "decimal", visiblePorDefecto: false },
  { key: "demanda_diaria", label: "Demanda Diaria", tipo: "decimal", visiblePorDefecto: false },
  { key: "desv_std_mensual", label: "Desv Std Mensual", tipo: "decimal", visiblePorDefecto: false },
  { key: "lead_time_dias", label: "Lead Time (dias)", tipo: "numero", visiblePorDefecto: false },
  { key: "lt_efectivo", label: "LT Efectivo", tipo: "numero", visiblePorDefecto: false },
  { key: "abastece_cd", label: "Abastece CD", tipo: "texto", visiblePorDefecto: false },
  { key: "comprar_en_el_cd", label: "¿Comprar en CD?", tipo: "texto", visiblePorDefecto: false },
  { key: "prioridad_cd", label: "Prioridad CD", tipo: "numero", visiblePorDefecto: false },
  { key: "costo_unitario", label: "Costo Unitario", tipo: "clp", visiblePorDefecto: false },
  { key: "unidad_medida", label: "Unidad", tipo: "texto", visiblePorDefecto: false },
  { key: "pedir", label: "Pedir", tipo: "texto", visiblePorDefecto: false },
  { key: "reemplazos", label: "Reemplazos", tipo: "texto", visiblePorDefecto: false },
  { key: "trasladar_desde", label: "Trasladar desde", tipo: "texto", visiblePorDefecto: false },
  // Stock por bodega/sucursal (espejo de las columnas del BI; incluye grupo de reemplazo).
  { key: "stock_linderos", label: "Stock Linderos", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_curico", label: "Stock Curico", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_talca", label: "Stock Talca", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_rancagua", label: "Stock Rancagua", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_diez_de_julio_2", label: "Stock Diez de Julio (2)", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_chillan", label: "Stock Chillan", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_cd_repuestos", label: "Stock CD Repuestos", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_brasil_18", label: "Stock Brasil 18", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_placilla", label: "Stock Placilla", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_chillan_viejo", label: "Stock Chillan Viejo", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_talca_2", label: "Stock Talca (2)", tipo: "numero", visiblePorDefecto: false },
];

export const KEYS_POR_DEFECTO = COLUMNAS.filter((c) => c.visiblePorDefecto).map((c) => c.key as string);

// Columnas por defecto de la vista "distribucion" (traslado CD -> sucursales).
// Prioriza el set operativo del jefe de compras: cuanto trasladar, stock del CD,
// lo que aun hay que comprar y si el CD debe comprarlo (el "Total Sugerido" se
// omite porque estas filas lo traen en cero: la sucursal se abastece via CD).
const COLS_DISTRIBUCION = [
  "producto", "descripcion", "clasificacion_abc", "nombre_sucursal",
  "sugerido_traslado", "stock_en_cd", "sugerido_compra_neto",
  "comprar_en_el_cd", "prioridad_cd",
];

// Set de columnas por defecto segun la vista del proceso de compras.
export function columnasPorDefectoVista(vista: string): string[] {
  return vista === "distribucion" ? COLS_DISTRIBUCION : KEYS_POR_DEFECTO;
}
