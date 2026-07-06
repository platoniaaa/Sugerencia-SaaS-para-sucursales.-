"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { BarChart3, ChevronDown, Columns3, Download, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { KpiCards } from "@/components/kpi-cards";
import { GraficosDashboard } from "@/components/graficos-dashboard";
import { FiltrosSugerido } from "@/components/filtros-sugerido";
import { TablaSugerido, type TablaSugeridoHandle } from "@/components/tabla-sugerido";
import { ConfigurarColumnas } from "@/components/configurar-columnas";
import { ModalSugerenciaManual } from "@/components/modal-sugerencia-manual";
import { api } from "@/lib/api-client";
import { getEsAdmin } from "@/lib/auth";
import { columnasPorDefectoVista } from "@/lib/columnas";
import { formatoFechaHora, formatoNumero } from "@/lib/formato";
import { STORAGE_KEYS, guardar, leer } from "@/lib/persistencia-dashboard";
import type { Sucursal, SugeridoFiltros, SugeridoKpis, SugeridoRow } from "@/lib/types";

type Vista = NonNullable<SugeridoFiltros["vista"]>;
const VISTAS: { id: Vista; label: string; hint: string }[] = [
  { id: "todas", label: "Todas", hint: "Todo el sugerido sin distinguir el proceso" },
  { id: "sucursales", label: "Compra sucursal", hint: "Lo que cada local pide directo al proveedor" },
  { id: "cd", label: "Compra CD", hint: "Lo que el CD le pide al proveedor para tener en stock central" },
  { id: "distribucion", label: "Distribución CD → Sucursales", hint: "Lo que el CD reparte a las sucursales (traslado interno)" },
];

const LS_COLUMNAS = "sugerido_columnas_visibles";

const FILTROS_DEFAULT: SugeridoFiltros = { solo_pedir: true, vista: "todas" };

// Las columnas se recuerdan por vista: cada pestania del proceso de compras tiene
// su propio set (clave `sugerido_columnas_visibles::<vista>`). Asi "Distribución"
// arranca con el set operativo sin pisar lo que el usuario configuro en "Todas".
function leerColumnasVista(vista: string): string[] {
  if (typeof window === "undefined") return columnasPorDefectoVista(vista);
  try {
    const saved = localStorage.getItem(`${LS_COLUMNAS}::${vista}`);
    if (saved) {
      const arr = JSON.parse(saved);
      if (Array.isArray(arr) && arr.length) return arr;
    }
  } catch {
    /* noop */
  }
  return columnasPorDefectoVista(vista);
}

