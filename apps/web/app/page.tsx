"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { BarChart3, ChevronDown, Columns3, Download, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { KpiCards } from "@/components/kpi-cards";
import { GraficosDashboard } from "@/components/graficos-dashboard";
import { FiltrosSugerido } from "@/components/filtros-sugerido";
import { TablaSugerido } from "@/components/tabla-sugerido";
import { ConfigurarColumnas } from "@/components/configurar-columnas";
import { ModalSugerenciaManual } from "@/components/modal-sugerencia-manual";
import { api } from "@/lib/api-client";
import { KEYS_POR_DEFECTO } from "@/lib/columnas";
import { formatoNumero } from "@/lib/formato";
import type { Sucursal, SugeridoFiltros, SugeridoKpis, SugeridoRow } from "@/lib/types";

const LS_COLUMNAS = "sugerido_columnas_visibles";

export default function DashboardPage() {
  const router = useRouter();

  const [filtros, setFiltros] = useState<SugeridoFiltros>({ solo_pedir: true });
  const [rows, setRows] = useState<SugeridoRow[]>([]);
  const [kpis, setKpis] = useState<SugeridoKpis | null>(null);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [marcas, setMarcas] = useState<string[]>([]);

  const [colsVisibles, setColsVisibles] = useState<string[]>(KEYS_POR_DEFECTO);
  const [modalCols, setModalCols] = useState(false);
  const [modalManual, setModalManual] = useState(false);
  const [exportando, setExportando] = useState(false);
  const [mostrarGraficos, setMostrarGraficos] = useState(false);

  // Restaurar columnas desde localStorage.
  useEffect(() => {
    const saved = localStorage.getItem(LS_COLUMNAS);
    if (saved) {
      try {
        const arr = JSON.parse(saved);
        if (Array.isArray(arr) && arr.length) setColsVisibles(arr);
      } catch {
        /* noop */
      }
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(LS_COLUMNAS, JSON.stringify(colsVisibles));
  }, [colsVisibles]);

  // Cargar catalogos una vez (sucursales + marcas).
  useEffect(() => {
    (async () => {
      try {
        const sucs = await api.sucursales();
        setSucursales(sucs);
        // Marcas: distinct de un fetch amplio sin filtro.
        const todo = await api.sugerido({ solo_pedir: false }, { limit: 5000 });
        const set = new Set<string>();
        todo.items.forEach((r) => r.filtro1_final && set.add(r.filtro1_final));
        setMarcas([...set].sort());
      } catch {
        /* el backend puede no estar arriba todavia */
      }
    })();
  }, []);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [page, k] = await Promise.all([
        api.sugerido(filtros, { limit: 5000, sort: "-total_sugerido_suc" }),
        api.kpis(filtros),
      ]);
      setRows(page.items);
      setTotal(page.total);
      setKpis(k);
    } catch (e) {
      setError(
        e instanceof Error
          ? `${e.message}. ¿Esta corriendo el backend en localhost:8000?`
          : "Error al cargar"
      );
    } finally {
      setCargando(false);
    }
  }, [filtros]);

  // Recargar al cambiar filtros (con debounce para texto).
  useEffect(() => {
    const t = setTimeout(cargar, 300);
    return () => clearTimeout(t);
  }, [cargar]);

  const nombresSucursales = useMemo(
    () => sucursales.map((s) => s.nombre ?? s.sucursal_id),
    [sucursales]
  );

  const exportar = async () => {
    setExportando(true);
    try {
      await api.exportExcel(filtros, colsVisibles, "-total_sugerido_suc");
    } catch (e) {
      alert(e instanceof Error ? e.message : "No se pudo exportar");
    } finally {
      setExportando(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">
            Sugerido de compras
          </h1>
          <p className="text-[13px] text-slate-500">
            {cargando ? "Cargando…" : `${formatoNumero(total)} filas`}
            {total > rows.length && ` (mostrando ${formatoNumero(rows.length)})`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={cargar}>
            <RefreshCw size={15} /> Actualizar
          </Button>
          <Button variant="outline" size="sm" onClick={() => setModalCols(true)}>
            <Columns3 size={15} /> Columnas
          </Button>
          <Button variant="outline" size="sm" onClick={exportar} disabled={exportando}>
            <Download size={15} /> {exportando ? "Generando…" : "Exportar Excel"}
          </Button>
          <Button size="sm" onClick={() => setModalManual(true)}>
            <Plus size={15} /> Sugerencia manual
          </Button>
        </div>
      </div>

      <KpiCards kpis={kpis} cargando={cargando} />

      <div>
        <button
          onClick={() => setMostrarGraficos((v) => !v)}
          className="flex items-center gap-1.5 text-[13px] font-medium text-slate-600 hover:text-slate-900"
        >
          <BarChart3 size={15} />
          {mostrarGraficos ? "Ocultar gráficos" : "Ver gráficos"}
          <ChevronDown
            size={15}
            className={mostrarGraficos ? "rotate-180 transition-transform" : "transition-transform"}
          />
        </button>
        {mostrarGraficos && (
          <div className="mt-3">
            <GraficosDashboard filtros={filtros} />
          </div>
        )}
      </div>

      <FiltrosSugerido
        filtros={filtros}
        onChange={setFiltros}
        sucursales={nombresSucursales}
        marcas={marcas}
      />

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
          {error}
        </div>
      )}

      <TablaSugerido
        rows={rows}
        columnasVisibles={colsVisibles}
        onRowClick={(r) =>
          router.push(
            `/producto/${encodeURIComponent(r.producto)}?sucursal=${encodeURIComponent(
              r.sucursal_id
            )}`
          )
        }
      />

      <ConfigurarColumnas
        open={modalCols}
        onClose={() => setModalCols(false)}
        visibles={colsVisibles}
        onChange={setColsVisibles}
      />
      <ModalSugerenciaManual
        open={modalManual}
        onClose={() => setModalManual(false)}
        onGuardado={cargar}
        sucursales={sucursales}
        marcas={marcas}
      />
    </div>
  );
}
