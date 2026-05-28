"use client";

import { useMemo, useRef } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, GridReadyEvent, RowClickedEvent } from "ag-grid-community";
import { COLUMNAS, type DefColumna } from "@/lib/columnas";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import type { SugeridoRow } from "@/lib/types";
import { FiltroMultiSelect } from "@/components/filtro-multiselect";

interface Props {
  rows: SugeridoRow[];
  columnasVisibles: string[];
  onRowClick: (row: SugeridoRow) => void;
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

export function TablaSugerido({ rows, columnasVisibles, onRowClick }: Props) {
  const gridRef = useRef<AgGridReact<SugeridoRow>>(null);

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

  return (
    <div className="ag-theme-quartz" style={{ width: "100%", height: "calc(100vh - 290px)", minHeight: 380 }}>
      <AgGridReact<SugeridoRow>
        ref={gridRef}
        rowData={rows}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        onGridReady={onGridReady}
        onRowClicked={(e: RowClickedEvent<SugeridoRow>) => e.data && onRowClick(e.data)}
        rowClass="cursor-pointer"
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
}
