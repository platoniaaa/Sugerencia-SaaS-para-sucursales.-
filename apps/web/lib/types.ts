// Tipos compartidos con el backend (espejo de los schemas Pydantic).

export interface SugeridoRow {
  id: number;
  producto: string;
  descripcion: string | null;
  sucursal_id: string;
  nombre_sucursal: string | null;
  clasificacion_abc: string | null;
  proveedor: string | null;
  filtro1_final: string | null;
  tipo_origen: string | null;
  es_importado: boolean | null;
  unidad_medida: string | null;
  lead_time_dias: number | null;
  lt_efectivo: number | null;
  lt_cd_a_sucursal_dias: number | null;
  lt_origen: string | null;
  abastece_cd: string | null;
  prioridad_cd: number | null;
  comprar_en_el_cd: string | null;
  tiene_stock_cd: boolean | null;
  demanda_mensual: number | null;
  demanda_diaria: number | null;
  desv_std_mensual: number | null;
  stock_seguridad: number | null;
  punto_de_pedido: number | null;
  costo_unitario: number | null;
  pedir: string | null;
  reemplazos: string | null;
  sugerido_suc: number | null;
  stock_activo_suc: number | null;
  stock_en_transito_suc: number | null;
  stock_en_cd: number | null;
  sugerido_traslado: number | null;
  sugerido_compra_neto: number | null;
  total_sugerido_suc: number | null;
  total_valor_sugerido_clp: number | null;
  pedir_flag: string | null;
}

export interface SugeridoPage {
  items: SugeridoRow[];
  total: number;
  page: number;
  limit: number;
}

export interface SugeridoKpis {
  total_sugerido: number;
  valor_total_clp: number;
  n_productos: number;
  n_proveedores: number;
}

export interface AgrupadoRow {
  grupo: string;
  total_sugerido: number;
  valor_clp: number;
  n_productos: number;
}

export type DimensionAgrupado = "sucursal" | "marca" | "proveedor";

export interface VentaMes {
  mes: string; // YYYYMM
  cantidad: number;
}

export interface VentasResponse {
  producto: string;
  sucursal_id: string;
  meses: VentaMes[];
  total: number;
}

export interface SugeridoFiltros {
  q?: string;
  sucursales?: string[];
  abc?: string[];
  filtro1?: string[];
  tipo_origen?: string[];
  proveedor?: string;
  solo_pedir?: boolean;
}

export interface Sucursal {
  sucursal_id: string;
  nombre: string | null;
  region: string | null;
  abastece_desde_cd: string | null;
  prioridad_cd: number | null;
}

export interface Producto {
  producto: string;
  descripcion: string | null;
  filtro1_final: string | null;
  unidad_medida: string | null;
  costo_unitario: number | null;
  proveedor: string | null;
  es_importado: boolean | null;
}

export interface SugerenciaManual {
  id: string;
  producto: string;
  sucursal_id: string;
  unidades: number;
  motivo: string | null;
  creado_por: string | null;
  creado_en: string;
  aprobado: boolean;
  usado_en_compra: boolean;
}

export interface LineaCarro {
  producto: string;
  descripcion: string | null;
  clasificacion_abc: string | null;
  cantidad: number;
  costo_unitario: number | null;
  subtotal_clp: number;
}

export interface CarroProveedor {
  proveedor: string;
  n_productos: number;
  total_unidades: number;
  total_clp: number;
  lineas: LineaCarro[];
}

export interface CarrosResponse {
  carros: CarroProveedor[];
  total_proveedores: number;
  total_clp: number;
  total_unidades: number;
}

export interface CargaResultado {
  filas_cargadas: number;
  productos: number;
  sucursales: number;
  columnas_detectadas: string[];
  advertencias: string[];
}
