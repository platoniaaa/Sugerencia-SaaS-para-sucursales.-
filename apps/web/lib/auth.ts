// Manejo de sesion del lado del cliente (token en localStorage).

const TOKEN = "sugerido_token";
const EMAIL = "sugerido_email";
const NOMBRE = "sugerido_nombre";
const ES_ADMIN = "sugerido_es_admin";

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

export function getEsAdmin(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(ES_ADMIN) === "1";
}

export function setSession(
  token: string, email: string, nombre: string | null, esAdmin = false
) {
  localStorage.setItem(TOKEN, token);
  localStorage.setItem(EMAIL, email);
  if (nombre) localStorage.setItem(NOMBRE, nombre);
  else localStorage.removeItem(NOMBRE);
  localStorage.setItem(ES_ADMIN, esAdmin ? "1" : "0");
}

export function clearSession() {
  localStorage.removeItem(TOKEN);
  localStorage.removeItem(EMAIL);
  localStorage.removeItem(NOMBRE);
  localStorage.removeItem(ES_ADMIN);
}

export function estaAutenticado(): boolean {
  return !!getToken();
}

// Emails no-admin que pueden ver la pestana "Accesos" de auditoria. El backend es el
// gate real (403); esto solo decide si mostrar la pestana. Mantener en sync con
// EMAILS_VER_ACCESOS del backend (config.emails_ver_accesos).
const EMAILS_VER_ACCESOS = ["mramos@curifor.com"];

/** True si el usuario puede ver la vista de accesos (admin o email autorizado). */
export function puedeVerAccesos(): boolean {
  if (getEsAdmin()) return true;
  const email = getEmail()?.toLowerCase();
  return !!email && EMAILS_VER_ACCESOS.includes(email);
}

/** Cierra sesion y manda al login. */
export function logout() {
  clearSession();
  if (typeof window !== "undefined") window.location.href = "/login";
}
