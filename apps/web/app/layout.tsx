import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Sugerido de Compras",
  description: "Plataforma de sugerido de reposicion de inventario — Curifor S.A.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es-CL" className={`${plexSans.variable} ${plexMono.variable}`}>
      <body className="min-h-screen font-sans">
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-3 px-4">
            <Link href="/" className="flex items-center gap-2.5">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/curifor-logo.png"
                alt="Curifor"
                className="h-6 w-auto"
              />
              <span className="hidden h-5 w-px bg-slate-200 sm:block" />
              <span className="hidden text-[15px] font-semibold tracking-tight text-slate-900 sm:inline">
                Sugerido de Compras
              </span>
            </Link>
            <nav className="ml-auto flex items-center gap-1 text-sm">
              <Link
                href="/"
                className="rounded-md px-3 py-1.5 text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              >
                Dashboard
              </Link>
              <Link
                href="/cargar"
                className="rounded-md px-3 py-1.5 text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              >
                Cargar datos
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-[1600px] px-4 py-5">{children}</main>
      </body>
    </html>
  );
}
