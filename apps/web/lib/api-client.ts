// Cliente del API. Centraliza las llamadas al backend FastAPI.
import { clearSession, getToken, setSession } from "./auth";
import type {
  AgrupadoRow,
  AuditoriaPage,
  CargaResultado,
  CarrosResponse,
  CatalogoDetalle,
  CatalogoFiltros,
  CatalogoOpciones,
  CatalogoPage,
  DimensionAgrupado,
  NotificacionesResponse,
  Producto,
  Sucursal,
  SugerenciaManual,
  SugeridoFiltros,
  SugeridoKpis,
  SugeridoPage,
  PostVentaFiltros,
  PostVentaMeta,
  Recurrente,
  RecurrenteCreate,
  VentasResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/** fetch con token, sin cache, y manejo de sesion expirada (401 -> login). */
async function req(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: { ...authHeaders(), ...(init.headers as Record<string, string> | undefined) },
  });
  if (
    res.status === 401 &&
    typeof window !== "undefined" &&
    !window.location.pathname.startsWith("/login")
  ) {
    clearSession();
    window.location.href = "/login";
  }
  return res;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await req(path);
  if (!res.ok) throw new Error(`Error ${res.status} en ${path}`);
  return res.json() as Promise<T>;
}

/** Construye los query params a partir de los filtros del dashboard. */
function filtrosToParams(f: SugeridoFiltros): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  (f.sucursales ?? []).forEach((s) => p.append("sucursal", s));
  (f.abc ?? []).forEach((s) => p.append("abc", s));
  (f.filtro1 ?? []).forEach((s) => p.append("filtro1", s));
  (f.tipo_origen ?? []).forEach((s) => p.append("tipo_origen", s));
  if (f.proveedor) p.set("proveedor", f.proveedor);
  p.set("solo_pedir", String(f.solo_pedir ?? true));
  if (f.solo_nacionales) p.set("solo_nacionales", "true");
  if (f.vista && f.vista !== "todas") p.set("vista", f.vista);
  return p;
}

async function descargar(path: string, body: unknown, fallbackNombre: string): Promise<void> {
  const res = await req(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("No se pudo generar el archivo");
  const blob = await res.blob();
  const dispo = res.headers.get("Content-Disposition") ?? "";
  const match = dispo.match(/filename="?([^"]+)"?/);
  const nombre = match?.[1] ?? fallbackNombre;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(url);
}

