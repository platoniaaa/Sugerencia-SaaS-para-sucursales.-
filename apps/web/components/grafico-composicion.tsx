"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { formatoNumero } from "@/lib/formato";

interface Props {
  traslado: number;
  compra: number;
}

/** Dona: como se reparte el sugerido total (traslado desde CD vs compra al proveedor). */
export function GraficoComposicion({ traslado, compra }: Props) {
  const total = traslado + compra;
  if (total <= 0) return null;

  const data = [
    { nombre: "Traslado desde CD", valor: traslado, color: "#1e40af" },
    { nombre: "Compra al proveedor", valor: compra, color: "#10b981" },
  ].filter((d) => d.valor > 0);

  return (
    <div className="flex items-center gap-4">
      <div className="relative h-[130px] w-[130px] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="valor"
              nameKey="nombre"
              innerRadius={42}
              outerRadius={62}
              paddingAngle={2}
              isAnimationActive={false}
              stroke="none"
            >
              {data.map((d) => (
                <Cell key={d.nombre} fill={d.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(v: number, n) => [formatoNumero(v) + " u.", n]}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="tabular text-xl font-bold text-slate-900">{formatoNumero(total)}</span>
          <span className="text-[10px] text-slate-400">unidades</span>
        </div>
      </div>
      <ul className="space-y-1.5 text-[13px]">
        {data.map((d) => (
          <li key={d.nombre} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: d.color }} />
            <span className="text-slate-600">{d.nombre}</span>
            <span className="tabular font-semibold text-slate-900">{formatoNumero(d.valor)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
