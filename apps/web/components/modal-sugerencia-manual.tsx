"use client";

import { useEffect, useMemo, useState } from "react";
import { Boxes, Layers, Package, TriangleAlert } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { MultiSelect } from "@/components/ui/multiselect";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api-client";
import { formatoNumero } from "@/lib/formato";
import type { Producto, Sucursal, SugeridoFiltros } from "@/lib/types";

type Modo = "individual" | "grupo" | "todos";

interface Props {
  open: boolean;
  onClose: () => void;
  onGuardado: () => void;
  sucursales: Sucursal[];
  marcas?: string[];
  productoInicial?: string;
  sucursalInicial?: string;
  /** Si es true, solo permite el modo individual (ej. desde la vista detalle). */
  soloIndividual?: boolean;
}

const ABC = [
  { value: "A", label: "A" },
  { value: "B", label: "B" },
  { value: "C", label: "C" },
];

export function ModalSugerenciaManual({
  open,
  onClose,
  onGuardado,
  sucursales,
  marcas = [],
  productoInicial,
  sucursalInicial,
  soloIndividual = false,
}: Props) {
  const [modo, setModo] = useState<Modo>("individual");

  // Comunes
  const [unidades, setUnidades] = useState("");
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Individual
  const [producto, setProducto] = useState("");
  const [sucursal, setSucursal] = useState("");
  const [sugerencias, setSugerencias] = useState<Producto[]>([]);

  // Grupo
  const [gSucursales, setGSucursales] = useState<string[]>([]);
  const [gMarcas, setGMarcas] = useState<string[]>([]);
  const [gAbc, setGAbc] = useState<string[]>([]);

  // Grupo/Todos
  const [soloPedir, setSoloPedir] = useState(true);
  const [conteo, setConteo] = useState<number | null>(null);
  const [contando, setContando] = useState(false);

  const nombresSucursales = useMemo(
    () => sucursales.map((s) => s.nombre ?? s.sucursal_id),
    [sucursales]
  );

  useEffect(() => {
    if (open) {
      setModo("individual");
      setUnidades("");
      setMotivo("");
      setError(null);
      setProducto(productoInicial ?? "");
      setSucursal(sucursalInicial ?? "");
      setGSucursales([]);
      setGMarcas([]);
      setGAbc([]);
      setSoloPedir(true);
      setConteo(null);
    }
  }, [open, productoInicial, sucursalInicial]);

  // Autocomplete producto (modo individual)
  useEffect(() => {
    if (modo !== "individual" || !producto || producto === productoInicial) {
      setSugerencias([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const r = await api.productos(producto);
        setSugerencias(r.items.slice(0, 6));
      } catch {
        setSugerencias([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [producto, productoInicial, modo]);

  // Filtros equivalentes al modo grupo/todos.
  const filtrosModo: SugeridoFiltros = useMemo(() => {
    if (modo === "todos") return { solo_pedir: soloPedir };
    if (modo === "grupo")
      return {
        sucursales: gSucursales,
        filtro1: gMarcas,
        abc: gAbc,
        solo_pedir: soloPedir,
      };
    return {};
  }, [modo, soloPedir, gSucursales, gMarcas, gAbc]);

  // Conteo en vivo de productos afectados.
  useEffect(() => {
    if (!open || modo === "individual") return;
    setContando(true);
    const t = setTimeout(async () => {
      try {
        setConteo(await api.contar(filtrosModo));
      } catch {
        setConteo(null);
      } finally {
        setContando(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [open, modo, filtrosModo]);

  const guardar = async () => {
    setError(null);
    const u = parseInt(unidades, 10);
    if (!u || u <= 0) {
      setError("Ingresa una cantidad de unidades (entero positivo).");
      return;
    }
    setGuardando(true);
    try {
      if (modo === "individual") {
        if (!producto || !sucursal) {
          setError("Completa producto y sucursal.");
          setGuardando(false);
          return;
        }
        await api.crearSugerenciaManual({
          producto,
          sucursal_id: sucursal,
          unidades: u,
          motivo: motivo || undefined,
        });
      } else {
        if (!conteo || conteo === 0) {
          setError("Ningun producto cumple ese criterio. Ajusta el grupo.");
          setGuardando(false);
          return;
        }
        await api.crearSugerenciaMasiva(filtrosModo, u, motivo || undefined);
      }
      onGuardado();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setGuardando(false);
    }
  };

  const tabs: { id: Modo; icon: React.ReactNode; label: string; sub: string }[] = [
    { id: "individual", icon: <Package size={16} />, label: "Individual", sub: "Un producto" },
    { id: "grupo", icon: <Layers size={16} />, label: "Por grupo", sub: "Por sucursal / marca / ABC" },
    { id: "todos", icon: <Boxes size={16} />, label: "Todos", sub: "Todos los productos" },
  ];

  const etiquetaBoton =
    modo === "individual"
      ? guardando
        ? "Guardando…"
        : "Guardar"
      : guardando
        ? "Aplicando…"
        : conteo
          ? `Aplicar a ${formatoNumero(conteo)} producto${conteo === 1 ? "" : "s"}`
          : "Aplicar";

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Agregar sugerencia manual"
      description="Suma unidades por sobre lo que sugiere el sistema."
    >
      <div className="space-y-4">
        {/* Selector de modo */}
        {!soloIndividual && (
          <div className="grid grid-cols-3 gap-2">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setModo(t.id)}
                className={cn(
                  "flex flex-col items-start gap-0.5 rounded-lg border p-2.5 text-left transition-colors",
                  modo === t.id
                    ? "border-brand bg-brand-50 text-brand"
                    : "border-slate-200 text-slate-600 hover:bg-slate-50"
                )}
              >
                <span className="flex items-center gap-1.5 text-[13px] font-medium">
                  {t.icon}
                  {t.label}
                </span>
                <span className="text-[11px] text-slate-400">{t.sub}</span>
              </button>
            ))}
          </div>
        )}

        {/* --- Modo individual --- */}
        {modo === "individual" && (
          <>
            <div className="relative">
              <Label htmlFor="prod">Producto</Label>
              <Input
                id="prod"
                value={producto}
                onChange={(e) => setProducto(e.target.value)}
                placeholder="Codigo del producto"
                autoComplete="off"
              />
              {sugerencias.length > 0 && (
                <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg">
                  {sugerencias.map((p) => (
                    <button
                      key={p.producto}
                      type="button"
                      onClick={() => {
                        setProducto(p.producto);
                        setSugerencias([]);
                      }}
                      className="block w-full px-3 py-1.5 text-left text-[13px] hover:bg-slate-50"
                    >
                      <span className="font-medium">{p.producto}</span>{" "}
                      <span className="text-slate-500">{p.descripcion}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div>
              <Label htmlFor="suc">Sucursal</Label>
              <select
                id="suc"
                value={sucursal}
                onChange={(e) => setSucursal(e.target.value)}
                className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <option value="">Selecciona…</option>
                {sucursales.map((s) => (
                  <option key={s.sucursal_id} value={s.sucursal_id}>
                    {s.nombre ?? s.sucursal_id}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        {/* --- Modo grupo --- */}
        {modo === "grupo" && (
          <div className="space-y-3 rounded-lg border border-slate-100 bg-slate-50/60 p-3">
            <p className="text-[12px] text-slate-500">
              Elige uno o varios criterios. Se aplicara a los productos que cumplan
              <b> todos</b> los criterios seleccionados.
            </p>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <Label>Sucursal</Label>
                <MultiSelect
                  label="Todas"
                  opciones={nombresSucursales.map((s) => ({ value: s, label: s }))}
                  seleccionados={gSucursales}
                  onChange={setGSucursales}
                />
              </div>
              <div>
                <Label>Marca</Label>
                <MultiSelect
                  label="Todas"
                  opciones={marcas.map((m) => ({ value: m, label: m }))}
                  seleccionados={gMarcas}
                  onChange={setGMarcas}
                />
              </div>
              <div>
                <Label>ABC</Label>
                <MultiSelect
                  label="Todas"
                  opciones={ABC}
                  seleccionados={gAbc}
                  onChange={setGAbc}
                />
              </div>
            </div>
          </div>
        )}

        {/* Toggle solo pedir (grupo y todos) */}
        {modo !== "individual" && (
          <label className="flex cursor-pointer select-none items-center gap-2 text-[13px] text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 accent-brand"
              checked={soloPedir}
              onChange={(e) => setSoloPedir(e.target.checked)}
            />
            Solo productos con pedir = Si (recomendado)
          </label>
        )}

        {/* Conteo en vivo */}
        {modo !== "individual" && (
          <div
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-[13px]",
              conteo && conteo > 1000
                ? "bg-amber-50 text-amber-800"
                : "bg-brand-50 text-brand"
            )}
          >
            {conteo && conteo > 1000 && <TriangleAlert size={15} />}
            {contando ? (
              "Calculando productos afectados…"
            ) : conteo === null ? (
              "—"
            ) : (
              <span>
                Se aplicara a <b>{formatoNumero(conteo)}</b> producto
                {conteo === 1 ? "" : "s"} (producto × sucursal).
                {conteo > 1000 && " Es una carga grande, revisa antes de aplicar."}
              </span>
            )}
          </div>
        )}

        {/* Unidades + motivo (comunes) */}
        <div>
          <Label htmlFor="uni">
            {modo === "individual" ? "Unidades adicionales" : "Unidades para cada producto"}
          </Label>
          <Input
            id="uni"
            type="number"
            min={1}
            value={unidades}
            onChange={(e) => setUnidades(e.target.value)}
            placeholder="0"
          />
        </div>
        <div>
          <Label htmlFor="mot">Motivo (opcional)</Label>
          <Textarea
            id="mot"
            rows={2}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ej: promo, quiebre puntual, pedido especial de la jefa…"
          />
        </div>

        {error && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
        )}

        <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={guardar} disabled={guardando}>
            {etiquetaBoton}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