export const api = {
  baseUrl: BASE,

  /** Inicia sesion. No usa el wrapper (maneja el 401 como credencial incorrecta). */
  async login(email: string, password: string): Promise<void> {
    const res = await fetch(`${BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo iniciar sesión");
    }
    const data = await res.json();
    setSession(data.token, data.email, data.nombre ?? null, Boolean(data.es_admin));
  },

  async health(): Promise<{ status: string }> {
    return getJSON("/api/health");
  },

  async sugerido(
    f: SugeridoFiltros,
    opts: { page?: number; limit?: number; sort?: string } = {}
  ): Promise<SugeridoPage> {
    const p = filtrosToParams(f);
    p.set("page", String(opts.page ?? 1));
    p.set("limit", String(opts.limit ?? 1000));
    if (opts.sort) p.set("sort", opts.sort);
    return getJSON(`/api/sugerido?${p.toString()}`);
  },

  async kpis(f: SugeridoFiltros): Promise<SugeridoKpis> {
    return getJSON(`/api/sugerido/kpis?${filtrosToParams(f).toString()}`);
  },

  async agrupado(f: SugeridoFiltros, por: DimensionAgrupado): Promise<AgrupadoRow[]> {
    const p = filtrosToParams(f);
    p.set("por", por);
    return getJSON(`/api/sugerido/agrupado?${p.toString()}`);
  },

  async carros(f: SugeridoFiltros): Promise<CarrosResponse> {
    return getJSON(`/api/compras/carros?${filtrosToParams(f).toString()}`);
  },

  async exportOrden(f: SugeridoFiltros, proveedor?: string): Promise<void> {
    return descargar("/api/compras/export-excel", { filtros: f, proveedor: proveedor ?? null }, "orden_compra.xlsx");
  },

  async detalle(producto: string, sucursalId: string) {
    return getJSON(
      `/api/sugerido/${encodeURIComponent(producto)}/${encodeURIComponent(sucursalId)}`
    );
  },

  async ventas(producto: string, sucursalId: string): Promise<VentasResponse> {
    return getJSON(
      `/api/sugerido/${encodeURIComponent(producto)}/${encodeURIComponent(sucursalId)}/ventas`
    );
  },

  async sucursales(): Promise<Sucursal[]> {
    return getJSON("/api/sucursales");
  },

  async productos(q: string): Promise<{ items: Producto[] }> {
    return getJSON(`/api/productos?q=${encodeURIComponent(q)}&limit=20`);
  },

  async catalogo(
    f: CatalogoFiltros,
    opts: { page?: number; limit?: number; sort?: string } = {}
  ): Promise<CatalogoPage> {
    const p = new URLSearchParams();
    if (f.q) p.set("q", f.q);
    (f.familia ?? []).forEach((v) => p.append("familia", v));
    (f.procedencia ?? []).forEach((v) => p.append("procedencia", v));
    (f.categoria ?? []).forEach((v) => p.append("categoria", v));
    if (f.con_stock) p.set("con_stock", "true");
    p.set("page", String(opts.page ?? 1));
    p.set("limit", String(opts.limit ?? 1000));
    if (opts.sort) p.set("sort", opts.sort);
    return getJSON(`/api/catalogo?${p.toString()}`);
  },

  async catalogoFiltros(): Promise<CatalogoOpciones> {
    return getJSON("/api/catalogo/filtros");
  },

  async catalogoDetalle(producto: string): Promise<CatalogoDetalle> {
    return getJSON(`/api/catalogo/${encodeURIComponent(producto)}`);
  },

  async catalogoVentas(producto: string): Promise<VentasResponse> {
    return getJSON(`/api/catalogo/${encodeURIComponent(producto)}/ventas`);
  },

  async sugerenciasManuales(
    opts: { producto?: string; sucursalId?: string; soloUnicas?: boolean } = {}
  ): Promise<SugerenciaManual[]> {
    const p = new URLSearchParams();
    if (opts.producto) p.set("producto", opts.producto);
    if (opts.sucursalId) p.set("sucursal_id", opts.sucursalId);
    if (opts.soloUnicas) p.set("solo_unicas", "true");
    return getJSON(`/api/sugerencias-manuales?${p.toString()}`);
  },

  async crearSugerenciaManual(payload: {
    producto: string;
    sucursal_id: string;
    unidades?: number;
    dias_inventario?: number;
    expira_en?: string; // fecha límite YYYY-MM-DD; vacío = no vence
    motivo?: string;
  }): Promise<SugerenciaManual> {
    const res = await req("/api/sugerencias-manuales", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo guardar la sugerencia");
    }
    return res.json();
  },

  async crearSugerenciaMasiva(
    filtros: SugeridoFiltros,
    cantidad: { unidades?: number; dias_inventario?: number },
    motivo?: string,
    expiraEn?: string
  ): Promise<{ creadas: number; omitidas: number; lote_id: string | null }> {
    const res = await req("/api/sugerencias-manuales/masiva", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filtros, ...cantidad, expira_en: expiraEn, motivo }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo crear la carga masiva");
    }
    return res.json();
  },

  async crearRecurrente(payload: RecurrenteCreate): Promise<Recurrente> {
    const res = await req("/api/sugerencias-manuales/recurrentes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo crear la recurrencia");
    }
    return res.json();
  },

  async recurrentes(): Promise<Recurrente[]> {
    return getJSON("/api/sugerencias-manuales/recurrentes");
  },

  async eliminarRecurrente(id: string): Promise<void> {
    const res = await req(`/api/sugerencias-manuales/recurrentes/${id}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) throw new Error("No se pudo eliminar la recurrencia");
  },

  async contar(filtros: SugeridoFiltros): Promise<number> {
    const page = await this.sugerido(filtros, { limit: 1 });
    return page.total;
  },

  async eliminarSugerenciaManual(id: string): Promise<void> {
    const res = await req(`/api/sugerencias-manuales/${id}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) throw new Error("No se pudo eliminar");
  },

  async eliminarLoteSugerencias(loteId: string): Promise<{ eliminadas: number }> {
    const res = await req(`/api/sugerencias-manuales/lote/${encodeURIComponent(loteId)}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo eliminar la carga masiva");
    }
    return res.json();
  },

  async exportExcel(
    filtros: SugeridoFiltros,
    columnas: string[],
    sort?: string,
    ids?: number[]
  ): Promise<void> {
    return descargar(
      "/api/sugerido/export-excel",
      { filtros, columnas, sort, ids: ids && ids.length ? ids : null },
      "sugerido.xlsx"
    );
  },

  async powerbiEstado(): Promise<{ configurado: boolean }> {
    return getJSON("/api/admin/powerbi/estado");
  },

  async sincronizarPowerBI(): Promise<CargaResultado> {
    const res = await req("/api/admin/cargar-desde-powerbi", { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo sincronizar con Power BI");
    }
    return res.json();
  },

  async sincronizarPowerBIDesktop(): Promise<CargaResultado> {
    const res = await req("/api/admin/cargar-desde-powerbi-desktop", { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo leer Power BI Desktop");
    }
    return res.json();
  },

  async postVentaMeta(): Promise<PostVentaMeta> {
    return getJSON("/api/post-venta/meta");
  },

  async postVentaContar(f: PostVentaFiltros): Promise<number> {
    const p = new URLSearchParams();
    if (f.periodo_desde) p.set("periodo_desde", f.periodo_desde);
    if (f.periodo_hasta) p.set("periodo_hasta", f.periodo_hasta);
    if (f.fecha_desde) p.set("fecha_desde", f.fecha_desde);
    if (f.fecha_hasta) p.set("fecha_hasta", f.fecha_hasta);
    if (f.sucursal) p.set("sucursal", f.sucursal);
    const r = await getJSON<{ filas: number }>(`/api/post-venta/contar?${p.toString()}`);
    return r.filas;
  },

  async exportPostVenta(
    f: PostVentaFiltros,
    formato: "csv" | "xlsx" = "csv"
  ): Promise<void> {
    const endpoint = formato === "csv" ? "/api/post-venta/export-csv" : "/api/post-venta/export-excel";
    const res = await req(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(f),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo generar el archivo");
    }
    const blob = await res.blob();
    const dispo = res.headers.get("Content-Disposition") ?? "";
    const match = dispo.match(/filename="?([^"]+)"?/);
    const nombre =
      match?.[1] ??
      (formato === "csv" ? "planilla_post_venta.csv" : "planilla_post_venta.xlsx");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nombre;
    a.click();
    URL.revokeObjectURL(url);
  },

  async auditoria(limit = 100, offset = 0): Promise<AuditoriaPage> {
    return getJSON(`/api/auditoria?limit=${limit}&offset=${offset}`);
  },

  /** Accesos (login) — solo admin o emails autorizados en el backend. */
  async accesos(limit = 200, offset = 0): Promise<AuditoriaPage> {
    return getJSON(`/api/auditoria/accesos?limit=${limit}&offset=${offset}`);
  },

  async notificaciones(soloNoLeidas = false, limit = 20): Promise<NotificacionesResponse> {
    return getJSON(
      `/api/notificaciones?solo_no_leidas=${soloNoLeidas}&limit=${limit}`
    );
  },

  async ventasKpis(): Promise<import("./types").VentasKpis> {
    return getJSON("/api/ventas/kpis");
  },

  async ventasMensual(meses = 12): Promise<import("./types").VentasMes[]> {
    return getJSON(`/api/ventas/mensual?meses=${meses}`);
  },

  async ventasPorSucursal(periodo?: string): Promise<import("./types").VentasPorSucursal> {
    const q = periodo ? `?periodo=${encodeURIComponent(periodo)}` : "";
    return getJSON(`/api/ventas/por-sucursal${q}`);
  },

  async ventasLineas(
    f: import("./types").VentasLineasFiltros,
    opts: { page?: number; limit?: number } = {}
  ): Promise<import("./types").VentasLineasPage> {
    const p = new URLSearchParams();
    if (f.periodo_desde) p.set("periodo_desde", f.periodo_desde);
    if (f.periodo_hasta) p.set("periodo_hasta", f.periodo_hasta);
    if (f.fecha_desde) p.set("fecha_desde", f.fecha_desde);
    if (f.fecha_hasta) p.set("fecha_hasta", f.fecha_hasta);
    if (f.sucursal) p.set("sucursal", f.sucursal);
    if (f.q) p.set("q", f.q);
    p.set("page", String(opts.page ?? 1));
    p.set("limit", String(opts.limit ?? 500));
    return getJSON(`/api/ventas/lineas?${p.toString()}`);
  },

  async ultimaSincronizacion(): Promise<{ creado_en: string | null; detalle: string | null }> {
    return getJSON("/api/ultima-sincronizacion");
  },

  async marcarLeidas(ids?: string[]): Promise<{ actualizadas: number }> {
    const res = await req("/api/notificaciones/marcar-leidas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: ids ?? null }),
    });
    if (!res.ok) throw new Error("No se pudo marcar como leida");
    return res.json();
  },

  async cargarSugerido(file: File): Promise<CargaResultado> {
    const fd = new FormData();
    fd.append("file", file);
    const res = await req("/api/admin/cargar-sugerido", { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo cargar el archivo");
    }
    return res.json();
  },

  async chat(
    pregunta: string,
    historial: { role: "user" | "model"; text: string }[] = []
  ): Promise<{ respuesta: string }> {
    const res = await req("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta, historial }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "El asistente no respondio");
    }
    return res.json();
  },
};
