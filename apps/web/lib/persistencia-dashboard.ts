// Helpers de persistencia para el dashboard del sugerido.
//
// Decisiones:
// - localStorage con namespace por email: dos usuarios que comparten el mismo
//   navegador no ven los filtros del otro.
// - Sufijo de version (`v1`): si en el futuro cambia el shape, bumpear y olvidar
//   los datos viejos sin romper el cliente.
// - Cap de 100 KB por clave: el filter model de AG Grid puede crecer si el
//   usuario pega 5.000 SKUs en el multi-select. Encima de ese tope no
//   guardamos, para no bloquear el main thread.

import { getEmail } from "./auth";

const PREFIJO = "sugerido_";
const VERSION = "v1";
const CAP_BYTES = 100_000;

export const STORAGE_KEYS = {
  filtros: "filtros",
  gridFilter: "grid_filter",
  gridCols: "grid_cols",
  gridPage: "grid_page",
} as const;

function nsKey(nombre: string): string {
  const email = (typeof window !== "undefined" && getEmail()) || "anon";
  return `${PREFIJO}${nombre}_${VERSION}_${email}`;
}

export function leer<T>(nombre: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(nsKey(nombre));
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    if (parsed === null || parsed === undefined) return fallback;
    return parsed as T;
  } catch {
    return fallback;
  }
}

export function guardar<T>(nombre: string, valor: T): void {
  if (typeof window === "undefined") return;
  try {
    const json = JSON.stringify(valor);
    // Cap para no bloquear el main thread con un payload gigante.
    if (json.length > CAP_BYTES) return;
    localStorage.setItem(nsKey(nombre), json);
  } catch {
    // Quota exceeded u otro error de storage: ignorar silenciosamente.
  }
}

export function eliminar(nombre: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(nsKey(nombre));
  } catch {
    /* noop */
  }
}
