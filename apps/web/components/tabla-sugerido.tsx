"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import type {
  ColDef,
  ColumnState,
  FirstDataRenderedEvent,
  GridReadyEvent,
  IRowNode,
  RowClickedEvent,
} from "ag-grid-community";
import { COLUMNAS, type DefColumna } from "@/lib/columnas";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import { STORAGE_KEYS, guardar, leer } from "@/lib/persistencia-dashboard";
import type { SugeridoFiltros, SugeridoRow } from "@/lib/types";
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
  { rows, columnasVisibles, vista, onRowClick },
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
  };

  // Eventos que persisten cambios del usuario:

  const onFilterChanged = () => {
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current || aplicandoRef.current) return;
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
    </div>
  );
});
