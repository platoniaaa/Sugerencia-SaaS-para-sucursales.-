"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import type { CatalogoDetalle } from "@/lib/types";

export default function DetalleCatalogoPage({ params }: { params: { producto: string } }) {
  const producto = decodeURIComponent(params.producto);
  const [d, setD] = useState<CatalogoDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    setCargando(true);
    api
      .catalogoDetalle(producto)
      .then((r) => setD(r))
      .catch((e) => setError(e instanceof Error ? e.message : "Error al cargar"))
      .finally(() => setCargando(false));
  }, [producto]);

  if (cargando) return <p className="text-slate-500">Cargando…</p>;
  if (error) return <p className="text-red-600">{error}</p>;
  if (!d) return <p className="text-slate-500">Producto no encontrado en el catálogo.</p>;

  const stockTotal = d.stock_total ?? 0;
  const conStock = d.stock_por_sucursal.filter((s) => s.stock > 0);

  return (
    <div className="space-y-4">
      <div>
        <Link
          href="/catalogo"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft size={14} /> Volver al catálogo
        </Link>
        <div className="mt-2 flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900">{d.producto}</h1>
            <p className="text-sm text-slate-600">{d.glosa ?? "—"}</p>
          </div>
          <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
            CATÁLOGO
          </span>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Card titulo="Stock total (BI)" valor={formatoNumero(stockTotal)} acento />
        <Card titulo="Familia" valor={d.familia ?? "—"} />
        <Card titulo="Procedencia" valor={d.procedencia ?? "—"} />
        <Card titulo="Costo" valor={d.costo != null ? formatoCLP(d.costo) : "—"} />
        <Card titulo="Precio" valor={d.precio != null ? formatoCLP(d.precio) : "—"} />
        <Card titulo="Unidad" valor={d.unidad ?? "—"} />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Stock por sucursal / bodega</h2>
          <p className="text-xs text-slate-500">
            Snapshot del Power BI (tabla "Stock Unificado") al último push.
          </p>
        </div>
        {conStock.length === 0 ? (
          <p className="px-4 py-6 text-sm text-slate-500">Este producto no tiene stock registrado.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Origen</th>
                <th className="px-4 py-2">Sucursal</th>
                <th className="px-4 py-2">Bodega</th>
                <th className="px-4 py-2 text-right">Stock</th>
              </tr>
            </thead>
            <tbody>
              {conStock.map((s, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="px-4 py-2 text-slate-600">{s.origen ?? "—"}</td>
                  <td className="px-4 py-2 font-medium">{s.sucursal_id ?? "—"}</td>
                  <td className="px-4 py-2 text-slate-600">{s.bodega ?? "—"}</td>
                  <td className="px-4 py-2 text-right tabular-nums font-semibold">
                    {formatoNumero(s.stock)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-slate-200 bg-slate-50">
                <td className="px-4 py-2 font-semibold" colSpan={3}>
                  Total
                </td>
                <td className="px-4 py-2 text-right tabular-nums font-semibold">
                  {formatoNumero(stockTotal)}
                </td>
              </tr>
            </tfoot>
          </table>
        )}
      </div>
    </div>
  );
}

function Card({ titulo, valor, acento }: { titulo: string; valor: string; acento?: boolean }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{titulo}</p>
      <p className={`mt-1 text-lg font-semibold ${acento ? "text-emerald-700" : "text-slate-900"}`}>
        {valor}
      </p>
    </div>
  );
}
