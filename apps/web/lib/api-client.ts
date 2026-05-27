// Cliente del API. Centraliza las llamadas al backend FastAPI.
import { clearSession, getToken, setSession } from "./auth";
import type {
  AgrupadoRow,
  CargaResultado,
  CarrosResponse,
  DimensionAgrupado,
  Producto,
  Sucursal,
  SugerenciaManual,
  SugeridoFiltros,
  SugeridoKpis,
  SugeridoPage,
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
    setSession(data.token, data.email, data.nombre ?? null);
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

  async sucursales(): Promise<Sucursal[]> {
    return getJSON("/api/sucursales");
  },

  async productos(q: string): Promise<{ items: Producto[] }> {
    return getJSON(`/api/productos?q=${encodeURIComponent(q)}&limit=20`);
  },

  async sugerenciasManuales(producto?: string, sucursalId?: string): Promise<SugerenciaManual[]> {
    const p = new URLSearchParams();
    if (producto) p.set("producto", producto);
    if (sucursalId) p.set("sucursal_id", sucursalId);
    return getJSON(`/api/sugerencias-manuales?${p.toString()}`);
  },

  async crearSugerenciaManual(payload: {
    producto: string;
    sucursal_id: string;
    unidades: number;
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
    unidades: number,
    motivo?: string
  ): Promise<{ creadas: number }> {
    const res = await req("/api/sugerencias-manuales/masiva", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filtros, unidades, motivo }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo crear la carga masiva");
    }
    return res.json();
  },

  async contar(filtros: SugeridoFiltros): Promise<number> {
    const page = await this.sugerido(filtros, { limit: 1 });
    return page.total;
  },

  async eliminarSugerenciaManual(id: string): Promise<void> {
    const res = await req(`/api/sugerencias-manuales/${id}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) throw new Error("No se pudo eliminar");
  },

  async exportExcel(filtros: SugeridoFiltros, columnas: string[], sort?: string): Promise<void> {
    return descargar("/api/sugerido/export-excel", { filtros, columnas, sort }, "sugerido.xlsx");
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
};
