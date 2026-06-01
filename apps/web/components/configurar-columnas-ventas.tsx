"use client";

import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface Props {
  open: boolean;
  onClose: () => void;
  todas: string[]; // todas las columnas disponibles (del backend)
  visibles: string[];
  defaultCols: string[];
  onChange: (cols: string[]) => void;
}

export function ConfigurarColumnasVentas({
  open,
  onClose,
  todas,
  visibles,
  defaultCols,
  onChange,
}: Props) {
  const toggle = (key: string) => {
    onChange(
      visibles.includes(key) ? visibles.filter((k) => k !== key) : [...visibles, key]
    );
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Configurar columnas"
      description="Elige qué columnas mostrar en la tabla de ventas. Se guardan en este navegador."
    >
      <div className="grid max-h-[50vh] grid-cols-2 gap-x-4 gap-y-1 overflow-auto pr-1">
        {todas.map((c) => (
          <label
            key={c}
            className="flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1 hover:bg-ink-100"
          >
            <input
              type="checkbox"
              className="h-4 w-4 accent-accent-700"
              checked={visibles.includes(c)}
              onChange={() => toggle(c)}
            />
            <span className="text-[13px] text-ink-800">{c}</span>
          </label>
        ))}
      </div>
      <div className="mt-4 flex justify-between gap-2 border-t border-ink-100 pt-3">
        <Button variant="outline" size="sm" onClick={() => onChange(defaultCols)}>
          Restaurar predeterminadas
        </Button>
        <Button size="sm" onClick={onClose}>
          Cerrar
        </Button>
      </div>
    </Dialog>
  );
}
