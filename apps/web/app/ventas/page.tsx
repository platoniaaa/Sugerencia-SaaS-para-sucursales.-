"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  Columns3,
  Download,
  LayoutList,
  RefreshCw,
  Search,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoCLPCorto, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type {
  PostVentaMeta,
  VentaLinea,
  VentasKpis,
  VentasMes,
  VentasPorSucursal,
} from "@/lib/types";
import { TablaVentas } from "@/components/tabla-ventas";
import { ConfigurarColumnasVentas } from "@/components/configurar-columnas-ventas";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

function etiquetaPeriodo(yyyymm: string): string {
  if (!yyyymm || yyyymm.length < 6) return yyyymm;
  const anio = yyyymm.slice(0, 4);
  const mes = parseInt(yyyymm.slice(4, 6), 10);
  return `${MESES[mes - 1] ?? yyyymm.slice(4, 6)} ${anio}`;
}

function etiquetaCorta(yyyymm: string): string {
  if (!yyyymm || yyyymm.length < 6) return yyyymm;
  const mes = parseInt(yyyymm.slice(4, 6), 10);
  const anio = yyyymm.slice(2, 4);
  return `${MESES[mes - 1] ?? ""} ${anio}`;
}

const EXCEL_MAX = 1_048_575;
const LIMIT_GRILLA = 2000;
const STORAGE_COLS = "ventas_cols_visibles";

const COLS_DEFAULT = [
  "Periodo",
  "Fecha",
  "tipoDocto",
  "Numero",
  "SUCURSAL",
  "Producto",
  "Descripcion Producto",
  "Cantidad",
  "Total Neta",
  "Marca",
  "Tipo Cliente",
];

type Tab = "detalle" | "resumen";

export default function VentasPage() {
  const [tab, setTab] = useState<Tab>("detalle");
  const [meta, setMeta] = useState<PostVentaMeta | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.postVentaMeta().then(setMeta).catch(() => setError("No se pudo cargar metadatos"));
  }, []);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "detalle", label: "Detalle", icon: <LayoutList size={15} /> },
    { id: "resumen", label: "Resumen", icon: <BarChart3 size={15} /> },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="kicker mb-1">Operación</p>
          <h1 className="editorial-rule font-display text-[28px] font-medium leading-none tracking-tight text-ink-900">
            Ventas
          </h1>
          <p className="mt-3 text-[13px] text-ink-500">
            {meta && (
              <>
                {formatoNumero(meta.filas)} líneas · {meta.periodos.length} mes
                {meta.periodos.length === 1 ? "" : "es"} · actualizado{" "}
                <b className="font-mono">
                  {meta.actualizado_en ? formatoFechaHora(meta.actualizado_en) : "—"}
                </b>
              </>
            )}
          </p>
        </div>
      </div>

      {error && (
        <p className="rounded-sm border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {error}
        </p>
      )}

      <div className="flex gap-1 border-b border-ink-200">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] font-medium transition-colors ${
              tab === t.id
                ? "border-accent-700 text-ink-900"
                : "border-transparent text-ink-500 hover:text-ink-900"
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {tab === "detalle" && <SeccionDetalle meta={meta} />}
      {tab === "resumen" && <SeccionResumen />}
    </div>
  );
}

/* =========================================================
   TAB DETALLE — tabla AG Grid estilo ERP + export
   ========================================================= */
