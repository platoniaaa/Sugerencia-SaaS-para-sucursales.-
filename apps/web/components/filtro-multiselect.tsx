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
  IDoesFilterPassParams,
  IFilterParams,
  IRowNode,
} from "ag-grid-community";

/** Filtro multi-select tipo Excel / D365 para AG Grid Community v32.
 *
 * - Buscador arriba: si escribes texto, filtra los checkboxes visibles;
 *   si PEGAS una lista (con saltos de línea, tabs, ; o varias comas), la
 *   usa como conjunto exacto de valores a filtrar.
 * - Lista de valores únicos de la columna con (Seleccionar todo).
 * - Aplica al apretar ACEPTAR y cierra el popup.
 */

interface FilterModel {
  values: string[];
}

const VISIBLE_LIMIT = 500;

function toStr(v: unknown): string {
  if (v === null || v === undefined || v === "") return "(en blanco)";
  return String(v);
}

export function FiltroMultiSelect(props: IFilterParams) {
  const { api, filterChangedCallback, colDef, column } = props;

  const obtenerValor = useCallback(
    (node: IRowNode): unknown => {
      // AG Grid v32 usa `valueGetter`; algunas builds tambien tienen `getValue`.
      // Si no hay ninguna, caemos al data crudo por field.
      const p = props as unknown as Record<string, unknown>;
      const fn =
        (p.getValue as ((n: IRowNode) => unknown) | undefined) ??
        (p.valueGetter as ((n: IRowNode) => unknown) | undefined);
      if (fn) return fn(node);
      const field = column?.getColId?.() ?? (colDef?.field as string | undefined);
      if (field && node.data) return (node.data as Record<string, unknown>)[field];
      return undefined;
    },
    [colDef, column, props]
  );

  // Estado "oficial" del filtro (refs estables que leen los callbacks).
  const selRef = useRef<Set<string>>(new Set());
  const activoRef = useRef(false);
  const valuesRef = useRef<string[]>([]);

  // Estado de la UI.
  const [busqueda, setBusqueda] = useState("");
  const [allValues, setAllValues] = useState<string[]>([]);
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set());
  const [listaPegada, setListaPegada] = useState<string[] | null>(null);

  // ----- Callbacks para AG Grid (registrados via useGridFilter) -----
  const isFilterActive = useCallback(() => activoRef.current, []);

  const doesFilterPass = useCallback(
    (params: IDoesFilterPassParams) => {
      const v = toStr(obtenerValor(params.node));
      return selRef.current.has(v);
    },
    [obtenerValor]
  );

  const getModel = useCallback(
    () => (activoRef.current ? { values: Array.from(selRef.current) } : null),
    []
  );

  const setModel = useCallback((model: FilterModel | null) => {
    if (!model || !model.values) {
      activoRef.current = false;
      selRef.current = new Set();
    } else {
      activoRef.current = true;
      selRef.current = new Set(model.values);
    }
    setSeleccion(new Set(selRef.current));
  }, []);

  // El hook recomendado en AG Grid React v32 para registrar el filtro custom.
  useGridFilter({
    isFilterActive,
    doesFilterPass,
    getModel,
    setModel,
  });

  // ----- Inicializar la lista de valores al montar -----
  useEffect(() => {
    const vals = new Set<string>();
    api.forEachNode((node: IRowNode) => {
      vals.add(toStr(obtenerValor(node)));
    });
    const arr = Array.from(vals).sort((a, b) =>
      a.localeCompare(b, "es", { numeric: true })
    );
    valuesRef.current = arr;
    setAllValues(arr);
    setSeleccion(
      activoRef.current ? new Set(selRef.current) : new Set(arr)
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ----- Lista visible y toggles -----
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
    setSeleccion(new Set(valuesRef.current));
  };

  // ----- Cerrar el popup despues de aplicar -----
  const cerrarPopup = () => {
    const a = api as unknown as { hidePopupMenu?: () => void };
    a.hidePopupMenu?.();
  };

  // ----- Aplicar / limpiar -----
  const aplicar = () => {
    const total = valuesRef.current.length;
    const allSelected =
      total > 0 &&
      seleccion.size >= total &&
      valuesRef.current.every((v) => seleccion.has(v));
    if (allSelected || seleccion.size === 0) {
      activoRef.current = false;
      selRef.current = new Set();
    } else {
      activoRef.current = true;
      selRef.current = new Set(seleccion);
    }
    filterChangedCallback();
    cerrarPopup();
  };

  const limpiar = () => {
    activoRef.current = false;
    selRef.current = new Set();
    setSeleccion(new Set(valuesRef.current));
    setBusqueda("");
    setListaPegada(null);
    filterChangedCallback();
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
