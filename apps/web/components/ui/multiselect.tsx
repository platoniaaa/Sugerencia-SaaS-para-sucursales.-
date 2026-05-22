"use client";

import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  opciones: { value: string; label: string }[];
  seleccionados: string[];
  onChange: (vals: string[]) => void;
  className?: string;
}

/** Dropdown de seleccion multiple con checkboxes (estilo slicer). */
export function MultiSelect({
  label,
  opciones,
  seleccionados,
  onChange,
  className,
}: Props) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const toggle = (value: string) => {
    onChange(
      seleccionados.includes(value)
        ? seleccionados.filter((v) => v !== value)
        : [...seleccionados, value]
    );
  };

  return (
    <div ref={ref} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex h-9 w-full items-center justify-between gap-2 rounded-md border border-slate-300 bg-white px-3 text-[13px] text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <span className="truncate">
          {label}
          {seleccionados.length > 0 && (
            <span className="ml-1 rounded bg-brand-50 px-1.5 py-0.5 text-[11px] font-medium text-brand">
              {seleccionados.length}
            </span>
          )}
        </span>
        <ChevronDown size={15} className="shrink-0 text-slate-400" />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 max-h-64 w-full min-w-[180px] overflow-auto rounded-md border border-slate-200 bg-white py-1 shadow-lg">
          {opciones.length === 0 && (
            <p className="px-3 py-2 text-[13px] text-slate-400">Sin opciones</p>
          )}
          {opciones.map((o) => {
            const sel = seleccionados.includes(o.value);
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => toggle(o.value)}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] text-slate-700 hover:bg-slate-50"
              >
                <span
                  className={cn(
                    "flex h-4 w-4 items-center justify-center rounded border",
                    sel ? "border-brand bg-brand text-white" : "border-slate-300"
                  )}
                >
                  {sel && <Check size={12} />}
                </span>
                <span className="truncate">{o.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
