"use client";

import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { MultiSelect } from "@/components/ui/multiselect";
import type { SugeridoFiltros } from "@/lib/types";

interface Props {
  filtros: SugeridoFiltros;
  onChange: (f: SugeridoFiltros) => void;
  sucursales: string[];
  marcas: string[];
}

const ABC = [
  { value: "A", label: "A" },
  { value: "B", label: "B" },
  { value: "C", label: "C" },
];
const TIPOS = [
  { value: "Nacional", label: "Nacional" },
  { value: "Importado", label: "Importado" },
  { value: "Frontera", label: "Frontera" },
];

export function FiltrosSugerido({ filtros, onChange, sucursales, marcas }: Props) {
  const set = (parcial: Partial<SugeridoFiltros>) => onChange({ ...filtros, ...parcial });
  const hayFiltros =
    filtros.q ||
    filtros.proveedor ||
    (filtros.sucursales?.length ?? 0) > 0 ||
    (filtros.abc?.length ?? 0) > 0 ||
    (filtros.filtro1?.length ?? 0) > 0 ||
    (filtros.tipo_origen?.length ?? 0) > 0 ||
    filtros.solo_pedir === false ||
    filtros.solo_abastece_cd === true;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="relative min-w-[220px] flex-1">
        <Search size={15} className="absolute left-2.5 top-2.5 text-slate-400" />
        <Input
          aria-label="Buscar producto"
          placeholder="Buscar producto o descripcion…"
          className="pl-8"
          value={filtros.q ?? ""}
          onChange={(e) => set({ q: e.target.value })}
        />
      </div>

      <MultiSelect
        label="Sucursal"
        className="w-[150px]"
        opciones={sucursales.map((s) => ({ value: s, label: s }))}
        seleccionados={filtros.sucursales ?? []}
        onChange={(v) => set({ sucursales: v })}
      />
      <MultiSelect
        label="ABC"
        className="w-[110px]"
        opciones={ABC}
        seleccionados={filtros.abc ?? []}
        onChange={(v) => set({ abc: v })}
      />
      <MultiSelect
        label="Marca"
        className="w-[140px]"
        opciones={marcas.map((m) => ({ value: m, label: m }))}
        seleccionados={filtros.filtro1 ?? []}
        onChange={(v) => set({ filtro1: v })}
      />
      <MultiSelect
        label="Origen"
        className="w-[140px]"
        opciones={TIPOS}
        seleccionados={filtros.tipo_origen ?? []}
        onChange={(v) => set({ tipo_origen: v })}
      />

      <Input
        aria-label="Proveedor"
        placeholder="Proveedor…"
        className="w-[170px]"
        value={filtros.proveedor ?? ""}
        onChange={(e) => set({ proveedor: e.target.value })}
      />

      <label className="flex h-9 cursor-pointer select-none items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-[13px] text-slate-700">
        <input
          type="checkbox"
          className="h-4 w-4 accent-brand"
          checked={filtros.solo_pedir ?? true}
          onChange={(e) => set({ solo_pedir: e.target.checked })}
        />
        Solo pedir = Si
      </label>

      <label
        className="flex h-9 cursor-pointer select-none items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-[13px] text-slate-700"
        title="Muestra solo los productos que abastece el CD (Abastece CD = Si)"
      >
        <input
          type="checkbox"
          className="h-4 w-4 accent-brand"
          checked={filtros.solo_abastece_cd ?? false}
          onChange={(e) => set({ solo_abastece_cd: e.target.checked })}
        />
        Solo abastece CD
      </label>

      {hayFiltros && (
        <button
          onClick={() =>
            onChange({
              q: "",
              proveedor: "",
              sucursales: [],
              abc: [],
              filtro1: [],
              tipo_origen: [],
              solo_pedir: true,
              solo_abastece_cd: false,
            })
          }
          className="flex h-9 items-center gap-1 rounded-md px-2 text-[13px] text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        >
          <X size={14} /> Limpiar
        </button>
      )}
    </div>
  );
}
