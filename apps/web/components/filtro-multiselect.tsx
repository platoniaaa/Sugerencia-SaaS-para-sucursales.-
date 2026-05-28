"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useGridFilter } from "ag-grid-react";
import type {
  GridApi,
  IDoesFilterPassParams,
  IRowNode,
} from "ag-grid-community";

/** Filtro multi-select tipo Excel / D365 para AG Grid React v32 Community.
 *
 * Patrón oficial v32: el `model` lo administra AG Grid (llega como prop +
 * se cambia con `onModelChange`), y `useGridFilter` solo registra
 * `doesFilterPass`. AG Grid maneja isFilterActive / getModel / setModel
 * automáticamente a partir de eso.
 */

interface FilterModel {
  values: string[];
}

interface CustomFilterProps {
  model: FilterModel | null;
  onModelChange: (model: FilterModel | null) => void;
  getValue: (node: IRowNode) => unknown;
  api: GridApi;
  colDef: { headerName?: string };
}

const VISIBLE_LIMIT = 500;

function toStr(v: unknown): string {
  if (v === null || v === undefined || v === "") return "(en blanco)";
  return String(v);
}

export function FiltroMultiSelect(props: CustomFilterProps) {
  const { model, onModelChange, getValue, api, colDef } = props;

  // Estado UI local (lo que el usuario está editando, NO el modelo aplicado).
  const [seleccion, setSeleccion] = useState<Set<string>>(
    () => new Set(model?.values ?? [])
  );
  const [busqueda, setBusqueda] = useState("");
  const [allValues, setAllValues] = useState<string[]>([]);
  const [listaPegada, setListaPegada] = useState<string[] | null>(null);
  const inicializadoRef = useRef(false);

  // doesFilterPass lee `model` (lo gestiona AG Grid). useGridFilter registra
  // el callback; AG Grid lo re-evalúa cuando cambia `model`.
  const doesFilterPass = useCallback(
    (params: IDoesFilterPassParams) => {
      if (!model || !model.values || model.values.length === 0) return true;
      const v = toStr(getValue(params.node));
      return model.values.includes(v);
    },
    [model, getValue]
  );

  useGridFilter({ doesFilterPass });

  // Calcular valores distintos al montar.
  useEffect(() => {
    if (inicializadoRef.current) return;
    inicializadoRef.current = true;
    const vals = new Set<string>();
    api.forEachNode((node: IRowNode) => {
      vals.add(toStr(getValue(node)));
    });
    const arr = Array.from(vals).sort((a, b) =>
      a.localeCompare(b, "es", { numeric: true })
    );
    setAllValues(arr);
    // Si no hay filtro aplicado, todos seleccionados por defecto.
    if (!model) setSeleccion(new Set(arr));
  }, [api, getValue, model]);

  // ----- Lista visible -----
  const visible = useMemo(() => {
    if (listaPegada) return listaPegada;
    const q = busqueda.trim().toLowerCase();
    if (!q) return allValues;
    return allValues.filter((v) => v.toLowerCase().includes(q));
  }, [allValues, busqueda, listaPegada]);

  const visibleCap = listaPegada ? visible : visible.slice(0, VISIBLE_LIMIT);
  const allVisibleChecked =
    visibleCap.length > 0 && visibleCap.every((v) => seleccion.has(v));
  const someVisibleChecked = visibleCap.some((v) => seleccion.has(v));

  const toggleAllVisible = (checked: boolean) => {
    const next = new Set(seleccion);
    if (checked) visibleCap.forEach((v) => next.add(v));
    else visibleCap.forEach((v) => next.delete(v));
    setSeleccion(next);
  };

  const toggleOne = (val: string, checked: boolean) => {
    const next = new Set(seleccion);
    if (checked) next.add(val);
    else next.delete(val);
    setSeleccion(next);
  };

  // ----- Pegado de lista -----
  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    const text = e.clipboardData.getData("text");
    const tieneMultiples = /[\n\t;]/.test(text) || text.split(",").length > 3;
    if (!tieneMultiples) return;
    e.preventDefault();
    const seen = new Set<string>();
    const vals: string[] = [];
    for (const raw of text.split(/[\n\t;,]+/)) {
      const s = raw.trim();
      if (s && !seen.has(s)) {
        seen.add(s);
        vals.push(s);
      }
    }
    if (vals.length > 1) {
      setListaPegada(vals);
      setSeleccion(new Set(vals));
      setBusqueda("");
    }
  };

  const onBuscarChange = (txt: string) => {
    setBusqueda(txt);
    if (listaPegada && txt !== "") setListaPegada(null);
  };

  const volverListaCompleta = () => {
    setListaPegada(null);
    setBusqueda("");
    setSeleccion(new Set(allValues));
  };

  // Cierra el popup. Probamos varias formas porque la API cambia entre versiones.
  const cerrarPopup = () => {
    try {
      const a = api as unknown as { hidePopupMenu?: () => void };
      a.hidePopupMenu?.();
    } catch {
      // ignore
    }
    // Fallback: ESC para cerrar
    try {
      document.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape", bubbles: true })
      );
    } catch {
      // ignore
    }
  };

  // ----- Aplicar / limpiar (cambian el modelo via onModelChange) -----
  const aplicar = () => {
    const allSelected =
      allValues.length > 0 &&
      seleccion.size >= allValues.length &&
      allValues.every((v) => seleccion.has(v));
    if (allSelected || seleccion.size === 0) {
      onModelChange(null); // sin filtro
    } else {
      onModelChange({ values: Array.from(seleccion) });
    }
    cerrarPopup();
  };

  const limpiar = () => {
    onModelChange(null);
    setSeleccion(new Set(allValues));
    setBusqueda("");
    setListaPegada(null);
    cerrarPopup();
  };

  const titulo = colDef?.headerName ?? "Filtrar";

  return (
    <div
      className="flex w-80 flex-col bg-white p-2 text-sm text-slate-800"
      style={{ maxHeight: "min(55vh, 360px)" }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <input
        type="text"
        placeholder={`Buscar en ${titulo}… (o pega una lista)`}
        value={busqueda}
        onChange={(e) => onBuscarChange(e.target.value)}
        onPaste={handlePaste}
        className="mb-2 w-full rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
      />

      {listaPegada && (
        <div className="mb-1 flex items-center justify-between rounded bg-brand-50 px-2 py-1 text-[12px] text-brand">
          <span>
            Lista pegada: <b>{listaPegada.length}</b> valores
          </span>
          <button
            type="button"
            onClick={volverListaCompleta}
            className="hover:underline"
          >
            Ver lista completa
          </button>
        </div>
      )}

      <label className="flex cursor-pointer select-none items-center gap-2 border-b border-slate-100 px-1 py-1.5 text-[13px] font-medium text-slate-800">
        <input
          type="checkbox"
          className="h-4 w-4 accent-brand"
          checked={allVisibleChecked}
          ref={(el) => {
            if (el) el.indeterminate = !allVisibleChecked && someVisibleChecked;
          }}
          onChange={(e) => toggleAllVisible(e.target.checked)}
        />
        (Seleccionar todo)
      </label>

      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {visibleCap.length === 0 && (
          <p className="px-2 py-4 text-center text-[12px] text-slate-400">
            Sin coincidencias.
          </p>
        )}
        {visibleCap.map((v) => (
          <label
            key={v}
            className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-[13px] hover:bg-slate-50"
          >
            <input
              type="checkbox"
              className="h-4 w-4 accent-brand"
              checked={seleccion.has(v)}
              onChange={(e) => toggleOne(v, e.target.checked)}
            />
            <span className="truncate" title={v}>
              {v}
            </span>
          </label>
        ))}
      </div>

      {!listaPegada && visible.length > VISIBLE_LIMIT && (
        <p className="border-t border-slate-100 px-1 pt-1 text-[11px] text-amber-700">
          Muestra los primeros {VISIBLE_LIMIT} de {visible.length}. Refina la
          búsqueda — o pega la lista — para los demás.
        </p>
      )}

      <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2">
        <button
          type="button"
          onClick={limpiar}
          className="text-[12px] text-slate-500 hover:text-slate-800 hover:underline"
        >
          Borrar filtro
        </button>
        <button
          type="button"
          onClick={aplicar}
          className="rounded bg-brand px-3 py-1.5 text-[12px] font-semibold text-white hover:opacity-90"
        >
          ACEPTAR
        </button>
      </div>
    </div>
  );
}
