"use client";

import { useEffect, useRef, useState } from "react";
import { MessageCircle, Send, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { getEsAdmin } from "@/lib/auth";

type Mensaje = { role: "user" | "model"; text: string };

/** Widget flotante de chat con el asistente (Gemini). Solo visible para admin
 * en esta fase 1. Persiste el hilo en memoria mientras la pestania este abierta;
 * no toca localStorage por ahora (privacidad). */
export function ChatBot() {
  const [montado, setMontado] = useState(false);
  const [esAdmin, setEsAdmin] = useState(false);
  const [abierto, setAbierto] = useState(false);
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [borrador, setBorrador] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // SSR-safe: solo leer flags despues del primer render del cliente.
  useEffect(() => {
    setMontado(true);
    setEsAdmin(getEsAdmin());
  }, []);

  // Auto-scroll al final cuando llegan mensajes nuevos.
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [mensajes, enviando]);

  if (!montado || !esAdmin) return null;

  const enviar = async () => {
    const pregunta = borrador.trim();
    if (!pregunta || enviando) return;
    setBorrador("");
    setError(null);
    setMensajes((prev) => [...prev, { role: "user", text: pregunta }]);
    setEnviando(true);
    try {
      const res = await api.chat(pregunta, mensajes);
      setMensajes((prev) => [...prev, { role: "model", text: res.respuesta }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error desconocido");
    } finally {
      setEnviando(false);
    }
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  };

  return (
    <>
      {/* Boton flotante */}
      <button
        onClick={() => setAbierto((v) => !v)}
        className="fixed bottom-5 right-5 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-accent-700 text-white shadow-lg transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-700/40"
        aria-label={abierto ? "Cerrar chat" : "Abrir chat"}
        title="Asistente del sugerido"
      >
        {abierto ? <X size={20} /> : <MessageCircle size={20} />}
      </button>

      {/* Panel */}
      {abierto && (
        <div className="fixed bottom-20 right-5 z-40 flex h-[560px] w-[380px] flex-col rounded-lg border border-ink-200 bg-white shadow-xl">
          <header className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
            <div>
              <p className="text-[13px] font-semibold text-ink-900">Asistente del sugerido</p>
              <p className="text-[11px] text-ink-500">Pregunta sobre productos, ventas o calculos</p>
            </div>
            <button
              onClick={() => setAbierto(false)}
              className="rounded p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
              aria-label="Cerrar"
            >
              <X size={16} />
            </button>
          </header>

          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto px-3 py-3"
          >
            {mensajes.length === 0 && !enviando && (
              <div className="space-y-2 px-2 py-4 text-[12.5px] text-ink-500">
                <p className="font-medium text-ink-700">Ejemplos:</p>
                <ul className="list-inside list-disc space-y-1">
                  <li>&iquest;Por que el sugerido de 20 BXO5W30AA en LINDEROS es tan alto?</li>
                  <li>&iquest;Cuanto vendi de 70 2723982 en los ultimos 12 meses?</li>
                  <li>Buscame productos con &ldquo;filtro aceite&rdquo; en la descripcion.</li>
                  <li>&iquest;Que reemplazo tiene el producto 80 391732?</li>
                </ul>
              </div>
            )}
            {mensajes.map((m, i) => (
              <div
                key={i}
                className={`mb-2 max-w-[85%] rounded-md px-3 py-2 text-[13px] leading-relaxed whitespace-pre-wrap ${
                  m.role === "user"
                    ? "ml-auto bg-accent-50 text-accent-900"
                    : "mr-auto bg-ink-50 text-ink-800"
                }`}
              >
                {m.text}
              </div>
            ))}
            {enviando && (
              <div className="mr-auto mb-2 max-w-[85%] rounded-md bg-ink-50 px-3 py-2 text-[12px] italic text-ink-500">
                Pensando…
              </div>
            )}
            {error && (
              <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
                {error}
              </div>
            )}
          </div>

          <div className="border-t border-ink-100 p-2">
            <div className="flex items-end gap-2">
              <textarea
                value={borrador}
                onChange={(e) => setBorrador(e.target.value)}
                onKeyDown={onKey}
                rows={2}
                placeholder="Escribe tu pregunta y presiona Enter…"
                className="flex-1 resize-none rounded-md border border-ink-200 bg-paper-50 px-3 py-2 text-[13px] text-ink-900 placeholder:text-ink-400 focus-visible:border-accent-700 focus-visible:bg-white focus-visible:outline-none"
                disabled={enviando}
              />
              <button
                onClick={enviar}
                disabled={enviando || !borrador.trim()}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent-700 text-white transition-colors hover:bg-accent-800 disabled:cursor-not-allowed disabled:bg-ink-300"
                aria-label="Enviar"
              >
                <Send size={15} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
