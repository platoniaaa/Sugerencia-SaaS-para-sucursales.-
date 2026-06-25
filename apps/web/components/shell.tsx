"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu } from "lucide-react";
import { estaAutenticado, getEmail, getNombre, logout } from "@/lib/auth";
import { CampanitaNotificaciones } from "@/components/campanita-notificaciones";
import { ChatBot } from "@/components/chat-bot";
import { Sidebar } from "@/components/sidebar";

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const esLogin = pathname === "/login";
  const [listo, setListo] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!esLogin && !estaAutenticado()) {
      router.replace("/login");
      return;
    }
    setListo(true);
  }, [esLogin, pathname, router]);

  // Cerrar sidebar al cambiar de ruta.
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  // La pantalla de login se muestra sin header.
  if (esLogin) {
    return (
      <main className="relative z-10 mx-auto max-w-[1600px] px-4 py-5">{children}</main>
    );
  }

  if (!listo) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-ink-400">
        Cargando…
      </div>
    );
  }

  const email = getEmail();
  const nombre = getNombre();

  return (
    <>
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <header className="sticky top-0 z-30 border-b border-ink-200 bg-paper/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-3 px-4">
          <button
            onClick={() => setSidebarOpen(true)}
            className="flex h-9 w-9 items-center justify-center rounded-sm text-ink-700 transition-colors hover:bg-ink-100"
            aria-label="Abrir menú"
          >
            <Menu size={20} />
          </button>

          <Link href="/" className="flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/curifor-logo.png" alt="Curifor" className="h-7 w-auto" />
            <span className="hidden h-5 w-px bg-ink-300 sm:block" />
            <span className="hidden flex-col sm:flex">
              <span className="font-display text-[17px] font-medium leading-none tracking-tight text-ink-900">
                Sugerido
              </span>
              <span className="mt-0.5 text-[10px] uppercase tracking-[0.14em] text-ink-500">
                de compras
              </span>
            </span>
          </Link>

          <div className="ml-auto flex items-center gap-2">
            <CampanitaNotificaciones />
            <span className="hidden text-[13px] text-ink-600 md:inline">
              {nombre ?? email}
            </span>
            <button
              onClick={logout}
              title="Cerrar sesión"
              className="flex items-center gap-1 rounded-sm px-2 py-1.5 text-[13px] text-ink-500 transition-colors hover:bg-ink-100 hover:text-ink-900"
            >
              <LogOut size={15} />{" "}
              <span className="hidden sm:inline">Salir</span>
            </button>
          </div>
        </div>
      </header>

      <main className="relative z-10 mx-auto max-w-[1600px] px-4 py-6">{children}</main>
      <ChatBot />
    </>
  );
}
