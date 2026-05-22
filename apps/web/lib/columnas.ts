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
  { key: "prioridad_cd", label: "Prioridad CD", tipo: "numero", visiblePorDefecto: false },
  { key: "costo_unitario", label: "Costo Unitario", tipo: "clp", visiblePorDefecto: false },
  { key: "unidad_medida", label: "Unidad", tipo: "texto", visiblePorDefecto: false },
  { key: "pedir", label: "Pedir", tipo: "texto", visiblePorDefecto: false },
];

export const KEYS_POR_DEFECTO = COLUMNAS.filter((c) => c.visiblePorDefecto).map((c) => c.key as string);
