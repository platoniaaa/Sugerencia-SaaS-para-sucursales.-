"use client";

import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { COLUMNAS, KEYS_POR_DEFECTO } from "@/lib/columnas";

interface Props {
  open: boolean;
  onClose: () => void;
  visibles: string[];
  onChange: (cols: string[]) => void;
}

export function ConfigurarColumnas({ open, onClose, visibles, onChange }: Props) {
  const toggle = (key: string) => {
    onChange(
      visibles.includes(key)
        ? visibles.filter((k) => k !== key)
        : [...visibles, key]
    );
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Configurar columnas"
      description="Elige que columnas mostrar en la tabla. Se guardan en este navegador."
    >
      <div className="grid max-h-[50vh] grid-cols-2 gap-x-4 gap-y-1 overflow-auto pr-1">
        {COLUMNAS.map((c) => (
          <label
            key={c.key as string}
            className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-slate-700 hover:bg-slate-50"
          >
            <input
              type="checkbox"
              className="h-4 w-4 accent-brand"
              checked={visibles.includes(c.key as string)}
              onChange={() => toggle(c.key as string)}
            />
            {c.label}
          </label>
        ))}
      </div>
      <div className="mt-4 flex justify-between border-t border-slate-100 pt-3">
        <Button variant="ghost" size="sm" onClick={() => onChange(KEYS_POR_DEFECTO)}>
          Restaurar por defecto
        </Button>
        <Button size="sm" onClick={onClose}>
          Listo
        </Button>
      </div>
    </Dialog>
  );
}
