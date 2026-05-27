"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Download, FileSpreadsheet } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { PostVentaMeta } from "@/lib/types";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

/** "202504" -> "Abr 2025" */
function etiquetaPeriodo(yyyymm: string): string {
  if (!yyyymm || yyyymm.length < 6) return yyyymm;
  const anio = yyyymm.slice(0, 4);
  const mes = parseInt(yyyymm.slice(4, 6), 10);
  return `${MESES[mes - 1] ?? yyyymm.slice(4, 6)} ${anio}`;
}

const EXCEL_MAX = 1_048_575;

const selectCls =
  "rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";

export default function ExportarPage() {
  const [meta, setMeta] = useState<PostVentaMeta | null>(null);
  const [errorMeta, setErrorMeta] = useState(false);

  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [sucursal, setSucursal] = useState("");

  const [conteo, setConteo] = useState<number | null>(null);
  const [contando, setContando] = useState(false);
  const [descargando, setDescargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .postVentaMeta()
      .then((m) => {
        setMeta(m);
        if (m.periodos.length > 0) {
          setDesde(m.periodos[0]);
          setHasta(m.periodos[m.periodos.length - 1]);
        }
      })
      .catch(() => setErrorMeta(true));
  }, []);

  const filtros = useMemo(
    () => ({
      periodo_desde: desde || null,
      periodo_hasta: hasta || null,
      sucursal: sucursal || null,
    }),
    [desde, hasta, sucursal]
  );

  useEffect(() => {
    if (!meta || meta.filas === 0) return;
    let activo = true;
    setContando(true);
    const t = setTimeout(() => {
      api
        .postVentaContar(filtros)
        .then((n) => activo && setConteo(n))
        .catch(() => activo && setConteo(null))
        .finally(() => activo && setContando(false));
    }, 250);
    return () => {
      activo = false;
      clearTimeout(t);
    };
  }, [filtros, meta]);

  const descargar = useCallback(async () => {
    setDescargando(true);
    setError(null);
    try {
      await api.exportPostVenta(filtros);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo generar el Excel");
    } finally {
      setDescargando(false);
    }
  }, [filtros]);

  const excedido = conteo !== null && conteo > EXCEL_MAX;
  const sinFilas = conteo === 0;
  const periodoInvalido = Boolean(desde && hasta && desde > hasta);

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">Exportar datos</h1>
        <p className="text-[13px] text-slate-500">
          Descarga en Excel la <b>Planilla Post Venta</b> (año en curso). Filtra por mes y
          sucursal para acotar el archivo.
        </p>
      </div>

      {errorMeta && (
        <Card>
          <CardContent className="text-[13px] text-slate-600">
            No se pudieron cargar los datos. Intenta recargar la página.
          </CardContent>
        </Card>
      )}

      {meta && meta.filas === 0 && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="text-[13px] text-amber-800">
            Aún no hay datos de Post Venta cargados. El administrador debe ejecutar{" "}
            <b>push_to_cloud.ps1</b> con Power BI Desktop abierto para publicarlos.
          </CardContent>
        </Card>
      )}

      {meta && meta.filas > 0 && (
        <>
          <Card>
            <CardContent className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="tabular text-lg font-semibold text-slate-900">
                  {formatoNumero(meta.filas)}
                </p>
                <p className="text-[12px] text-slate-500">filas disponibles</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="tabular text-lg font-semibold text-slate-900">
                  {meta.periodos.length}
                </p>
                <p className="text-[12px] text-slate-500">meses</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3">
                <p className="text-sm font-semibold text-slate-900">
                  {meta.actualizado_en ? formatoFechaHora(meta.actualizado_en) : "—"}
                </p>
                <p className="text-[12px] text-slate-500">última actualización</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileSpreadsheet size={18} className="text-brand" /> Planilla Post Venta
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-3">
                <label className="flex flex-col gap-1 text-[13px] text-slate-600">
                  Desde
                  <select className={selectCls} value={desde} onChange={(e) => setDesde(e.target.value)}>
                    {meta.periodos.map((p) => (
                      <option key={p} value={p}>
                        {etiquetaPeriodo(p)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[13px] text-slate-600">
                  Hasta
                  <select className={selectCls} value={hasta} onChange={(e) => setHasta(e.target.value)}>
                    {meta.periodos.map((p) => (
                      <option key={p} value={p}>
                        {etiquetaPeriodo(p)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[13px] text-slate-600">
                  Sucursal
                  <select
                    className={selectCls}
                    value={sucursal}
                    onChange={(e) => setSucursal(e.target.value)}
                  >
                    <option value="">Todas</option>
                    {meta.sucursales.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="text-[13px] text-slate-600">
                {periodoInvalido ? (
                  <span className="text-amber-700">
                    El mes &ldquo;desde&rdquo; es posterior al &ldquo;hasta&rdquo;.
                  </span>
                ) : contando ? (
                  "Calculando filas…"
                ) : conteo !== null ? (
                  <>
                    Selección: <b className="tabular text-slate-900">{formatoNumero(conteo)}</b> filas
                  </>
                ) : null}
              </div>

              {excedido && (
                <p className="flex items-start gap-2 rounded-md bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
                  <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                  Son demasiadas filas para un Excel (máx {formatoNumero(EXCEL_MAX)}). Acota el mes
                  o elige una sucursal.
                </p>
              )}

              {error && (
                <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
              )}

              <Button
                onClick={descargar}
                disabled={descargando || excedido || sinFilas || periodoInvalido}
                className="w-full"
              >
                <Download size={15} className={descargando ? "animate-pulse" : ""} />
                {descargando ? "Generando Excel…" : "Descargar Excel"}
              </Button>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
