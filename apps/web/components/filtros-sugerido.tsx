"use client";

import { Search, X } from "lucide-react";
import type { SugeridoFiltros } from "@/lib/types";

interface Props {
  filtros: SugeridoFiltros;
  onChange: (f: SugeridoFiltros) => void;
}

export function FiltrosSugerido({ filtros, onChange }: Props) {
  const set = (parcial: Partial<SugeridoFiltros>) => onChange({ ...filtros, ...parcial });
  const hayCambios =
    Boolean(filtros.q) ||
    filtros.solo_pedir === false ||
    filtros.solo_abastece_cd === true ||
    filtros.solo_nacionales === true;

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-sm border border-ink-200 bg-white p-3 shadow-card">
      {/* Buscador global — matchea cualquier columna del sugerido */}
      <div className="relative min-w-[260px] flex-1">
        <Search
          size={15}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400"
        />
        <input
          aria-label="Buscar"
          placeholder="Buscar en toda la tabla… (producto, sucursal, marca, proveedor, ABC…)"
          className="h-10 w-full rounded-sm border border-ink-200 bg-paper-50 pl-9 pr-3 text-[13.5px] text-ink-900 placeholder:text-ink-400 transition-colors focus-visible:border-accent-700 focus-visible:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-700/30"
          value={filtros.q ?? ""}
          onChange={(e) => set({ q: e.target.value })}
        />
        {filtros.q && (
          <button
            onClick={() => set({ q: "" })}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
            aria-label="Borrar búsqueda"
          >
            <X size={13} />
          </button>
        )}
      </div>

      <Toggle
        label="Solo pedir = Sí"
        active={filtros.solo_pedir ?? true}
        onChange={(v) => set({ solo_pedir: v })}
      />
      <Toggle
        label="Solo abastece CD"
        active={filtros.solo_abastece_cd ?? false}
        onChange={(v) => set({ solo_abastece_cd: v })}
        title="Muestra solo los productos con Abastece CD = Sí"
      />
      <Toggle
        label="Solo nacionales"
        active={filtros.solo_nacionales ?? false}
        onChange={(v) => set({ solo_nacionales: v })}
        title="Excluye los productos importados"
      />

      {hayCambios && (
        <button
          onClick={() =>
            onChange({
              q: "",
              solo_pedir: true,
              solo_abastece_cd: false,
              solo_nacionales: false,
            })
          }
          className="flex items-center gap-1 rounded-sm px-2 py-1.5 text-[12px] text-ink-500 hover:bg-ink-100 hover:text-ink-800"
        >
          <X size={13} /> Limpiar
        </button>
      )}
    </div>
  );
}

function Toggle({
  label,
  active,
  onChange,
  title,
}: {
  label: string;
  active: boolean;
  onChange: (v: boolean) => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={() => onChange(!active)}
      className={`group flex h-10 items-center gap-2 rounded-sm border px-3 text-[13px] font-medium transition-colors ${
        active
          ? "border-accent-700 bg-accent-50 text-accent-700"
          : "border-ink-200 bg-white text-ink-600 hover:border-ink-300 hover:text-ink-900"
      }`}
    >
      <span
        className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors ${
          active ? "bg-accent-700" : "bg-ink-300 group-hover:bg-ink-400"
        }`}
      >
        <span
          className={`inline-block h-3 w-3 rounded-full bg-white shadow transition-transform ${
            active ? "translate-x-3.5" : "translate-x-0.5"
          }`}
        />
      </span>
      {label}
    </button>
  );
}
