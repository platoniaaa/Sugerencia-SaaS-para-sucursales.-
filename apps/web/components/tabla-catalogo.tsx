"use client";

import { useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, GridReadyEvent, RowClickedEvent } from "ag-grid-community";
import { COLUMNAS_CAT, type DefColCat } from "@/lib/columnas-catalogo";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import type { CatalogoRow } from "@/lib/types";
import { FiltroMultiSelect } from "@/components/filtro-multiselect";

interface Props {
  rows: CatalogoRow[];
  columnasVisibles: string[];
}

function formateador(def: DefColCat) {
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

function colDef(def: DefColCat): ColDef {
  const numerica = def.tipo !== "texto";
  const base: ColDef = {
    field: def.key as string,
    headerName: def.label,
    pinned: def.pin,
    sortable: true,
    resizable: true,
    minWidth: def.tipo === "texto" ? 140 : 110,
    flex: def.key === "glosa" ? 2 : undefined,
  };
  if (numerica) {
    base.type = "rightAligned";
    base.cellClass = "tabular";
    base.valueFormatter = formateador(def);
    if (def.key === "stock_total") base.cellClass = "tabular font-semibold";
  }
  return base;
}

export function TablaCatalogo({ rows, columnasVisibles }: Props) {
  const gridRef = useRef<AgGridReact<CatalogoRow>>(null);
  const router = useRouter();

  const columnDefs = useMemo<ColDef[]>(
    () => COLUMNAS_CAT.filter((c) => columnasVisibles.includes(c.key as string)).map(colDef),
    [columnasVisibles]
  );

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
    <div className="ag-theme-quartz" style={{ width: "100%", height: "calc(100vh - 290px)", minHeight: 380 }}>
      <AgGridReact<CatalogoRow>
        ref={gridRef}
        rowData={rows}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        popupParent={popupParent}
        onGridReady={onGridReady}
        onRowClicked={(e: RowClickedEvent<CatalogoRow>) => {
          if (e.data) router.push(`/catalogo/${encodeURIComponent(e.data.producto)}`);
        }}
        rowClass="cursor-pointer"
        pagination
        paginationPageSize={50}
        paginationPageSizeSelector={[50, 100, 200, 500]}
        animateRows
        suppressCellFocus
        overlayNoRowsTemplate="<span class='text-slate-400'>Sin productos para los filtros aplicados</span>"
        localeText={{
          page: "Pagina", to: "a", of: "de", next: "Siguiente",
          previous: "Anterior", first: "Primera", last: "Ultima",
          noRowsToShow: "Sin datos",
        }}
      />
    </div>
  );
}
