"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import type {
  CellContextMenuEvent,
  ColDef,
  ColumnState,
  FirstDataRenderedEvent,
  GridReadyEvent,
  IRowNode,
  RowClickedEvent,
} from "ag-grid-community";
import { Check, Copy } from "lucide-react";
import { COLUMNAS, type DefColumna } from "@/lib/columnas";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import { STORAGE_KEYS, guardar, leer } from "@/lib/persistencia-dashboard";
import type { SugeridoFiltros, SugeridoKpis, SugeridoRow } from "@/lib/types";
import { FiltroMultiSelect } from "@/components/filtro-multiselect";

type Vista = NonNullable<SugeridoFiltros["vista"]>;

interface Props {
  rows: SugeridoRow[];
  columnasVisibles: string[];
  /**
   * Vista activa (todas/sucursales/cd/distribucion). El filter model se guarda
   * por vista porque sus columnas/valores no son iguales entre tabs.
   */
  vista: Vista;
  onRowClick: (row: SugeridoRow) => void;
  /**
   * Se dispara cada vez que cambia el conjunto de filas visibles (filtros de
   * columna, sort, rowData). El padre lo usa para refrescar los KPIs sobre las
   * filas realmente visibles, no sobre el universo server-side.
   */
  onKpisVisiblesChange?: (kpis: SugeridoKpis, totalVisibles: number) => void;
}

export interface TablaSugeridoHandle {
  /** IDs de las filas visibles tras filtros y orden del AG Grid. Solo del BI (id > 0). */
  obtenerIdsVisibles(): number[];
}

function ProductoCelda(p: { value: unknown; data?: SugeridoRow }) {
  const v = (p.value as string | null) ?? "";
  const origen = p.data?.origen;
  if (origen !== "catalogo" && origen !== "manual") return <>{v}</>;
  const cls =
    origen === "manual"
      ? "rounded bg-emerald-50 px-1.5 py-px text-[10px] font-semibold text-emerald-700"
      : "rounded bg-slate-100 px-1.5 py-px text-[10px] font-semibold text-slate-500";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span>{v}</span>
      <span className={cls}>{origen === "manual" ? "MANUAL" : "CATÁLOGO"}</span>
    </span>
  );
}

function formateador(def: DefColumna) {
  return (p: { value: unknown }) => {
    const v = p.value as number | string | null;
    if (v === null || v === undefined || v === "") return "—";
    switch (def.tipo) {
      case "clp":
        return formatoCLP(v as number);
      case "numero":
        return formatoNumero(v as number, 0);
      case "decimal":
        return formatoNumero(v as number, 2);
      default:
        return String(v);
    }
  };
}

function colDef(def: DefColumna): ColDef {
  const numerica = def.tipo !== "texto" && def.tipo !== "abc";
  const base: ColDef = {
    field: def.key as string,
    headerName: def.label,
    pinned: def.pin,
    sortable: true,
    resizable: true,
    minWidth: def.tipo === "texto" ? 140 : 110,
    flex: def.key === "descripcion" ? 2 : undefined,
  };

  if (def.key === "producto") {
    base.cellRenderer = ProductoCelda;
  }

  if (def.tipo === "abc") {
    base.width = 80;
    base.cellClass = "font-semibold";
    base.cellStyle = (p) => {
      const map: Record<string, { color: string }> = {
        A: { color: "#047857" },
        B: { color: "#b45309" },
        C: { color: "#64748b" },
      };
      return map[String(p.value)] ?? null;
    };
  } else if (numerica) {
    base.type = "rightAligned";
    base.cellClass = "tabular";
    base.valueFormatter = formateador(def);
    if (def.key === "total_sugerido_suc") {
      base.cellClass = "tabular font-semibold";
      base.width = 130;
    }
  }
  return base;
}

type FilterModelByVista = Record<string, Record<string, unknown>>;
type FilterModel = Record<string, unknown>;

