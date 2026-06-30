"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Bell,
  BookOpen,
  ClipboardList,
  Database,
  FileText,
  LineChart,
  LogOut,
  ShoppingCart,
  Sigma,
  X,
} from "lucide-react";
import { getEmail, getEsAdmin, getNombre, logout } from "@/lib/auth";

type NavItem = {
  href: string;
  label: string;
  icon: typeof BarChart3;
  soloAdmin?: boolean;
};

const NAV: NavItem[] = [
  { href: "/", label: "Sugerido", icon: BarChart3 },
  { href: "/compras", label: "Compras", icon: ShoppingCart },
  { href: "/catalogo", label: "Catálogo", icon: BookOpen },
  { href: "/sugerencias-manuales", label: "Sugerencias", icon: ClipboardList },
  { href: "/ventas", label: "Ventas", icon: LineChart },
  { href: "/auditoria", label: "Auditoría", icon: FileText },
  { href: "/modelo", label: "Modelo", icon: Sigma },
  { href: "/cargar", label: "Cargar datos", icon: Database, soloAdmin: true },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: Props) {
  const pathname = usePathname();
  const email = getEmail();
  const nombre = getNombre();
  const esAdmin = getEsAdmin();
  const items = NAV.filter((n) => !n.soloAdmin || esAdmin);

  // Cerrar con ESC.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Bloquear scroll del body cuando esta abierta.
  useEffect(() => {
    if (open) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [open]);

  return (
    <>
      {/* Overlay oscuro */}
      <div
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-ink-900/50 backdrop-blur-sm transition-opacity duration-300 ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        aria-hidden="true"
      />

      {/* Drawer */}
      <aside
        className={`fixed left-0 top-0 z-50 flex h-full w-[280px] flex-col bg-brand text-paper shadow-2xl transition-transform duration-300 ease-out ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-hidden={!open}
      >
        {/* Header del drawer */}
        <div className="flex items-center justify-between border-b border-brand-700/60 px-5 py-4">
          <div className="flex flex-col">
            <span className="font-display text-[19px] font-medium leading-none tracking-tight text-paper">
              Sugerido
            </span>
            <span className="mt-1 text-[10px] uppercase tracking-[0.16em] text-brand-200">
              de compras
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-sm p-1.5 text-brand-200 transition-colors hover:bg-brand-700 hover:text-paper"
            aria-label="Cerrar menú"
          >
            <X size={18} />
          </button>
        </div>

        {/* Navegacion */}
        <nav className="flex-1 overflow-y-auto py-4">
          <p className="kicker !text-brand-200 mb-2 px-5">Menú</p>
          <ul className="space-y-px">
            {items.map((n) => {
              const Icon = n.icon;
              const activo = pathname === n.href;
              return (
                <li key={n.href}>
                  <Link
                    href={n.href}
                    onClick={onClose}
                    className={`group relative flex items-center gap-3 px-5 py-2.5 text-[14px] transition-colors ${
                      activo
                        ? "bg-brand-900 font-semibold text-paper"
                        : "text-brand-100 hover:bg-brand-700 hover:text-paper"
                    }`}
                  >
                    {/* Linea clay a la izquierda cuando esta activo */}
                    <span
                      className={`absolute left-0 top-0 h-full w-[3px] transition-all ${
                        activo ? "bg-accent-500" : "bg-transparent"
                      }`}
                    />
                    <Icon
                      size={17}
                      className={
                        activo ? "text-accent-500" : "text-brand-200 group-hover:text-paper"
                      }
                    />
                    <span>{n.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Footer del drawer: usuario + salir */}
        <div className="border-t border-brand-700/60 px-5 py-4">
          <div className="mb-3">
            <p className="kicker !text-brand-200">Sesión</p>
            <p className="mt-1 truncate text-[13px] font-medium text-paper">
              {nombre ?? email}
            </p>
            {nombre && email && (
              <p className="truncate text-[11px] text-brand-200">{email}</p>
            )}
          </div>
          <button
            onClick={logout}
            className="flex w-full items-center justify-between rounded-sm border border-brand-700/60 px-3 py-2 text-[13px] text-paper transition-colors hover:border-accent-500 hover:bg-brand-700"
          >
            <span className="flex items-center gap-2">
              <LogOut size={14} /> Cerrar sesión
            </span>
          </button>
        </div>
      </aside>
    </>
  );
}
