"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Boxes, ChevronDown, ChevronRight, Layers, Repeat, Trash2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";
import { formatoFecha, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { Recurrente, SugerenciaManual } from "@/lib/types";

type Tab = "unicas" | "recurrentes";

// expira_en apunta a la medianoche del día SIGUIENTE a la fecha límite elegida
// (la sugerencia vive todo ese día). Para mostrar la fecha límite inclusive se
// resta un minuto al instante de vencimiento.
function fechaLimite(expiraEn: string): string {
  const d = new Date(expiraEn);
  if (Number.isNaN(d.getTime())) return "—";
  return formatoFecha(new Date(d.getTime() - 60000).toISOString());
}

function BadgeVencimiento({ expiraEn }: { expiraEn: string }) {
  const vencida = new Date(expiraEn).getTime() <= Date.now();
  return vencida ? (
    <Badge className="bg-red-50 text-red-700">vencida — ya no suma</Badge>
  ) : (
    <Badge className="bg-amber-50 text-amber-700">hasta el {fechaLimite(expiraEn)}</Badge>
  );
}

export default function SugerenciasManualesPage() {
  const [tab, setTab] = useState<Tab>("unicas");
  const [unicas, setUnicas] = useState<SugerenciaManual[] | null>(null);
  const [recurrentes, setRecurrentes] = useState<Recurrente[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const [u, r] = await Promise.all([
        api.sugerenciasManuales({ soloUnicas: true }),
        api.recurrentes(),
      ]);
      setUnicas(u);
      setRecurrentes(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const eliminarUnica = async (id: string) => {
    if (!confirm("¿Eliminar esta sugerencia? Se quita de la compra.")) return;
    await api.eliminarSugerenciaManual(id);
    cargar();
  };

  const eliminarLote = async (loteId: string, n: number) => {
    if (
      !confirm(
        `¿Eliminar las ${formatoNumero(n)} sugerencias de esta carga masiva? Esta acción no se puede deshacer.`
      )
    )
      return;
    await api.eliminarLoteSugerencias(loteId);
    cargar();
  };

  const eliminarRecurrente = async (id: string) => {
    if (
      !confirm(
        "¿Eliminar esta recurrencia? Su ajuste vigente dejará de sumar a la compra."
      )
    )
      return;
    await api.eliminarRecurrente(id);
    cargar();
  };

  const tabs: { id: Tab; icon: React.ReactNode; label: string; count: number | null }[] = [
    {
      id: "unicas",
      icon: <Boxes size={15} />,
      label: "Únicas",
      count: unicas?.length ?? null,
    },
    {
      id: "recurrentes",
      icon: <Repeat size={15} />,
      label: "Recurrentes",
      count: recurrentes?.length ?? null,
    },
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">
          Sugerencias manuales
        </h1>
        <p className="text-[13px] text-slate-500">
          Ajustes del equipo que se suman al sugerido del BI. Se crean desde el botón
          “Sugerencia manual” en el dashboard.
        </p>
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] font-medium transition-colors ${
              tab === t.id
                ? "border-brand text-brand"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.icon} {t.label}
            {t.count !== null && (
              <span className="rounded bg-slate-100 px-1.5 py-px text-[10px] text-slate-600">
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
          {error}
        </div>
      )}

      {tab === "unicas" && (
        <SeccionUnicas
          items={unicas}
          onEliminar={eliminarUnica}
          onEliminarLote={eliminarLote}
        />
      )}

      {tab === "recurrentes" && (
        <SeccionRecurrentes
          items={recurrentes}
          onEliminar={eliminarRecurrente}
        />
      )}
    </div>
  );
}

function SeccionUnicas({
  items,
  onEliminar,
  onEliminarLote,
}: {
  items: SugerenciaManual[] | null;
  onEliminar: (id: string) => void;
  onEliminarLote: (loteId: string, n: number) => void;
}) {
  // Separamos en lotes (cargas masivas) e individuales para mostrarlos
  // como cards distintas: el lote se colapsa para no inundar la pantalla
  // con miles de filas.
  const { lotes, individuales } = useMemo(() => {
    const lotesMap = new Map<string, SugerenciaManual[]>();
    const ind: SugerenciaManual[] = [];
    for (const s of items ?? []) {
      if (s.lote_id) {
        const arr = lotesMap.get(s.lote_id) ?? [];
        arr.push(s);
        lotesMap.set(s.lote_id, arr);
      } else {
        ind.push(s);
      }
    }
    // Lote más reciente primero (creado_en del primer item).
    const lotesOrdenados = Array.from(lotesMap.entries()).sort((a, b) => {
      const ta = new Date(a[1][0]?.creado_en ?? 0).getTime();
      const tb = new Date(b[1][0]?.creado_en ?? 0).getTime();
      return tb - ta;
    });
    return { lotes: lotesOrdenados, individuales: ind };
  }, [items]);

  if (items === null) return <p className="text-slate-500">Cargando…</p>;
  if (items.length === 0)
    return (
      <Card>
        <CardContent className="text-[13px] text-slate-500">
          No hay sugerencias únicas vigentes. Para crear una, andá al dashboard, hacé
          click en “Sugerencia manual” y <b>no</b> marqués “Repetir periódicamente”.
        </CardContent>
      </Card>
    );
  return (
    <div className="space-y-2">
      {lotes.map(([loteId, filas]) => (
        <LoteCard
          key={loteId}
          loteId={loteId}
          filas={filas}
          onEliminarLote={onEliminarLote}
          onEliminarUna={onEliminar}
        />
      ))}
      {individuales.map((s) => (
        <Card key={s.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900">{s.producto}</span>
                <span className="text-[13px] text-slate-500">·</span>
                <span className="text-[13px] text-slate-600">{s.sucursal_id}</span>
                <Badge className="bg-emerald-50 text-emerald-700">
                  +{formatoNumero(s.unidades)} u
                </Badge>
                {s.expira_en && <BadgeVencimiento expiraEn={s.expira_en} />}
              </div>
              <p className="mt-1 text-[12px] text-slate-500">
                {s.creado_por && <>{s.creado_por} · </>}
                {formatoFechaHora(s.creado_en)}
                {s.motivo && <> · {s.motivo}</>}
              </p>
            </div>
            <button
              onClick={() => onEliminar(s.id)}
              className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
              aria-label="Eliminar sugerencia"
            >
              <Trash2 size={16} />
            </button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

const EXPANDIDO_MAX = 100;

function LoteCard({
  loteId,
  filas,
  onEliminarLote,
  onEliminarUna,
}: {
  loteId: string;
  filas: SugerenciaManual[];
  onEliminarLote: (loteId: string, n: number) => void;
  onEliminarUna: (id: string) => void;
}) {
  const [expandido, setExpandido] = useState(false);
  const primera = filas[0];
  const totalUnidades = filas.reduce((acc, f) => acc + (f.unidades ?? 0), 0);
  const filasVisibles = expandido ? filas.slice(0, EXPANDIDO_MAX) : [];
  const ocultas = expandido ? filas.length - filasVisibles.length : 0;

  return (
    <Card>
      <CardContent className="py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <button
            onClick={() => setExpandido((v) => !v)}
            className="flex min-w-0 flex-1 items-start gap-2 text-left"
          >
            <span className="mt-0.5 text-slate-400">
              {expandido ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </span>
            <span className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Layers size={14} className="text-brand" />
                <span className="font-semibold text-slate-900">Carga masiva</span>
                <Badge className="bg-brand-50 text-brand">
                  {formatoNumero(filas.length)} productos
                </Badge>
                <Badge className="bg-emerald-50 text-emerald-700">
                  +{formatoNumero(totalUnidades)} u en total
                </Badge>
                {primera?.expira_en && <BadgeVencimiento expiraEn={primera.expira_en} />}
              </div>
              <p className="mt-1 text-[12px] text-slate-500">
                {primera?.creado_por && <>{primera.creado_por} · </>}
                {primera?.creado_en && formatoFechaHora(primera.creado_en)}
                {primera?.motivo && <> · {primera.motivo}</>}
              </p>
            </span>
          </button>
          <button
            onClick={() => onEliminarLote(loteId, filas.length)}
            className="flex items-center gap-1 rounded-md border border-red-200 bg-white px-3 py-1.5 text-[12px] font-medium text-red-600 hover:bg-red-50"
          >
            <Trash2 size={14} /> Eliminar las {formatoNumero(filas.length)}
          </button>
        </div>

        {expandido && (
          <div className="mt-3 divide-y divide-slate-100 rounded-md border border-slate-200">
            {filasVisibles.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between gap-2 px-3 py-2 text-[12.5px]"
              >
                <div className="min-w-0 flex-1">
                  <span className="font-medium text-slate-900">{s.producto}</span>
                  <span className="text-slate-400"> · </span>
                  <span className="text-slate-600">{s.sucursal_id}</span>
                  <span className="text-slate-400"> · </span>
                  <span className="font-mono text-emerald-700">
                    +{formatoNumero(s.unidades)} u
                  </span>
                </div>
                <button
                  onClick={() => onEliminarUna(s.id)}
                  className="rounded p-1 text-slate-300 hover:bg-red-50 hover:text-red-600"
                  aria-label="Eliminar solo esta fila"
                  title="Eliminar solo esta fila"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {ocultas > 0 && (
              <p className="px-3 py-2 text-center text-[11px] text-slate-500">
                Y {formatoNumero(ocultas)} más. Usa “Eliminar las {formatoNumero(filas.length)}”
                para borrarlas todas juntas.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SeccionRecurrentes({
  items,
  onEliminar,
}: {
  items: Recurrente[] | null;
  onEliminar: (id: string) => void;
}) {
  if (items === null) return <p className="text-slate-500">Cargando…</p>;
  if (items.length === 0)
    return (
      <Card>
        <CardContent className="text-[13px] text-slate-500">
          No hay recurrencias activas. Se crean desde el dashboard, marcando “Repetir
          periódicamente” en el modal de sugerencia manual.
        </CardContent>
      </Card>
    );
  return (
    <div className="space-y-2">
      {items.map((r) => (
        <Card key={r.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900">{r.resumen}</span>
                <Badge className="bg-brand-50 text-brand">
                  {r.dias_inventario
                    ? `+${r.dias_inventario} días`
                    : `+${formatoNumero(r.unidades)} u`}
                </Badge>
                <Badge className="bg-slate-100 text-slate-600">
                  cada {r.cada_dias} días
                </Badge>
                <Badge className="bg-slate-100 text-slate-500">
                  {r.modo === "individual" ? "Individual" : "Por grupo"}
                </Badge>
              </div>
              <p className="mt-1 text-[12px] text-slate-500">
                Próxima: <b>{formatoFecha(r.proxima_ejecucion)}</b>
                {r.fecha_fin && <> · termina {formatoFecha(r.fecha_fin)}</>}
                {r.ultima_ejecucion && <> · última {formatoFecha(r.ultima_ejecucion)}</>}
                {r.motivo && <> · {r.motivo}</>}
              </p>
            </div>
            <button
              onClick={() => onEliminar(r.id)}
              className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
              aria-label="Eliminar recurrencia"
            >
              <Trash2 size={16} />
            </button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