export const TablaSugerido = forwardRef<TablaSugeridoHandle, Props>(function TablaSugerido(
  { rows, columnasVisibles, vista, onRowClick, onKpisVisiblesChange },
  ref
) {
  const gridRef = useRef<AgGridReact<SugeridoRow>>(null);
  const router = useRouter();

  // Persistencia:
  // - `restoredRef`: pasa a true tras la primera restauración. Antes de eso,
  //   ignoramos los eventos del grid (algunos disparan durante setup interno).
  // - `aplicandoRef`: true mientras NOSOTROS llamamos setFilterModel/applyColumnState
  //   para que no se persistan los cambios derivados de esa restauración.
  // - `vistaRef`: vista activa al momento del último evento (refleja la prop
  //   sin requerir cierre fresco en los handlers).
  const restoredRef = useRef(false);
  const aplicandoRef = useRef(false);
  const vistaRef = useRef<Vista>(vista);
  const resizeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Ref a la callback de KPIs para que `notificarKpis` lea siempre la version
  // mas reciente sin recrear el handler cada render.
  const onKpisRef = useRef(onKpisVisiblesChange);
  useEffect(() => {
    onKpisRef.current = onKpisVisiblesChange;
  }, [onKpisVisiblesChange]);

  /**
   * Suma KPIs sobre las filas visibles tras filtros de columna + sort del grid.
   * Espeja la misma lógica que `kpis()` del backend: sum totales, distinct de
   * producto y proveedor. Asi cuando el comprador filtra ABC=A en la columna,
   * las tarjetas de arriba muestran exactamente lo que ve en la tabla.
   */
  const notificarKpis = () => {
    const cb = onKpisRef.current;
    if (!cb) return;
    const api = gridRef.current?.api;
    if (!api) return;
    let totalSugerido = 0;
    let valorTotal = 0;
    const productos = new Set<string>();
    const proveedores = new Set<string>();
    let n = 0;
    api.forEachNodeAfterFilterAndSort((node: IRowNode<SugeridoRow>) => {
      const d = node.data;
      if (!d) return;
      n += 1;
      if (typeof d.total_sugerido_suc === "number") totalSugerido += d.total_sugerido_suc;
      if (typeof d.total_valor_sugerido_clp === "number") valorTotal += d.total_valor_sugerido_clp;
      if (d.producto) productos.add(d.producto);
      if (d.proveedor) proveedores.add(d.proveedor);
    });
    cb(
      {
        total_sugerido: totalSugerido,
        valor_total_clp: valorTotal,
        n_productos: productos.size,
        n_proveedores: proveedores.size,
      },
      n
    );
  };

  // Context menu custom (AG Grid Community no incluye context menu nativo).
  // Posicion absoluta en pixeles del viewport. valor = lo que ve el usuario
  // (post valueFormatter), no el numerico crudo: al pegar en una nota queda
  // legible; para pegar en Excel hay que limpiar puntos a mano.
  const [menu, setMenu] = useState<{ x: number; y: number; valor: string } | null>(null);
  const [toast, setToast] = useState<{ x: number; y: number } | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useImperativeHandle(
    ref,
    () => ({
      obtenerIdsVisibles: () => {
        const api = gridRef.current?.api;
        if (!api) return [];
        const ids: number[] = [];
        api.forEachNodeAfterFilterAndSort((node: IRowNode<SugeridoRow>) => {
          const id = node.data?.id;
          if (typeof id === "number" && id > 0) ids.push(id);
        });
        return ids;
      },
    }),
    []
  );

  const columnDefs = useMemo<ColDef[]>(() => {
    return COLUMNAS.filter((c) => columnasVisibles.includes(c.key as string)).map(colDef);
  }, [columnasVisibles]);

  const defaultColDef = useMemo<ColDef>(
    () => ({
      sortable: true,
      resizable: true,
      suppressHeaderMenuButton: false,
      filter: FiltroMultiSelect,
      menuTabs: ["filterMenuTab"],
    }),
    []
  );

  // Al cambiar la vista activa, re-aplicar el filter model guardado para
  // esa vista (puede ser null → AG Grid limpia los filtros).
  useEffect(() => {
    vistaRef.current = vista;
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current) return;
    const all = leer<FilterModelByVista>(STORAGE_KEYS.gridFilter, {});
    const model = all[vista] ?? null;
    aplicandoRef.current = true;
    try {
      api.setFilterModel(model);
    } catch {
      /* setFilterModel puede rechazar valores incompatibles: ignoramos */
    }
    aplicandoRef.current = false;
  }, [vista]);

  const onGridReady = (e: GridReadyEvent) => {
    // Column state (sort + orden + width) no depende de filas — se restaura ahora.
    aplicandoRef.current = true;
    try {
      const cols = leer<ColumnState[] | null>(STORAGE_KEYS.gridCols, null);
      if (cols && Array.isArray(cols) && cols.length > 0) {
        e.api.applyColumnState({ state: cols, applyOrder: true });
      }
    } catch {
      /* state incompatible (cambio columnas visibles, etc.): ignoramos */
    }
    aplicandoRef.current = false;
    e.api.sizeColumnsToFit();
  };

  const onFirstDataRendered = (e: FirstDataRenderedEvent) => {
    // El filter model del multiselect necesita rowData presente para preseleccionar
    // valores → se restaura recién acá.
    aplicandoRef.current = true;
    try {
      const all = leer<FilterModelByVista>(STORAGE_KEYS.gridFilter, {});
      const model = all[vistaRef.current] ?? null;
      if (model) e.api.setFilterModel(model);
      const page = leer<number>(STORAGE_KEYS.gridPage, 0);
      if (typeof page === "number" && page > 0) {
        e.api.paginationGoToPage(page);
      }
    } catch {
      /* noop */
    }
    aplicandoRef.current = false;
    restoredRef.current = true;
    // Primer cálculo de KPIs visibles (ya hay filas + filtros restaurados).
    notificarKpis();
  };

  // Cada vez que cambia rowData (sync, cambio vista, refresh), AG Grid puede
  // descartar valores del filter multiselect que ya no existan. Re-aplicar el
  // modelo guardado de la vista actual.
  const onRowDataUpdated = () => {
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current) return;
    aplicandoRef.current = true;
    try {
      const all = leer<FilterModelByVista>(STORAGE_KEYS.gridFilter, {});
      const model = all[vistaRef.current] ?? null;
      api.setFilterModel(model);
    } catch {
      /* noop */
    }
    aplicandoRef.current = false;
    // El dataset cambió → recalcular KPIs sobre las filas visibles.
    notificarKpis();
  };

  // Eventos que persisten cambios del usuario:

  const onFilterChanged = () => {
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current) return;
    // El usuario cambió un filtro de columna → recalcular KPIs siempre, no
    // solo cuando persistimos (la restauración también dispara este evento).
    notificarKpis();
    if (aplicandoRef.current) return;
    try {
      const all = leer<FilterModelByVista>(STORAGE_KEYS.gridFilter, {});
      const model = (api.getFilterModel() ?? {}) as FilterModel;
      all[vistaRef.current] = model;
      guardar(STORAGE_KEYS.gridFilter, all);
    } catch {
      /* noop */
    }
  };

  const persistirColumnState = () => {
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current || aplicandoRef.current) return;
    try {
      guardar(STORAGE_KEYS.gridCols, api.getColumnState());
    } catch {
      /* noop */
    }
  };

  const onSortChanged = persistirColumnState;
  const onColumnMoved = persistirColumnState;

  const onColumnResized = () => {
    if (!restoredRef.current || aplicandoRef.current) return;
    if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
    resizeTimerRef.current = setTimeout(persistirColumnState, 200);
  };

  const onPaginationChanged = () => {
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current || aplicandoRef.current) return;
    try {
      guardar(STORAGE_KEYS.gridPage, api.paginationGetCurrentPage());
    } catch {
      /* noop */
    }
  };

  // --- Context menu (copiar celda) ---

  const onCellContextMenu = (e: CellContextMenuEvent<SugeridoRow>) => {
    // Sin valor: no abrir menu (evitamos celdas vacias).
    if (e.value === null || e.value === undefined || e.value === "") return;
    // Prevenir el menu nativo del navegador.
    const mouse = e.event as MouseEvent | undefined;
    mouse?.preventDefault?.();
    // Calcular el texto que el usuario ve (aplicando valueFormatter si hay).
    let valor = "";
    try {
      const fmt = e.colDef?.valueFormatter;
      if (typeof fmt === "function") {
        const out = fmt({
          value: e.value,
          data: e.data,
          node: e.node,
          colDef: e.colDef,
          column: e.column,
          api: e.api,
          context: e.context,
        } as Parameters<typeof fmt>[0]);
        valor = out == null ? "" : String(out);
      } else {
        valor = String(e.value);
      }
    } catch {
      valor = String(e.value);
    }
    if (!valor || valor === "—") return;
    const x = mouse?.clientX ?? 0;
    const y = mouse?.clientY ?? 0;
    setMenu({ x, y, valor });
  };

  const copiarValor = async () => {
    if (!menu) return;
    const { x, y, valor } = menu;
    setMenu(null);
    try {
      await navigator.clipboard.writeText(valor);
    } catch {
      // Fallback: textarea + execCommand (navegadores viejos).
      try {
        const ta = document.createElement("textarea");
        ta.value = valor;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      } catch {
        return; // sin copy posible: no mostramos toast
      }
    }
    setToast({ x, y });
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 1200);
  };

  // ESC y click fuera: cerrar menu.
  useEffect(() => {
    if (!menu) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setMenu(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menu]);

  // Limpiar timer del toast al desmontar.
  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, []);

  // El popup del menu/filtro se monta en body para poder voltearse hacia arriba
  // cuando no hay espacio abajo (asi el boton ACEPTAR no queda cortado).
  const popupParent = useMemo<HTMLElement | undefined>(
    () => (typeof document !== "undefined" ? document.body : undefined),
    []
  );

  return (
    <div className="ag-theme-quartz" style={{ width: "100%", height: "calc(100vh - 290px)", minHeight: 380 }}>
      <AgGridReact<SugeridoRow>
        ref={gridRef}
        rowData={rows}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        popupParent={popupParent}
        onGridReady={onGridReady}
        onFirstDataRendered={onFirstDataRendered}
        onRowDataUpdated={onRowDataUpdated}
        onFilterChanged={onFilterChanged}
        onSortChanged={onSortChanged}
        onColumnMoved={onColumnMoved}
        onColumnResized={onColumnResized}
        onPaginationChanged={onPaginationChanged}
        onCellContextMenu={onCellContextMenu}
        onRowClicked={(e: RowClickedEvent<SugeridoRow>) => {
          if (!e.data) return;
          if (e.data.origen === "catalogo" || e.data.origen === "manual") {
            router.push(`/catalogo/${encodeURIComponent(e.data.producto)}`);
            return;
          }
          onRowClick(e.data);
        }}
        getRowClass={() => "cursor-pointer"}
        pagination
        paginationPageSize={50}
        paginationPageSizeSelector={[50, 100, 200, 500]}
        animateRows
        suppressCellFocus
        overlayNoRowsTemplate="<span class='text-slate-400'>No hay datos para los filtros aplicados</span>"
        localeText={{
          page: "Pagina",
          to: "a",
          of: "de",
          next: "Siguiente",
          previous: "Anterior",
          first: "Primera",
          last: "Ultima",
          noRowsToShow: "Sin datos",
        }}
      />

      {/* Context menu custom (AG Grid Community no incluye uno nativo) */}
      {menu && (
        <>
          <div
            className="fixed inset-0 z-[100]"
            onClick={() => setMenu(null)}
            onContextMenu={(ev) => {
              ev.preventDefault();
              setMenu(null);
            }}
          />
          <div
            className="fixed z-[101] min-w-[160px] overflow-hidden rounded-sm border border-ink-200 bg-white shadow-lift"
            style={{ left: menu.x, top: menu.y }}
          >
            <button
              type="button"
              onClick={copiarValor}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] text-ink-800 hover:bg-paper-100"
            >
              <Copy size={14} className="text-ink-500" /> Copiar
            </button>
          </div>
        </>
      )}

      {/* Toast "Copiado" sobre la celda copiada */}
      {toast && (
        <div
          className="pointer-events-none fixed z-[102] -translate-x-1/2 -translate-y-full rounded-sm bg-ink-900 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-paper shadow-lift"
          style={{ left: toast.x, top: toast.y - 8, animation: "fadeOut 1.2s ease-out forwards" }}
        >
          <span className="inline-flex items-center gap-1">
            <Check size={12} className="text-accent-500" /> Copiado
          </span>
        </div>
      )}

      <style jsx>{`
        @keyframes fadeOut {
          0% { opacity: 0; transform: translate(-50%, -100%) translateY(4px); }
          15% { opacity: 1; transform: translate(-50%, -100%) translateY(0); }
          70% { opacity: 1; }
          100% { opacity: 0; transform: translate(-50%, -100%) translateY(-6px); }
        }
      `}</style>
    </div>
  );
});
