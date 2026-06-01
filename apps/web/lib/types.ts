// Tipos compartidos con el backend (espejo de los schemas Pydantic).

export interface SugeridoRow {
  id: number;
  origen?: "sugerido" | "catalogo" | "manual";
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
  meses_general: VentaMes[];
  meses_sucursal: VentaMes[];
  total_general: number;
  total_sucursal: number;
}

export interface SugeridoFiltros {
  q?: string;
  sucursales?: string[];
  abc?: string[];
  filtro1?: string[];
  tipo_origen?: string[];
  proveedor?: string;
  solo_pedir?: boolean;
  solo_abastece_cd?: boolean;
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

export interface RecurrenteCreate {
  modo: "individual" | "grupo";
  producto?: string | null;
  sucursal_id?: string | null;
  filtros?: SugeridoFiltros | null;
  unidades?: number | null;
  dias_inventario?: number | null;
  motivo?: string | null;
  cada_dias: number;
  fecha_fin?: string | null; // YYYY-MM-DD
}

export interface Recurrente {
  id: string;
  modo: string;
  resumen: string;
  unidades: number;
  dias_inventario: number | null;
  motivo: string | null;
  cada_dias: number;
  proxima_ejecucion: string;
  fecha_fin: string | null;
  activa: boolean;
  ultima_ejecucion: string | null;
}

export interface CatalogoRow {
  id: number;
  producto: string;
  glosa: string | null;
  familia: string | null;
  subfamilia: string | null;
  procedencia: string | null;
  tipo_repuesto: string | null;
  categoria: string | null;
  sub_categoria: string | null;
  tipo_producto: string | null;
  clasificacion_stock: string | null;
  costo: number | null;
  precio: number | null;
  stock_total: number | null;
  stock_minimo: number | null;
  stock_maximo: number | null;
  sub_modelo: string | null;
  cilindrada: string | null;
  combustible: string | null;
  anio: string | null;
  unidad: string | null;
  reemplazo: string | null;
}

export interface CatalogoPage {
  items: CatalogoRow[];
  total: number;
  page: number;
  limit: number;
}

export interface CatalogoFiltros {
  q?: string;
  familia?: string[];
  procedencia?: string[];
  categoria?: string[];
  con_stock?: boolean;
}

export interface CatalogoOpciones {
  familias: string[];
  procedencias: string[];
  categorias: string[];
}

export interface StockSucursalRow {
  bodega: string | null;
  sucursal_id: string | null;
  stock: number;
  origen: string | null;
}

export interface CatalogoDetalle extends CatalogoRow {
  stock_por_sucursal: StockSucursalRow[];
}

export interface PostVentaMeta {
  columnas: string[];
  filas: number;
  periodos: string[];
  sucursales: string[];
  actualizado_en: string | null;
}

export interface PostVentaFiltros {
  periodo_desde?: string | null;
  periodo_hasta?: string | null;
  sucursal?: string | null;
}

export interface CargaResultado {
  filas_cargadas: number;
  productos: number;
  sucursales: number;
  columnas_detectadas: string[];
  advertencias: string[];
}
