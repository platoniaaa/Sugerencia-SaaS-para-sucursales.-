"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, colorABC } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ModalSugerenciaManual } from "@/components/modal-sugerencia-manual";
import { GraficoStock } from "@/components/grafico-stock";
import { GraficoComposicion } from "@/components/grafico-composicion";
import { GraficoVentas } from "@/components/grafico-ventas";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { Sucursal, SugerenciaManual, SugeridoRow } from "@/lib/types";

function Dato({
  label,
  valor,
  tooltip,
}: {
  label: string;
  valor: React.ReactNode;
  tooltip?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-slate-100 py-2 last:border-0">
      <span className="text-[13px] text-slate-500" title={tooltip}>
        {label}
        {tooltip && <span className="ml-1 cursor-help text-slate-300">ⓘ</span>}
      </span>
      <span className="tabular text-sm font-medium text-slate-900">{valor}</span>
    </div>
  );
}

export function VistaDetalleProducto({
  producto,
  sucursalId,
}: {
  producto: string;
  sucursalId: string;
}) {
  const [d, setD] = useState<SugeridoRow | null>(null);
  const [manuales, setManuales] = useState<SugerenciaManual[]>([]);
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [detalle, mans, sucs] = await Promise.all([
        api.detalle(producto, sucursalId) as Promise<SugeridoRow>,
        api.sugerenciasManuales(producto, sucursalId),
        api.sucursales(),
      ]);
      setD(detalle);
      setManuales(mans);
      setSucursales(sucs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    }
  }, [producto, sucursalId]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  if (error) {
    return (
      <div className="space-y-4">
        <Link href="/" className="inline-flex items-center gap-1 text-sm text-brand hover:underline">
          <ArrowLeft size={15} /> Volver al dashboard
        </Link>
        <Card>
          <CardContent className="text-slate-600">
            No se encontro el producto <b>{producto}</b> en la sucursal{" "}
            <b>{sucursalId}</b>. {error}
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!d) return <p className="text-slate-500">Cargando…</p>;

  const stockOptimo =
    (d.demanda_diaria ?? 0) * (5 + (d.lt_efectivo ?? 0)) + (d.stock_seguridad ?? 0);
  const pctStock = stockOptimo > 0 ? Math.min(100, ((d.stock_activo_suc ?? 0) / stockOptimo) * 100) : 0;
  const reemplazos = (d.reemplazos ?? "").split(",").map((s) => s.trim()).filter(Boolean);

  return (
    <div className="space-y-5">
      <Link href="/" className="inline-flex items-center gap-1 text-sm text-brand hover:underline">
        <ArrowLeft size={15} /> Volver al dashboard
      </Link>

      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{d.producto}</h1>
        <Badge className={colorABC(d.clasificacion_abc)}>ABC {d.clasificacion_abc ?? "—"}</Badge>
        {d.proveedor && (
          <Badge className="bg-slate-100 text-slate-600">{d.proveedor}</Badge>
        )}
        {d.nombre_sucursal && (
          <Badge className="bg-brand-50 text-brand">{d.nombre_sucursal}</Badge>
        )}
      </div>
      {d.descripcion && <p className="-mt-3 text-slate-500">{d.descripcion}</p>}

      {/* 3 columnas */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Demanda</CardTitle>
          </CardHeader>
          <CardContent className="py-2">
            <Dato
              label="Demanda Mensual"
              valor={formatoNumero(d.demanda_mensual, 1)}
              tooltip="Promedio de los ultimos 4 o 6 meses segun clasificacion"
            />
            <Dato label="Demanda Diaria" valor={formatoNumero(d.demanda_diaria, 2)} />
            <Dato label="Desv Std Mensual" valor={formatoNumero(d.desv_std_mensual, 2)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Stock</CardTitle>
          </CardHeader>
          <CardContent className="py-2">
            <div className="py-2">
              <div className="mb-1 flex items-baseline justify-between">
                <span className="text-[13px] text-slate-500">Stock Activo Suc</span>
                <span className="tabular text-sm font-medium">
                  {formatoNumero(d.stock_activo_suc)} / {formatoNumero(Math.ceil(stockOptimo))}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-brand"
                  style={{ width: `${pctStock}%` }}
                />
              </div>
            </div>
            <Dato label="Stock en Transito" valor={formatoNumero(d.stock_en_transito_suc)} />
            <Dato label="Stock en CD" valor={formatoNumero(d.stock_en_cd)} />
            <Dato label="Stock de Seguridad" valor={formatoNumero(d.stock_seguridad)} />
            <Dato label="Punto de Pedido" valor={formatoNumero(d.punto_de_pedido)} />
            <div className="pt-3">
              <GraficoStock
                stockActivoMasTransito={(d.stock_activo_suc ?? 0) + (d.stock_en_transito_suc ?? 0)}
                puntoPedido={d.punto_de_pedido ?? 0}
                stockOptimo={stockOptimo}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Lead Time y Compra</CardTitle>
          </CardHeader>
          <CardContent className="py-2">
            <Dato
              label="Lead Time (dias)"
              valor={formatoNumero(d.lead_time_dias)}
              tooltip={d.lt_origen ?? undefined}
            />
            <Dato label="LT Efectivo" valor={formatoNumero(d.lt_efectivo)} />
            <Dato label="Abastece CD" valor={d.abastece_cd ?? "—"} />
            <Dato label="Prioridad CD" valor={formatoNumero(d.prioridad_cd)} />
            <Dato label="Costo Unitario" valor={formatoCLP(d.costo_unitario)} />
            <Dato label="Valor del Sugerido" valor={formatoCLP(d.total_valor_sugerido_clp)} />
          </CardContent>
        </Card>
      </div>

      {/* Banner sugerido */}
      <Card className="border-brand/20 bg-gradient-to-br from-brand-50 to-white">
        <CardContent className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-[13px] font-medium uppercase tracking-wide text-brand">
              Sugerido Total
            </p>
            <p className="tabular text-4xl font-bold text-slate-900">
              {formatoNumero(d.total_sugerido_suc)}{" "}
              <span className="text-lg font-normal text-slate-500">unidades</span>
            </p>
          </div>
          <GraficoComposicion
            traslado={d.sugerido_traslado ?? 0}
            compra={d.sugerido_compra_neto ?? 0}
          />
        </CardContent>
      </Card>

      {/* Tendencia de venta (últimos 12 meses) */}
      <GraficoVentas producto={d.producto} sucursalId={d.sucursal_id} />

      {reemplazos.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Productos equivalentes (reemplazos)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {reemplazos.map((r) => (
                <Badge key={r} className="bg-slate-100 text-slate-600">
                  {r}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Sugerencias manuales */}
      <Card>
        <CardHeader className="flex items-center justify-between">
          <CardTitle>Sugerencias manuales</CardTitle>
          <Button size="sm" onClick={() => setModal(true)}>
            <Plus size={15} /> Agregar
          </Button>
        </CardHeader>
        <CardContent>
          {manuales.length === 0 ? (
            <p className="text-[13px] text-slate-400">
              Aun no hay sugerencias manuales para este producto/sucursal.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {manuales.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-3 py-2">
                  <div>
                    <span className="tabular font-semibold text-slate-900">
                      +{formatoNumero(m.unidades)}
                    </span>{" "}
                    <span className="text-[13px] text-slate-500">{m.motivo ?? "Sin motivo"}</span>
                    <p className="text-[11px] text-slate-400">
                      {m.creado_por} · {formatoFechaHora(m.creado_en)}
                      {m.aprobado && " · aprobada"}
                    </p>
                  </div>
                  <button
                    onClick={async () => {
                      await api.eliminarSugerenciaManual(m.id);
                      cargar();
                    }}
                    className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
                    aria-label="Eliminar"
                  >
                    <Trash2 size={16} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <ModalSugerenciaManual
        open={modal}
        onClose={() => setModal(false)}
        onGuardado={cargar}
        sucursales={sucursales}
        productoInicial={producto}
        sucursalInicial={sucursalId}
        soloIndividual
      />
    </div>
  );
}
