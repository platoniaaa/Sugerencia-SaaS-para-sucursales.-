"use client";

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatoNumero } from "@/lib/formato";

interface Props {
  stockActivoMasTransito: number;
  puntoPedido: number;
  stockOptimo: number;
}

/** Barras horizontales: stock disponible vs umbrales de reposicion. */
export function GraficoStock({ stockActivoMasTransito, puntoPedido, stockOptimo }: Props) {
  const data = [
    { nombre: "Stock Optimo", valor: Math.round(stockOptimo), color: "#1e40af" },
    { nombre: "Punto de Pedido", valor: Math.round(puntoPedido), color: "#60a5fa" },
    { nombre: "Disponible (activo+transito)", valor: Math.round(stockActivoMasTransito), color: "#10b981" },
  ];

  return (
    <ResponsiveContainer width="100%" height={150}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 48, left: 8, bottom: 4 }}
        barCategoryGap={10}
      >
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="nombre"
          width={150}
          tick={{ fontSize: 11, fill: "#475569" }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          formatter={(v: number) => [formatoNumero(v), "Unidades"]}
          cursor={{ fill: "#f1f5f9" }}
          contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
        />
        <Bar dataKey="valor" radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.nombre} fill={d.color} />
          ))}
          <LabelList
            dataKey="valor"
            position="right"
            formatter={(v: number) => formatoNumero(v)}
            style={{ fontSize: 11, fill: "#334155", fontWeight: 600 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
