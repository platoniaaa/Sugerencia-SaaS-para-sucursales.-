"use client";

import {
  forwardRef,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  IDoesFilterPassParams,
  IFilterParams,
  IRowNode,
} from "ag-grid-community";

/** Filtro multi-select tipo Excel / D365 para AG Grid Community.
 *
 * - Buscador arriba: si escribes texto, filtra los checkboxes visibles;
 *   si PEGAS una lista (con saltos de línea, tabs, ; o comas), la usa
 *   como conjunto exacto de valores a filtrar.
 * - Lista de valores únicos de la columna con (Seleccionar todo).
 * - Aplica al apretar ACEPTAR; "Borrar filtro" deja la columna sin filtro.
 */

interface FilterModel {
  values: string[];
}

const VISIBLE_LIMIT = 500;

function toStr(v: unknown): string {
  if (v === null || v === undefined || v === "") return "(en blanco)";
  if (typeof v === "number") return String(v);
  return String(v);
}

export const FiltroMultiSelect = forwardRef<unknown, IFilterParams>(
  function FiltroMultiSelect(props, ref) {
    const { api, getValue, filterChangedCallback, colDef } = props;

    // Estado "oficial" del filtro (lo que AG Grid usa para doesFilterPass).
    const selRef = useRef<Set<string>>(new Set());
    const activoRef = useRef(false);
    const valuesRef = useRef<string[]>([]);

    // Estado de la UI (lo que el usuario está editando).
    const [busqueda, setBusqueda] = useState("");
    const [allValues, setAllValues] = useState<string[]>([]);
    const [seleccion, setSeleccion] = useState<Set<string>>(new Set());
    const [, bump] = useState(0);

    const computeDistinct = (): string[] => {
      const vals = new Set<string>();
      api.forEachNode((node: IRowNode) => {
        vals.add(toStr(getValue(node)));
      });
      return Array.from(vals).sort((a, b) =>
        a.localeCompare(b, "es", { numeric: true })
      );
    };

    useImperativeHandle(
      ref,
      () => ({
        isFilterActive: () => activoRef.current,
        doesFilterPass: (params: IDoesFilterPassParams) => {
          const v = toStr(getValue(params.node));
          return selRef.current.has(v);
        },
        getModel: () =>
          activoRef.current ? { values: Array.from(selRef.current) } : null,
        setModel: (model: FilterModel | null) => {
          if (!model || !model.values) {
            activoRef.current = false;
            selRef.current = new Set();
          } else {
            activoRef.current = true;
            selRef.current = new Set(model.values);
          }
          setSeleccion(new Set(selRef.current));
          bump((n) => n + 1);
        },
        afterGuiAttached: () => {
          const distinct = computeDistinct();
          valuesRef.current = distinct;
          setAllValues(distinct);
          // Si no hay filtro activo, todos seleccionados por defecto (= sin filtro).
          setSeleccion(
            activoRef.current ? new Set(selRef.current) : new Set(distinct)
          );
          setBusqueda("");
        },
      }),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      []
    );

    const visible = useMemo(() => {
      const q = busqueda.trim().toLowerCase();
      if (!q) return allValues;
      return allValues.filter((v) => v.toLowerCase().includes(q));
    }, [allValues, busqueda]);

    const visibleCap = visible.slice(0, VISIBLE_LIMIT);
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

    // Pegar una columna del Excel → reemplaza la selección por esos valores exactos.
    const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
      const text = e.clipboardData.getData("text");
      const tieneMultiples = /[\n\t;]/.test(text) || text.split(",").length > 3;
      if (!tieneMultiples) return;
      e.preventDefault();
      const vals = text
        .split(/[\n\t;,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      if (vals.length > 1) {
        setSeleccion(new Set(vals));
        setBusqueda("");
      }
    };

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
    };

    const limpiar = () => {
      activoRef.current = false;
      selRef.current = new Set();
      setSeleccion(new Set(valuesRef.current));
      setBusqueda("");
      filterChangedCallback();
    };

    const titulo = colDef?.headerName ?? "Filtrar";

    return (
      <div
        className="w-80 bg-white p-2 text-sm text-slate-800"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <input
          type="text"
          placeholder={`Buscar en ${titulo}… (o pega una lista)`}
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          onPaste={handlePaste}
          className="mb-2 w-full rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />

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

        <div className="max-h-64 overflow-y-auto py-1">
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

        {visible.length > VISIBLE_LIMIT && (
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
);
