"use client";

import { useMemo, useRef } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, GridReadyEvent } from "ag-grid-community";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import type { VentaLinea } from "@/lib/types";
import { FiltroMultiSelect } from "@/components/filtro-multiselect";

const COLS_NUMERICAS = new Set([
  "Cantidad",
  "Neto",
  "Total",
  "Total Neta",
  "Items",
  "Costo Neto",
]);

const COLS_CLP = new Set(["Neto", "Total", "Total Neta", "Costo Neto"]);

interface Props {
  rows: VentaLinea[];
  columnasVisibles: string[];
  columnasOrden: string[]; // orden global tal cual vino del backend
}

function colDef(nombre: string): ColDef {
  const numerica = COLS_NUMERICAS.has(nombre);
  const clp = COLS_CLP.has(nombre);
  const base: ColDef = {
    field: nombre,
    headerName: nombre,
    sortable: true,
    resizable: true,
    minWidth: numerica ? 110 : 140,
    flex: nombre === "Descripcion Producto" || nombre === "Razón Social" ? 2 : undefined,
  };
  if (numerica) {
    base.cellClass = "tabular text-right";
    base.valueFormatter = (p) => {
      const v = p.value;
      if (v === null || v === undefined || v === "") return "—";
      const n = typeof v === "number" ? v : parseFloat(String(v).replace(/\./g, "").replace(",", "."));
      if (Number.isNaN(n)) return String(v);
      return clp ? formatoCLP(n) : formatoNumero(n, 0);
    };
  }
  return base;
}

export function TablaVentas({ rows, columnasVisibles, columnasOrden }: Props) {
  const gridRef = useRef<AgGridReact<VentaLinea>>(null);

  const columnDefs = useMemo<ColDef[]>(() => {
    // Mantener el orden global del backend, solo las visibles.
    return columnasOrden.filter((c) => columnasVisibles.includes(c)).map(colDef);
  }, [columnasVisibles, columnasOrden]);

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

  const popupParent = useMemo<HTMLElement | undefined>(
    () => (typeof document !== "undefined" ? document.body : undefined),
    []
  );

  const onGridReady = (e: GridReadyEvent) => {
    e.api.sizeColumnsToFit();
  };

  return (
    <div className="ag-theme-quartz" style={{ width: "100%", height: "calc(100vh - 320px)", minHeight: 380 }}>
      <AgGridReact<VentaLinea>
        ref={gridRef}
        rowData={rows}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        popupParent={popupParent}
        onGridReady={onGridReady}
        pagination
        paginationPageSize={50}
        paginationPageSizeSelector={[50, 100, 200, 500]}
        animateRows
        suppressCellFocus
        overlayNoRowsTemplate="<span class='text-ink-400'>Sin líneas para los filtros aplicados</span>"
        localeText={{
          page: "Pagina", to: "a", of: "de", next: "Siguiente",
          previous: "Anterior", first: "Primera", last: "Ultima",
          noRowsToShow: "Sin datos",
        }}
      />
    </div>
  );
}
