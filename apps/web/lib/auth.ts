// Manejo de sesion del lado del cliente (token en localStorage).

const TOKEN = "sugerido_token";
const EMAIL = "sugerido_email";
const NOMBRE = "sugerido_nombre";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN);
}

export function getEmail(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(EMAIL);
}

export function getNombre(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(NOMBRE);
}

export function setSession(token: string, email: string, nombre: string | null) {
  localStorage.setItem(TOKEN, token);
  localStorage.setItem(EMAIL, email);
  if (nombre) localStorage.setItem(NOMBRE, nombre);
  else localStorage.removeItem(NOMBRE);
}

export function clearSession() {
  localStorage.removeItem(TOKEN);
  localStorage.removeItem(EMAIL);
  localStorage.removeItem(NOMBRE);
}

export function estaAutenticado(): boolean {
  return !!getToken();
}

/** Cierra sesion y manda al login. */
export function logout() {
  clearSession();
  if (typeof window !== "undefined") window.location.href = "/login";
}
