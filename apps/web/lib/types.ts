// Tipos compartidos con el backend (espejo de los schemas Pydantic).

export interface SugeridoRow {
  id: number;
  origen?: "sugerido" | "catalogo" | "manual";
  producto: string;
  descripcion: string | null;
  sucursal_id: string;
  nombre_sucursal: string | null;
  empresa: string | null;
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
  trasladar_desde: string | null;
  // Stock por bodega/sucursal (espejo de las columnas del BI).
  stock_linderos: number | null;
  stock_curico: number | null;
  stock_talca: number | null;
  stock_rancagua: number | null;
  stock_diez_de_julio_2: number | null;
  stock_chillan: number | null;
  stock_cd_repuestos: number | null;
  stock_brasil_18: number | null;
  stock_placilla: number | null;
  stock_chillan_viejo: number | null;
  stock_talca_2: number | null;
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
  /** Busqueda parcial por nombre de proveedor (legacy, ILIKE %valor%). */
  proveedor?: string;
  /** Multi-seleccion exacta de proveedores (modal sugerencia manual). */
  proveedores?: string[];
  solo_pedir?: boolean;
  solo_nacionales?: boolean;
  vista?: "todas" | "sucursales" | "cd" | "distribucion";
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
  /** UUID compartido por las filas de una misma carga masiva. */
  lote_id?: string | null;
  /** Fecha (ISO) en que se archiva automáticamente. null = no vence. */
  expira_en?: string | null;
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
  fecha_desde?: string | null;  // YYYY-MM-DD
  fecha_hasta?: string | null;  // YYYY-MM-DD
  sucursal?: string | null;
}

export interface CargaResultado {
  filas_cargadas: number;
  productos: number;
  sucursales: number;
  columnas_detectadas: string[];
  advertencias: string[];
}

export interface AuditoriaLog {
  id: string;
  accion: string;
  entidad: string;
  entidad_id: string | null;
  usuario_email: string | null;
  producto: string | null;
  sucursal_id: string | null;
  unidades: number | null;
  dias_inventario: number | null;
  motivo: string | null;
  detalle: string | null;
  creado_en: string;
}

export interface AuditoriaPage {
  items: AuditoriaLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface Notificacion {
  id: string;
  tipo: string;
  titulo: string;
  mensaje: string | null;
  creado_por_email: string | null;
  producto: string | null;
  sucursal_id: string | null;
  creado_en: string;
  leida: boolean;
}

export interface NotificacionesResponse {
  items: Notificacion[];
  no_leidas: number;
}

export interface VentasKpis {
  periodo_actual: string | null;
  periodo_anterior: string | null;
  actual: { clp: number; unidades: number; n_lineas: number };
  anterior: { clp: number; unidades: number; n_lineas: number };
  var_clp_pct: number | null;
  var_unidades_pct: number | null;
}

export interface VentasMes {
  periodo: string;
  clp: number;
  unidades: number;
}

export interface VentasSucursalRow {
  sucursal: string;
  clp: number;
  unidades: number;
  n_lineas: number;
}

export interface VentasPorSucursal {
  periodo: string | null;
  items: VentasSucursalRow[];
}

export interface VentaLinea {
  _id: number;
  [columna: string]: string | number | null;
}

export interface VentasLineasPage {
  items: VentaLinea[];
  total: number;
  page: number;
  limit: number;
  columnas: string[];
}

export interface VentasLineasFiltros {
  periodo_desde?: string;
  periodo_hasta?: string;
  fecha_desde?: string;  // YYYY-MM-DD
  fecha_hasta?: string;  // YYYY-MM-DD
  sucursal?: string;
  q?: string;
}
