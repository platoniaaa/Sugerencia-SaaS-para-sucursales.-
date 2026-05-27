"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import { formatoNumero } from "@/lib/formato";
import type { VentasResponse } from "@/lib/types";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

/** "202504" -> "Abr 25" */
function etiquetaMes(yyyymm: string): string {
  if (!yyyymm || yyyymm.length < 6) return yyyymm;
  const anio = yyyymm.slice(2, 4);
  const mes = parseInt(yyyymm.slice(4, 6), 10);
  const nombre = MESES[mes - 1] ?? yyyymm.slice(4, 6);
  return `${nombre} ${anio}`;
}

export function GraficoVentas({
  producto,
  sucursalId,
}: {
  producto: string;
  sucursalId: string;
}) {
  const [data, setData] = useState<VentasResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let activo = true;
    api
      .ventas(producto, sucursalId)
      .then((r) => activo && setData(r))
      .catch(() => activo && setError(true));
    return () => {
      activo = false;
    };
  }, [producto, sucursalId]);

  // Si no hay datos de venta cargados, no mostramos la tarjeta.
  if (error || (data && data.meses.length === 0)) return null;

  const filas = (data?.meses ?? []).map((m) => ({
    mes: etiquetaMes(m.mes),
    cantidad: Math.round(m.cantidad),
  }));
  const promedio =
    filas.length > 0 ? data!.total / filas.length : 0;

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-baseline justify-between gap-2">
        <CardTitle>Venta últimos 12 meses</CardTitle>
        {data && (
          <span className="text-[13px] text-slate-500">
            Total{" "}
            <b className="tabular text-slate-900">{formatoNumero(data.total)}</b> u ·
            promedio{" "}
            <b className="tabular text-slate-900">{formatoNumero(promedio, 1)}</b> u/mes
          </span>
        )}
      </CardHeader>
      <CardContent>
        {!data ? (
          <p className="py-8 text-center text-sm text-slate-400">Cargando ventas…</p>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={filas} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis
                dataKey="mes"
                tick={{ fontSize: 11, fill: "#475569" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#94a3b8" }}
                axisLine={false}
                tickLine={false}
                width={40}
                tickFormatter={(v: number) => formatoNumero(v)}
              />
              <Tooltip
                formatter={(v: number) => [formatoNumero(v), "Unidades"]}
                cursor={{ fill: "#f1f5f9" }}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
              />
              <Bar
                dataKey="cantidad"
                fill="#1e40af"
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