export default function DashboardPage() {
  const router = useRouter();

  // Lazy init: leemos localStorage (namespaced por email) ANTES del primer render
  // para que el efecto de fetch arranque ya con los filtros buenos. Si guardáramos
  // dentro de un useEffect haríamos 2 fetches (uno con defaults, otro con
  // restaurados).
  const [filtros, setFiltrosRaw] = useState<SugeridoFiltros>(() =>
    leer<SugeridoFiltros>(STORAGE_KEYS.filtros, FILTROS_DEFAULT)
  );

  // Wrapper de setFiltros que persiste sincrónicamente. Si el usuario filtra y
  // navega al detalle en <300ms (más rápido que el debounce de fetch), igual
  // se guarda. Cubre setter como objeto o como función.
  const setFiltros: React.Dispatch<React.SetStateAction<SugeridoFiltros>> = useCallback(
    (updater) => {
      setFiltrosRaw((prev) => {
        const nuevo =
          typeof updater === "function"
            ? (updater as (p: SugeridoFiltros) => SugeridoFiltros)(prev)
            : updater;
        guardar(STORAGE_KEYS.filtros, nuevo);
        return nuevo;
      });
    },
    []
  );

  const [esAdmin, setEsAdmin] = useState(false);

  // Las tabs de vista solo se muestran a admin. Detectamos al montar.
  useEffect(() => {
    setEsAdmin(getEsAdmin());
  }, []);
  const [rows, setRows] = useState<SugeridoRow[]>([]);
  const [kpis, setKpis] = useState<SugeridoKpis | null>(null);
  const [total, setTotal] = useState(0);
  // Fecha/hora de la última carga de datos desde Power BI (para todos los usuarios).
  const [ultimaSync, setUltimaSync] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [proveedores, setProveedores] = useState<string[]>([]);

  const vista = filtros.vista ?? "todas";
  const [colsVisibles, setColsVisibles] = useState<string[]>(() =>
    leerColumnasVista(leer<SugeridoFiltros>(STORAGE_KEYS.filtros, FILTROS_DEFAULT).vista ?? "todas")
  );
  const [modalCols, setModalCols] = useState(false);
  const [modalManual, setModalManual] = useState(false);

  // Ref para recolectar IDs visibles de la grilla cuando se exporta con filtros
  // de columna activos (AG Grid los maneja del lado cliente).
  const tablaRef = useRef<TablaSugeridoHandle>(null);
  // Si el server devolvio mas filas de las que la grilla puede cargar (limit 5000),
  // los KPIs calculados sobre las filas visibles quedarian truncados: en ese caso
  // se piden al backend (que agrega sobre el total) y se ignora el calculo del grid.
  const truncadoRef = useRef(false);
  const [exportando, setExportando] = useState(false);
  const [mostrarGraficos, setMostrarGraficos] = useState(false);
  // El grid notifica si hay filtros de columna activos; usamos esto para que
  // el boton "Limpiar filtros" aparezca tambien cuando los server-side estan
  // en default pero hay filtros aplicados sobre alguna columna de la tabla.
  const [hayFiltrosColumna, setHayFiltrosColumna] = useState(false);

  const limpiarFiltrosTodo = useCallback(() => {
    // Filtros server-side -> default.
    setFiltros((f) => ({
      q: "",
      solo_pedir: true,
      solo_nacionales: false,
      // Mantener la vista que el usuario tiene seleccionada: limpiar filtros
      // no implica cambiar de pestania.
      vista: f.vista ?? "todas",
    }));
    // Filtros de columna del grid.
    tablaRef.current?.limpiarFiltrosColumnas();
  }, [setFiltros]);

  // Al cambiar de vista, cargar las columnas de esa pestania (guardadas o su
  // set por defecto). No persiste: cargar defaults no debe pisar lo guardado.
  useEffect(() => {
    setColsVisibles(leerColumnasVista(vista));
  }, [vista]);

  // Cambios explicitos del usuario (modal de columnas): persisten en la vista actual.
  const cambiarColumnas = useCallback(
    (cols: string[]) => {
      setColsVisibles(cols);
      try {
        localStorage.setItem(`${LS_COLUMNAS}::${vista}`, JSON.stringify(cols));
      } catch {
        /* noop */
      }
    },
    [vista]
  );

  // Fecha/hora de la última sincronización de datos desde Power BI.
  useEffect(() => {
    api
      .ultimaSincronizacion()
      .then((r) => setUltimaSync(r.creado_en))
      .catch(() => {
        /* el backend puede no estar arriba todavia */
      });
  }, []);

  // Cargar catalogos una vez (sucursales + proveedores).
  useEffect(() => {
    (async () => {
      try {
        const sucs = await api.sucursales();
        setSucursales(sucs);
        // Proveedores: distinct de un fetch amplio sin filtro.
        const todo = await api.sugerido({ solo_pedir: false }, { limit: 5000 });
        const set = new Set<string>();
        todo.items.forEach((r) => r.proveedor && set.add(r.proveedor));
        setProveedores([...set].sort());
      } catch {
        /* el backend puede no estar arriba todavia */
      }
    })();
  }, []);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      // KPIs: los calcula la grilla sobre las filas visibles tras los filtros de
      // columna (ver onKpisVisiblesChange abajo)... salvo que el resultado exceda
      // el limite de 5000 filas: ahi la grilla veria un subconjunto y los KPIs
      // saldrian truncados, asi que se piden al backend (agrega sobre el total).
      const page = await api.sugerido(filtros, { limit: 5000, sort: "-total_sugerido_suc" });
      setRows(page.items);
      setTotal(page.total);
      const estaTruncado = page.total > page.items.length;
      truncadoRef.current = estaTruncado;
      if (estaTruncado) {
        const k = await api.kpis(filtros);
        setKpis(k);
      }
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
      // Recolectamos los IDs visibles del AG Grid (respeta cualquier filtro de
      // columna que el usuario haya aplicado en la tabla). Si la grilla aun no
      // esta montada, ids queda vacio y el backend usa los filtros server-side.
      const ids = tablaRef.current?.obtenerIdsVisibles() ?? [];
      await api.exportExcel(
        filtros,
        colsVisibles,
        "-total_sugerido_suc",
        ids.length ? ids : undefined
      );
    } catch (e) {
      alert(e instanceof Error ? e.message : "No se pudo exportar");
    } finally {
      setExportando(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="kicker mb-1">Reposición</p>
          <h1 className="editorial-rule font-display text-[28px] font-medium leading-none tracking-tight text-ink-900">
            Sugerido de compras
          </h1>
          <p className="mt-3 text-[13px] text-ink-500">
            {cargando ? "Cargando…" : `${formatoNumero(total)} filas`}
            {total > rows.length &&
              ` (mostrando ${formatoNumero(rows.length)} — los KPIs cubren el total; el Excel exporta solo lo visible)`}
          </p>
          {ultimaSync && (
            <p className="mt-1 text-[12px] text-ink-400">
              Datos actualizados el {formatoFechaHora(ultimaSync)}
            </p>
          )}
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

      {esAdmin && (
        <div className="flex flex-wrap gap-1 border-b border-ink-200">
          {VISTAS.map((v) => {
            const activa = (filtros.vista ?? "todas") === v.id;
            return (
              <button
                key={v.id}
                onClick={() => setFiltros((f) => ({ ...f, vista: v.id }))}
                title={v.hint}
                className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] font-medium transition-colors ${
                  activa
                    ? "border-accent-700 text-ink-900"
                    : "border-transparent text-ink-500 hover:text-ink-900"
                }`}
              >
                {v.label}
              </button>
            );
          })}
        </div>
      )}

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
        hayFiltrosColumna={hayFiltrosColumna}
        onLimpiarTodo={limpiarFiltrosTodo}
      />

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
          {error}
        </div>
      )}

      <TablaSugerido
        ref={tablaRef}
        rows={rows}
        columnasVisibles={colsVisibles}
        vista={filtros.vista ?? "todas"}
        onKpisVisiblesChange={(k) => {
          // Con resultado truncado mandan los KPIs del backend (cubren el total).
          if (!truncadoRef.current) setKpis(k);
        }}
        onFiltrosColumnaChange={setHayFiltrosColumna}
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
        onChange={cambiarColumnas}
      />
      <ModalSugerenciaManual
        open={modalManual}
        onClose={() => setModalManual(false)}
        onGuardado={cargar}
        sucursales={sucursales}
        proveedores={proveedores}
      />
    </div>
  );
}
