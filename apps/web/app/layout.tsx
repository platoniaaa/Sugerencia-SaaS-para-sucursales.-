import type { Metadata } from "next";
import { Fraunces, Inter_Tight, JetBrains_Mono } from "next/font/google";
import { Shell } from "@/components/shell";
import "./globals.css";

// Display serif con caracter editorial — uso para titulos y numeros grandes.
const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

// Sans con personalidad para UI, mas geometrico que Inter neutro.
const interTight = Inter_Tight({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

// Mono para codigos de producto (e.j. "71 88863336", "14 BE2Y7089A").
const jetMono = JetBrains_Mono({
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
    <html
      lang="es-CL"
      className={`${fraunces.variable} ${interTight.variable} ${jetMono.variable}`}
    >
      <body className="min-h-screen bg-paper font-sans text-ink antialiased">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
