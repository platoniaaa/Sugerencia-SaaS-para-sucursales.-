"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  values?: string[];
  contains?: string;
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

  // Función para calcular los valores únicos de la columna. Se llama tanto al
  // montar (para la lista completa) como dentro de handlePaste (para garantizar
  // que el matching siempre tenga datos frescos del grid, sin depender del estado).
  const calcularDistintos = useCallback((): string[] => {
    const vals = new Set<string>();
    api.forEachNode((node: IRowNode) => {
      vals.add(toStr(getValue(node)));
    });
    return Array.from(vals).sort((a, b) =>
      a.localeCompare(b, "es", { numeric: true })
    );
  }, [api, getValue]);

  const [allValues, setAllValues] = useState<string[]>(() => calcularDistintos());

  // Mantener allValues sincronizado: AG Grid construye el filter component
  // una vez por columna y lo cachea. Si rowData cambia despues (carga
  // asincrona, re-fetch), tenemos que recalcular o quedamos con los valores
  // del primer render (en algunas vistas iniciales podia haber 0-1 filas).
  useEffect(() => {
    const refrescar = () => {
      const nuevos = calcularDistintos();
      setAllValues((prev) => {
        if (prev.length === nuevos.length && prev.every((v, i) => v === nuevos[i])) {
          return prev; // sin cambios -> no re-render
        }
        return nuevos;
      });
    };
    refrescar();
    api.addEventListener("modelUpdated", refrescar);
    return () => {
      api.removeEventListener("modelUpdated", refrescar);
    };
  }, [api, calcularDistintos]);

  // Estado UI local (lo que el usuario está editando, NO el modelo aplicado).
  const [seleccion, setSeleccion] = useState<Set<string>>(
    () => new Set(model?.values ?? allValues)
  );

  // Si todavia no hay filtro aplicado (model null) y allValues crecio, ampliar
  // la seleccion para que el "(Seleccionar todo)" siga marcando todos los nuevos.
  useEffect(() => {
    if (model) return; // filtro activo -> respetamos el model del usuario
    setSeleccion((prev) => {
      if (prev.size === allValues.length && allValues.every((v) => prev.has(v))) {
        return prev;
      }
      return new Set(allValues);
    });
  }, [allValues, model]);
  // Si el modelo guardado es "contiene X", precargamos esa busqueda al abrir.
  const [busqueda, setBusqueda] = useState<string>(model?.contains ?? "");
  const [listaPegada, setListaPegada] = useState<string[] | null>(null);
  const [pegadoInfo, setPegadoInfo] = useState<{
    total: number;
    exactos: number;
    expandidos: number;
    sinMatch: string[];
  } | null>(null);

  // doesFilterPass lee `model` (lo gestiona AG Grid). useGridFilter registra
  // el callback; AG Grid lo re-evalúa cuando cambia `model`.
  // Tres modos:
  // - model null            -> sin filtro (pasan todas las filas).
  // - model.contains "X"    -> incluye "X" (case-insensitive). Funciona como el
  //                            buscador grande de arriba: matchea cualquier valor
  //                            que contenga ese texto, sin tope de 500.
  // - model.values [...]    -> solo las filas cuyo valor esta en la lista exacta.
  //                            Si la lista esta vacia, la tabla queda vacia.
  const doesFilterPass = useCallback(
    (params: IDoesFilterPassParams) => {
      if (!model) return true;
      const v = toStr(getValue(params.node));
      if (model.contains !== undefined && model.contains !== "") {
        return v.toLowerCase().includes(model.contains.toLowerCase());
      }
      if (!model.values || model.values.length === 0) return false;
      return model.values.includes(v);
    },
    [model, getValue]
  );

  useGridFilter({ doesFilterPass });

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
  // Si un valor pegado no calza EXACTO con un valor real de la columna, lo busca
  // por PREFIJO (ej. pegan "19 HL3Z8005" -> incluye "19 HL3Z8005B" y "19 HL3Z8005C").
  // Asi el filtro tolera que el BI muestre los codigos truncados.
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
    if (vals.length < 2) return;

    // SIEMPRE recalculamos los valores frescos del grid (no confiamos en el state,
    // por si al primer render el grid no habia terminado de poblarse).
    let valoresFrescos = calcularDistintos();
    // Si api.forEachNode no devolvio nada, intentar via rowModel.
    if (valoresFrescos.length <= 1) {
      const model = (api as unknown as { getDisplayedRowCount?: () => number; getDisplayedRowAtIndex?: (i: number) => IRowNode | null });
      const n = model.getDisplayedRowCount?.() ?? 0;
      if (n > 0 && model.getDisplayedRowAtIndex) {
        const s = new Set<string>();
        for (let i = 0; i < n; i++) {
          const node = model.getDisplayedRowAtIndex(i);
          if (node) s.add(toStr(getValue(node)));
        }
        valoresFrescos = Array.from(s).sort((a, b) => a.localeCompare(b, "es", { numeric: true }));
      }
    }
    if (valoresFrescos.length > allValues.length) {
      setAllValues(valoresFrescos);
    }

    // Indice case-insensitive para buscar rapido
    const allLower = valoresFrescos.map((v) => v.toLowerCase());
    const matched = new Set<string>();
    let exactos = 0;
    let expandidos = 0;
    const sinMatch: string[] = [];
    for (const v of vals) {
      const norm = v.toLowerCase();
      // 1. Exacto (case-insensitive)
      const iEx = allLower.indexOf(norm);
      if (iEx !== -1) {
        matched.add(valoresFrescos[iEx]);
        exactos++;
        continue;
      }
      // 2. Prefijo
      const prefijo = valoresFrescos.filter((_, i) => allLower[i].startsWith(norm));
      if (prefijo.length > 0) {
        prefijo.forEach((m) => matched.add(m));
        expandidos++;
        continue;
      }
      // 3. Contiene (ultimo recurso)
      const contiene = valoresFrescos.filter((_, i) => allLower[i].includes(norm));
      if (contiene.length > 0) {
        contiene.forEach((m) => matched.add(m));
        expandidos++;
        continue;
      }
      sinMatch.push(v);
    }

    if (matched.size === 0) {
      // Nada calzo. Igualmente activamos el modo "lista pegada" con los literales
      // y los dejamos como seleccion: al aplicar la tabla quedara vacia (ningun
      // valor real coincide con esos literales), asi el usuario ve que sus codigos
      // no estan en la vista actual.
      setListaPegada(vals);
      setSeleccion(new Set(vals));
      setPegadoInfo({ total: vals.length, exactos: 0, expandidos: 0, sinMatch: vals });
      setBusqueda("");
      return;
    }

    const ordenados = Array.from(matched).sort((a, b) =>
      a.localeCompare(b, "es", { numeric: true })
    );
    setListaPegada(ordenados);
    setSeleccion(matched);
    setBusqueda("");
    setPegadoInfo({ total: vals.length, exactos, expandidos, sinMatch });
  };

  const onBuscarChange = (txt: string) => {
    setBusqueda(txt);
    if (listaPegada && txt !== "") {
      setListaPegada(null);
      setPegadoInfo(null);
    }
  };

  const volverListaCompleta = () => {
    setListaPegada(null);
    setPegadoInfo(null);
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
    const q = busqueda.trim();
    const usandoBusqueda = !listaPegada && q !== "";
    // Si todos los visibles siguen marcados, el usuario solo escribio un texto
    // (no destildo nada manualmente) -> usamos el modo CONTIENE, que captura
    // TODO lo que matchea sin tope de 500 ni snapshot fijo.
    const todoVisibleMarcado =
      visibleCap.length > 0 && visibleCap.every((v) => seleccion.has(v));

    if (usandoBusqueda && todoVisibleMarcado) {
      onModelChange({ contains: q });
      cerrarPopup();
      return;
    }

    // Si destildo algo o no hay busqueda, vamos al modo VALUES (lista explicita).
    const finalValues = usandoBusqueda
      ? new Set(visibleCap.filter((v) => seleccion.has(v)))
      : seleccion;

    const allSelected =
      allValues.length > 0 &&
      finalValues.size >= allValues.length &&
      allValues.every((v) => finalValues.has(v));

    if (allSelected) {
      onModelChange(null);
    } else {
      onModelChange({ values: Array.from(finalValues) });
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
        <div className="mb-1 rounded bg-brand-50 px-2 py-1 text-[12px] text-brand">
          <div className="flex items-center justify-between">
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
          {pegadoInfo && (
            <p className="mt-0.5 text-[11px] text-slate-600">
              {pegadoInfo.total} pegado{pegadoInfo.total === 1 ? "" : "s"}
              {pegadoInfo.exactos > 0 && ` · ${pegadoInfo.exactos} exacto${pegadoInfo.exactos === 1 ? "" : "s"}`}
              {pegadoInfo.expandidos > 0 && ` · ${pegadoInfo.expandidos} expandido${pegadoInfo.expandidos === 1 ? "" : "s"} por coincidencia parcial`}
              {pegadoInfo.sinMatch.length > 0 && (
                <span className="text-amber-700">
                  {" "}
                  · {pegadoInfo.sinMatch.length} sin coincidencia
                </span>
              )}
            </p>
          )}
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
          <div className="px-3 py-3 text-center text-[12px] text-slate-400">
            <p>Sin coincidencias en esta vista.</p>
            {busqueda.trim() && (
              <p className="mt-2 leading-snug text-slate-500">
                Si el producto debería estar, probá quitar los toggles de
                arriba (<b>Solo pedir = Sí</b>, <b>Solo nacionales</b>) o usá
                el <b>buscador grande</b> de la barra superior — busca en
                toda la base e ignora esos filtros.
              </p>
            )}
          </div>
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
