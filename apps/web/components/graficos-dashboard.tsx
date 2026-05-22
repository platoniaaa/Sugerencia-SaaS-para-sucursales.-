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
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoCLPCorto, formatoNumero } from "@/lib/formato";
import type { AgrupadoRow, DimensionAgrupado, SugeridoFiltros } from "@/lib/types";

type Metrica = "valor_clp" | "total_sugerido";

function MiniToggle<T extends string>({
  valor,
  opciones,
  onChange,
}: {
  valor: T;
  opciones: { id: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex rounded-md border border-slate-200 p-0.5">
      {opciones.map((o) => (
        <button
          key={o.id}
          onClick={() => onChange(o.id)}
          className={cn(
            "rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
            valor === o.id ? "bg-brand text-white" : "text-slate-500 hover:text-slate-700"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function GraficoBarras({
  titulo,
  data,
  metrica,
  extra,
}: {
  titulo: string;
  data: AgrupadoRow[];
  metrica: Metrica;
  extra?: React.ReactNode;
}) {
  const esClp = metrica === "valor_clp";
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">{titulo}</h3>
        {extra}
      </div>
      {data.length === 0 ? (
        <p className="py-10 text-center text-[13px] text-slate-400">Sin datos</p>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(160, data.length * 26)}>
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 0, right: 56, left: 8, bottom: 0 }}
            barCategoryGap={6}
          >
            <CartesianGrid horizontal={false} stroke="#f1f5f9" />
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="grupo"
              width={120}
              tick={{ fontSize: 11, fill: "#475569" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              cursor={{ fill: "#f8fafc" }}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
              formatter={(v: number) =>
                esClp ? [formatoCLP(v), "Valor"] : [formatoNumero(v), "Unidades"]
              }
            />
            <Bar
              dataKey={metrica}
              fill="#1e40af"
              radius={[0, 4, 4, 0]}
              isAnimationActive={false}
              label={{
                position: "right",
                fontSize: 10,
                fill: "#334155",
                formatter: (v: number) => (esClp ? formatoCLPCorto(v) : formatoNumero(v)),
              }}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

export function GraficosDashboard({ filtros }: { filtros: SugeridoFiltros }) {
  const [metrica, setMetrica] = useState<Metrica>("valor_clp");
  const [dim2, setDim2] = useState<DimensionAgrupado>("marca");
  const [porSucursal, setPorSucursal] = useState<AgrupadoRow[]>([]);
  const [porDim2, setPorDim2] = useState<AgrupadoRow[]>([]);

  useEffect(() => {
    let vivo = true;
    const t = setTimeout(async () => {
      try {
        const [s, d] = await Promise.all([
          api.agrupado(filtros, "sucursal"),
          api.agrupado(filtros, dim2),
        ]);
        if (vivo) {
          setPorSucursal(s);
          setPorDim2(d);
        }
      } catch {
        /* backend puede estar reiniciando */
      }
    }, 300);
    return () => {
      vivo = false;
      clearTimeout(t);
    };
  }, [filtros, dim2]);

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <GraficoBarras
        titulo="Por sucursal"
        data={porSucursal}
        metrica={metrica}
        extra={
          <MiniToggle
            valor={metrica}
            onChange={setMetrica}
            opciones={[
              { id: "valor_clp", label: "CLP" },
              { id: "total_sugerido", label: "Unidades" },
            ]}
          />
        }
      />
      <GraficoBarras
        titulo={dim2 === "marca" ? "Por marca" : "Por proveedor"}
        data={porDim2}
        metrica={metrica}
        extra={
          <MiniToggle
            valor={dim2}
            onChange={setDim2}
            opciones={[
              { id: "marca", label: "Marca" },
              { id: "proveedor", label: "Proveedor" },
            ]}
          />
        }
      />
    </div>
  );
}
