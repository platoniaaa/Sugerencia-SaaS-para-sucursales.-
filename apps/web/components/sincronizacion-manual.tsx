"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoFechaHora } from "@/lib/formato";

function tiempoRelativo(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const segs = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (segs < 60) return "hace segundos";
  const mins = Math.floor(segs / 60);
  if (mins < 60) return `hace ${mins} min`;
  const hs = Math.floor(mins / 60);
  if (hs < 24) return `hace ${hs} h`;
  return `hace ${Math.floor(hs / 24)} d`;
}

export function SincronizacionManual() {
  const [ultimaSync, setUltimaSync] = useState<string | null>(null);
  const [esperando, setEsperando] = useState(false);
  const [exitoReciente, setExitoReciente] = useState(false);
  const refUltima = useRef<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      const r = await api.ultimaSincronizacion();
      setUltimaSync(r.creado_en);
      refUltima.current = r.creado_en;
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Tras click, espera hasta 3 minutos polling cada 4s.
  const onClickSincronizar = () => {
    setEsperando(true);
    setExitoReciente(false);
    const antes = refUltima.current;
    const inicio = Date.now();

    const interval = setInterval(async () => {
      try {
        const r = await api.ultimaSincronizacion();
        if (r.creado_en && r.creado_en !== antes) {
          // Cambio el timestamp -> sincronizo OK
          setUltimaSync(r.creado_en);
          refUltima.current = r.creado_en;
          setEsperando(false);
          setExitoReciente(true);
          clearInterval(interval);
          // Quitar el indicador de exito a los 8 segundos
          setTimeout(() => setExitoReciente(false), 8000);
        }
      } catch {
        /* silent */
      }
      // Timeout 3 minutos
      if (Date.now() - inicio > 180_000) {
        setEsperando(false);
        clearInterval(interval);
      }
    }, 4000);
  };

  return (
    <div className="mt-4 rounded-sm border border-accent-700/20 bg-white p-3">
      <p className="kicker">Sincronización manual</p>
      <p className="mt-1.5 mb-3 text-[12.5px] text-ink-700">
        Forzá una actualización inmediata desde el PC del admin. Power BI Desktop debe
        estar abierto.
      </p>

      <a
        href="sugerido://sync"
        onClick={onClickSincronizar}
        className="inline-flex items-center gap-2 rounded-sm bg-ink-900 px-4 py-2 text-[13px] font-semibold uppercase tracking-wider text-paper transition-colors hover:bg-accent-700"
      >
        {esperando ? (
          <>
            <Loader2 size={14} className="animate-spin" /> Sincronizando…
          </>
        ) : (
          <>
            <RefreshCw size={14} /> Sincronizar ahora
          </>
        )}
      </a>

      {/* Estado actual */}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[12px]">
        <span className="kicker">Última sincronización</span>
        {ultimaSync ? (
          <span className="text-ink-700">
            <b className="font-mono">{formatoFechaHora(ultimaSync)}</b>{" "}
            <span className="text-ink-500">({tiempoRelativo(ultimaSync)})</span>
          </span>
        ) : (
          <span className="text-ink-500">sin registros aún</span>
        )}
      </div>

      {esperando && (
        <p className="mt-2 rounded-sm bg-brand-50 px-3 py-2 text-[12px] text-brand-800">
          Esperando confirmación de la nube… cuando la consola de PowerShell termine en
          tu PC, este mensaje cambia a &ldquo;Listo&rdquo; automáticamente.
        </p>
      )}

      {exitoReciente && (
        <p className="mt-2 inline-flex items-center gap-1.5 rounded-sm bg-emerald-50 px-3 py-2 text-[12.5px] font-medium text-emerald-700">
          <CheckCircle2 size={14} /> Listo — el equipo ya ve los datos actualizados.
        </p>
      )}
    </div>
  );
}