function SeccionDetalle({ meta }: { meta: PostVentaMeta | null }) {
  const [busqueda, setBusqueda] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [sucursal, setSucursal] = useState("");
  const [rows, setRows] = useState<VentaLinea[]>([]);
  const [columnas, setColumnas] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [colsVisibles, setColsVisibles] = useState<string[]>([]);
  const [modalCols, setModalCols] = useState(false);
  const [conteo, setConteo] = useState<number | null>(null);
  const [descargando, setDescargando] = useState(false);

  // Inicializar filtros desde meta (rango completo).
  useEffect(() => {
    if (!meta || meta.periodos.length === 0) return;
    setDesde(meta.periodos[meta.periodos.length - 1]); // por defecto mes mas reciente
    setHasta(meta.periodos[meta.periodos.length - 1]);
  }, [meta]);

  // Restaurar columnas visibles desde localStorage.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = localStorage.getItem(STORAGE_COLS);
    if (saved) {
      try {
        const arr = JSON.parse(saved);
        if (Array.isArray(arr) && arr.length > 0) {
          setColsVisibles(arr);
          return;
        }
      } catch {}
    }
    setColsVisibles(COLS_DEFAULT);
  }, []);

  // Guardar columnas visibles.
  useEffect(() => {
    if (typeof window === "undefined" || colsVisibles.length === 0) return;
    localStorage.setItem(STORAGE_COLS, JSON.stringify(colsVisibles));
  }, [colsVisibles]);

  const filtros = useMemo(
    () => ({
      periodo_desde: desde || undefined,
      periodo_hasta: hasta || undefined,
      sucursal: sucursal || undefined,
      q: busqueda || undefined,
    }),
    [desde, hasta, sucursal, busqueda]
  );

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const r = await api.ventasLineas(filtros, { page: 1, limit: LIMIT_GRILLA });
      setRows(r.items);
      setTotal(r.total);
      setColumnas(r.columnas);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setCargando(false);
    }
  }, [filtros]);

  useEffect(() => {
    const t = setTimeout(cargar, 300);
    return () => clearTimeout(t);
  }, [cargar]);

  // Conteo para el boton "Exportar" (cuantas se descargarian).
  useEffect(() => {
    if (!meta) return;
    api
      .postVentaContar({
        periodo_desde: desde || null,
        periodo_hasta: hasta || null,
        sucursal: sucursal || null,
      })
      .then(setConteo)
      .catch(() => setConteo(null));
  }, [desde, hasta, sucursal, meta]);

  const descargar = async () => {
    setDescargando(true);
    try {
      await api.exportPostVenta({
        periodo_desde: desde || null,
        periodo_hasta: hasta || null,
        sucursal: sucursal || null,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo generar el Excel");
    } finally {
      setDescargando(false);
    }
  };

  const excedido = conteo !== null && conteo > EXCEL_MAX;

  if (!meta) {
    return <p className="text-ink-500">Cargando…</p>;
  }
  if (meta.filas === 0) {
    return (
      <div className="rounded-sm border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
        Aún no hay datos de Post Venta cargados. Ejecutá la sincronización con Power BI
        Desktop abierto.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-[13px] text-ink-600">
          {cargando ? "Cargando…" : `${formatoNumero(total)} líneas`}
          {total > rows.length && ` (mostrando ${formatoNumero(rows.length)})`}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={cargar}
            className="inline-flex items-center gap-1.5 rounded-sm border border-ink-200 bg-white px-3 py-1.5 text-[13px] hover:bg-paper-100"
          >
            <RefreshCw size={14} /> Actualizar
          </button>
          <button
            onClick={() => setModalCols(true)}
            className="inline-flex items-center gap-1.5 rounded-sm border border-ink-200 bg-white px-3 py-1.5 text-[13px] hover:bg-paper-100"
          >
            <Columns3 size={14} /> Columnas
          </button>
          <button
            onClick={descargar}
            disabled={descargando || excedido}
            className="inline-flex items-center gap-1.5 rounded-sm bg-ink-900 px-3 py-1.5 text-[13px] font-semibold uppercase tracking-wider text-paper transition-colors hover:bg-accent-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Download size={14} className={descargando ? "animate-pulse" : ""} />
            {descargando ? "Generando…" : "Exportar Excel"}
          </button>
        </div>
      </div>

      {/* Filtros */}
      <div className="rounded-sm border border-ink-200 bg-white p-3 shadow-card">
        <div className="grid gap-3 sm:grid-cols-4">
          <FieldText
            label="Buscar"
            icon={<Search size={14} />}
            value={busqueda}
            onChange={setBusqueda}
            placeholder="Producto, descripción, cliente…"
          />
          <FieldSelect
            label="Desde"
            value={desde}
            onChange={setDesde}
            options={meta.periodos.map((p) => ({ value: p, label: etiquetaPeriodo(p) }))}
          />
          <FieldSelect
            label="Hasta"
            value={hasta}
            onChange={setHasta}
            options={meta.periodos.map((p) => ({ value: p, label: etiquetaPeriodo(p) }))}
          />
          <FieldSelect
            label="Sucursal"
            value={sucursal}
            onChange={setSucursal}
            options={[
              { value: "", label: "Todas" },
              ...meta.sucursales.map((s) => ({ value: s, label: s })),
            ]}
          />
        </div>
        {excedido && (
          <p className="mt-3 flex items-start gap-2 rounded-sm border border-amber-200 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-800">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            La selección excede el máximo de Excel ({formatoNumero(EXCEL_MAX)} filas). Acotá
            el rango o elegí una sucursal para descargar.
          </p>
        )}
        {!excedido && conteo !== null && (
          <p className="mt-2 text-[12px] text-ink-500">
            Al exportar se descargarán <b className="text-ink-800">{formatoNumero(conteo)}</b>{" "}
            líneas. (La tabla de arriba muestra hasta {formatoNumero(LIMIT_GRILLA)} para ser
            ágil.)
          </p>
        )}
      </div>

      {error && (
        <p className="rounded-sm border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {error}
        </p>
      )}

      <TablaVentas rows={rows} columnasVisibles={colsVisibles} columnasOrden={columnas} />

      <ConfigurarColumnasVentas
        open={modalCols}
        onClose={() => setModalCols(false)}
        todas={columnas}
        visibles={colsVisibles}
        defaultCols={COLS_DEFAULT}
        onChange={setColsVisibles}
      />
    </div>
  );
}

/* =========================================================
   TAB RESUMEN — KPIs + gráfico + tabla por sucursal
   ========================================================= */
function SeccionResumen() {
  const [kpis, setKpis] = useState<VentasKpis | null>(null);
  const [serie, setSerie] = useState<VentasMes[]>([]);
  const [porSucursal, setPorSucursal] = useState<VentasPorSucursal | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.ventasKpis(), api.ventasMensual(12), api.ventasPorSucursal()])
      .then(([k, s, ps]) => {
        setKpis(k);
        setSerie(s);
        setPorSucursal(ps);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error"));
  }, []);

  if (error) {
    return (
      <p className="rounded-sm border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
        {error}
      </p>
    );
  }
  if (!kpis) return <p className="text-ink-500">Cargando…</p>;

  const serieParaGrafico = serie.map((m) => ({ ...m, etiqueta: etiquetaCorta(m.periodo) }));

  return (
    <div className="space-y-5">
      {kpis.periodo_actual && (
        <>
          <p className="kicker">Mes en curso · {etiquetaPeriodo(kpis.periodo_actual)}</p>
          <div className="grid grid-cols-2 gap-px bg-ink-200 lg:grid-cols-4">
            <KpiCard
              index="01"
              label="Venta CLP"
              valor={formatoCLPCorto(kpis.actual.clp)}
              variacion={kpis.var_clp_pct}
              acento
            />
            <KpiCard
              index="02"
              label="Unidades"
              valor={formatoNumero(kpis.actual.unidades)}
              variacion={kpis.var_unidades_pct}
            />
            <KpiCard
              index="03"
              label="Líneas / transacciones"
              valor={formatoNumero(kpis.actual.n_lineas)}
            />
            <KpiCard
              index="04"
              label={`Mes anterior · ${
                kpis.periodo_anterior ? etiquetaPeriodo(kpis.periodo_anterior) : "—"
              }`}
              valor={formatoCLPCorto(kpis.anterior.clp)}
            />
          </div>
        </>
      )}

      {serieParaGrafico.length > 0 && (
        <div className="rounded-sm border border-ink-200 bg-white shadow-card">
          <div className="border-b border-ink-100 px-5 py-3">
            <p className="kicker">Histórico</p>
            <h2 className="font-display text-[16px] font-medium text-ink-900">
              Venta mensual ({serieParaGrafico.length} meses)
            </h2>
          </div>
          <div className="p-3">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={serieParaGrafico} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ebe9dd" vertical={false} />
                <XAxis
                  dataKey="etiqueta"
                  tick={{ fontSize: 11, fill: "#57534e" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "#a8a29e" }}
                  axisLine={false}
                  tickLine={false}
                  width={56}
                  tickFormatter={(v: number) => formatoCLPCorto(v)}
                />
                <Tooltip
                  formatter={(v: number) => [formatoCLP(v), "CLP"]}
                  cursor={{ fill: "#fff7ed" }}
                  contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #ebe9dd" }}
                />
                <Legend iconType="square" wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                <Bar
                  dataKey="clp"
                  name="CLP"
                  fill="#1e40af"
                  radius={[2, 2, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {porSucursal && porSucursal.items.length > 0 && (
        <div className="rounded-sm border border-ink-200 bg-white shadow-card">
          <div className="border-b border-ink-100 px-5 py-3">
            <p className="kicker">Detalle</p>
            <h2 className="font-display text-[16px] font-medium text-ink-900">
              Por sucursal · {etiquetaPeriodo(porSucursal.periodo ?? "")}
            </h2>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-paper-100 text-left text-xs uppercase tracking-wider text-ink-500">
              <tr>
                <th className="px-5 py-2">Sucursal</th>
                <th className="px-5 py-2 text-right">CLP</th>
                <th className="px-5 py-2 text-right">Unidades</th>
                <th className="px-5 py-2 text-right">Líneas</th>
              </tr>
            </thead>
            <tbody>
              {porSucursal.items.map((s) => (
                <tr key={s.sucursal} className="border-t border-ink-100 hover:bg-paper-100/50">
                  <td className="px-5 py-2 font-medium text-ink-900">{s.sucursal}</td>
                  <td className="px-5 py-2 text-right tabular font-semibold">
                    {formatoCLP(s.clp)}
                  </td>
                  <td className="px-5 py-2 text-right tabular">{formatoNumero(s.unidades)}</td>
                  <td className="px-5 py-2 text-right tabular text-ink-500">
                    {formatoNumero(s.n_lineas)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function KpiCard({
  index,
  label,
  valor,
  variacion,
  acento,
}: {
  index: string;
  label: string;
  valor: string;
  variacion?: number | null;
  acento?: boolean;
}) {
  const positivo = variacion !== null && variacion !== undefined && variacion >= 0;
  return (
    <div className="group relative overflow-hidden border border-ink-200 bg-white p-5 transition-colors hover:border-ink-300">
      <span className="absolute left-5 top-4 font-mono text-[10px] text-ink-400">{index}</span>
      <p className="kicker mt-6">{label}</p>
      <p
        className={`figure mt-2 text-[28px] leading-none ${
          acento ? "text-accent-700" : "text-ink-900"
        }`}
      >
        {valor}
      </p>
      {variacion !== null && variacion !== undefined && (
        <p
          className={`mt-2 inline-flex items-center gap-1 text-[12px] font-semibold ${
            positivo ? "text-emerald-700" : "text-red-600"
          }`}
        >
          {positivo ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
          {Math.abs(variacion).toFixed(1)}% vs mes anterior
        </p>
      )}
      <span
        className={`absolute bottom-0 left-0 h-px transition-all ${
          acento ? "w-12 bg-accent-700" : "w-8 bg-ink-300 group-hover:w-16"
        }`}
      />
    </div>
  );
}

function FieldSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="kicker">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-sm border border-ink-200 bg-white px-3 py-2 text-[13px] text-ink-900 focus:border-accent-700 focus:outline-none focus:ring-2 focus:ring-accent-700/30"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function FieldText({
  label,
  icon,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  icon?: React.ReactNode;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="kicker">{label}</span>
      <div className="relative">
        {icon && (
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-400">
            {icon}
          </span>
        )}
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={`w-full rounded-sm border border-ink-200 bg-white py-2 text-[13px] text-ink-900 placeholder:text-ink-400 focus:border-accent-700 focus:outline-none focus:ring-2 focus:ring-accent-700/30 ${
            icon ? "pl-8 pr-3" : "px-3"
          }`}
        />
      </div>
    </label>
  );
}
