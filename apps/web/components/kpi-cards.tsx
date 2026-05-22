"use client";

import { Boxes, DollarSign, Package, Truck } from "lucide-react";
import { Card } from "@/components/ui/card";
import { formatoCLPCorto, formatoNumero } from "@/lib/formato";
import type { SugeridoKpis } from "@/lib/types";

interface Props {
  kpis: SugeridoKpis | null;
  cargando: boolean;
}

function KpiCard({
  icon,
  label,
  valor,
  tono,
}: {
  icon: React.ReactNode;
  label: string;
  valor: string;
  tono: string;
}) {
  return (
    <Card className="flex items-center gap-3 px-4 py-3.5">
      <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${tono}`}>
        {icon}
      </div>
      <div className="min-w-0">
        <p className="truncate text-[12px] font-medium uppercase tracking-wide text-slate-500">
          {label}
        </p>
        <p className="tabular text-xl font-semibold text-slate-900">{valor}</p>
      </div>
    </Card>
  );
}

export function KpiCards({ kpis, cargando }: Props) {
  const v = (s: string) => (cargando || !kpis ? "…" : s);
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <KpiCard
        icon={<Boxes size={20} className="text-brand" />}
        tono="bg-brand-50"
        label="Total Sugerido"
        valor={v(formatoNumero(kpis?.total_sugerido))}
      />
      <KpiCard
        icon={<DollarSign size={20} className="text-emerald-600" />}
        tono="bg-emerald-50"
        label="Valor Total"
        valor={v(formatoCLPCorto(kpis?.valor_total_clp))}
      />
      <KpiCard
        icon={<Package size={20} className="text-violet-600" />}
        tono="bg-violet-50"
        label="Productos a Comprar"
        valor={v(formatoNumero(kpis?.n_productos))}
      />
      <KpiCard
        icon={<Truck size={20} className="text-amber-600" />}
        tono="bg-amber-50"
        label="Proveedores a Contactar"
        valor={v(formatoNumero(kpis?.n_proveedores))}
      />
    </div>
  );
}
