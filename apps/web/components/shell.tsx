"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { estaAutenticado, getEmail, getEsAdmin, getNombre, logout } from "@/lib/auth";
import { CampanitaNotificaciones } from "@/components/campanita-notificaciones";

type NavItem = { href: string; label: string; soloAdmin?: boolean };
const NAV: NavItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/compras", label: "Compras" },
  { href: "/catalogo", label: "Catálogo" },
  { href: "/sugerencias-manuales", label: "Sugerencias manuales" },
  { href: "/auditoria", label: "Auditoría" },
  { href: "/exportar", label: "Exportar" },
  { href: "/cargar", label: "Cargar datos", soloAdmin: true },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const esLogin = pathname === "/login";
  const [listo, setListo] = useState(false);

  useEffect(() => {
    if (!esLogin && !estaAutenticado()) {
      router.replace("/login");
      return;
    }
    setListo(true);
  }, [esLogin, pathname, router]);

  // La pantalla de login se muestra sin header.
  if (esLogin) {
    return <main className="mx-auto max-w-[1600px] px-4 py-5">{children}</main>;
  }

  // Evita mostrar contenido protegido antes de verificar la sesion.
  if (!listo) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-400">
        Cargando…
      </div>
    );
  }

  const email = getEmail();
  const nombre = getNombre();
  const esAdmin = getEsAdmin();
  const navVisible = NAV.filter((n) => !n.soloAdmin || esAdmin);

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-3 px-4">
          <Link href="/" className="flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/curifor-logo.png" alt="Curifor" className="h-6 w-auto" />
            <span className="hidden h-5 w-px bg-slate-200 sm:block" />
            <span className="hidden text-[15px] font-semibold tracking-tight text-slate-900 sm:inline">
              Sugerido de Compras
            </span>
          </Link>
          <nav className="ml-auto flex items-center gap-1 text-sm">
            {navVisible.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`rounded-md px-3 py-1.5 hover:bg-slate-100 hover:text-slate-900 ${
                  pathname === n.href ? "text-slate-900 font-medium" : "text-slate-600"
                }`}
              >
                {n.label}
              </Link>
            ))}
            <div className="ml-2 flex items-center gap-2 border-l border-slate-200 pl-3">
              <CampanitaNotificaciones />
              <span className="hidden text-[13px] text-slate-500 md:inline">
                {nombre ?? email}
              </span>
              <button
                onClick={logout}
                title="Cerrar sesión"
                className="flex items-center gap-1 rounded-md px-2 py-1.5 text-[13px] text-slate-500 hover:bg-slate-100 hover:text-slate-900"
              >
                <LogOut size={15} /> Salir
              </button>
            </div>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] px-4 py-5">{children}</main>
    </>
  );
}
