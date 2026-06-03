"use client";

import { forwardRef, useImperativeHandle, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, GridReadyEvent, IRowNode, RowClickedEvent } from "ag-grid-community";
import { COLUMNAS, type DefColumna } from "@/lib/columnas";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import type { SugeridoRow } from "@/lib/types";
import { FiltroMultiSelect } from "@/components/filtro-multiselect";

interface Props {
  rows: SugeridoRow[];
  columnasVisibles: string[];
  onRowClick: (row: SugeridoRow) => void;
}

export interface TablaSugeridoHandle {
  /** IDs de las filas visibles tras filtros y orden del AG Grid. Solo del BI (id > 0). */
  obtenerIdsVisibles(): number[];
  /** true si el usuario aplico algun filtro de columna en la tabla. */
  hayFiltrosTabla(): boolean;
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
    // Filtro custom multi-select (estilo Excel / D365) en TODAS las columnas — ver
    // defaultColDef más abajo. Aquí no se sobreescribe.
    minWidth: def.tipo === "texto" ? 140 : 110,
    flex: def.key === "descripcion" ? 2 : undefined,
  };

  // Para la columna "producto" agregamos un badge "Catálogo" cuando origen === "catalogo".
  // AG Grid >= 32 escapa strings desde cellRenderer; hay que devolver JSX para HTML real.
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

export const TablaSugerido = forwardRef<TablaSugeridoHandle, Props>(function TablaSugerido(
  { rows, columnasVisibles, onRowClick },
  ref
) {
  const gridRef = useRef<AgGridReact<SugeridoRow>>(null);
  const router = useRouter();

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
      hayFiltrosTabla: () => Boolean(gridRef.current?.api?.isAnyFilterPresent()),
    }),
    []
  );

  const columnDefs = useMemo<ColDef[]>(() => {
    // Mantener el orden definido en COLUMNAS, solo las visibles.
    return COLUMNAS.filter((c) => columnasVisibles.includes(c.key as string)).map(colDef);
  }, [columnasVisibles]);

  const defaultColDef = useMemo<ColDef>(
    () => ({
      sortable: true,
      resizable: true,
      suppressHeaderMenuButton: false,
      filter: FiltroMultiSelect,
      // Solo la pestaña de filtro (sin las otras del menú por defecto) → al clickear
      // el icono se abre directo el multiselect.
      menuTabs: ["filterMenuTab"],
    }),
    []
  );

  const onGridReady = (e: GridReadyEvent) => {
    e.api.sizeColumnsToFit();
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
        onRowClicked={(e: RowClickedEvent<SugeridoRow>) => {
          if (!e.data) return;
          // Manual-pura: producto sin sugerido del BI. Lo mandamos al detalle del catalogo.
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
