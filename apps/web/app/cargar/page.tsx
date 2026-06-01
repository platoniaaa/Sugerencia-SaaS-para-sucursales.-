"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, Cloud, FileSpreadsheet, RefreshCw, Upload } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { getEsAdmin } from "@/lib/auth";
import { formatoNumero } from "@/lib/formato";
import type { CargaResultado } from "@/lib/types";

export default function CargarPage() {
  const router = useRouter();
  // Si alguien sin permisos cae aca por URL, lo mandamos al dashboard.
  useEffect(() => {
    if (!getEsAdmin()) router.replace("/");
  }, [router]);
  const [file, setFile] = useState<File | null>(null);
  const [cargando, setCargando] = useState(false);
  const [resultado, setResultado] = useState<CargaResultado | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [powerbiOk, setPowerbiOk] = useState(false);
  const [sincronizando, setSincronizando] = useState(false);
  const [sincDesktop, setSincDesktop] = useState(false);

  // El boton "Actualizar desde Power BI" (Desktop) solo sirve cuando la app corre en
  // el MISMO PC que Power BI (modo local). En la nube no aplica, asi que se oculta.
  const apiEsLocal = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").includes(
    "localhost"
  );

  useEffect(() => {
    api
      .powerbiEstado()
      .then((e) => setPowerbiOk(e.configurado))
      .catch(() => setPowerbiOk(false));
  }, []);

  const sincronizar = async () => {
    setSincronizando(true);
    setError(null);
    setResultado(null);
    try {
      setResultado(await api.sincronizarPowerBI());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al sincronizar");
    } finally {
      setSincronizando(false);
    }
  };

  const sincronizarDesktop = async () => {
    setSincDesktop(true);
    setError(null);
    setResultado(null);
    try {
      setResultado(await api.sincronizarPowerBIDesktop());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al leer Power BI Desktop");
    } finally {
      setSincDesktop(false);
    }
  };

  const subir = async () => {
    if (!file) return;
    setCargando(true);
    setError(null);
    setResultado(null);
    try {
      setResultado(await api.cargarSugerido(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">Cargar datos</h1>
        <p className="text-[13px] text-slate-500">
          Sube el Excel o CSV que exportas del Power BI (tabla &ldquo;Sugerido por
          Sucursal&rdquo;). Reemplaza por completo los datos actuales.
        </p>
      </div>

      {/* Power BI Desktop abierto (solo modo LOCAL; en la nube se oculta) */}
      {apiEsLocal && (
        <Card className="border-brand/30 bg-gradient-to-br from-brand-50 to-white">
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand text-white">
                <RefreshCw size={20} />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-900">Actualizar desde Power BI</p>
                <p className="text-[13px] text-slate-500">
                  Ten Power BI Desktop <b>abierto</b> con el modelo y haz clic. Lee los datos
                  directo, sin exportar archivos.
                </p>
              </div>
            </div>
            <Button onClick={sincronizarDesktop} disabled={sincDesktop}>
              <RefreshCw size={15} className={sincDesktop ? "animate-spin" : ""} />
              {sincDesktop ? "Leyendo…" : "Actualizar ahora"}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Nota para la version en la nube: como actualizar los datos */}
      {!apiEsLocal && (
        <Card className="border-brand/30 bg-brand-50">
          <CardContent className="text-[13px] text-slate-700">
            <p className="font-semibold text-slate-900">¿Cómo se actualizan los datos?</p>
            <p className="mt-1">
              Esta es la versión en la nube. Los datos los actualiza el administrador desde su
              PC: abre Power BI Desktop y ejecuta el script <b>push_to_cloud.ps1</b>. Eso trae el
              sugerido con todas sus medidas y lo publica para todo el equipo.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Sincronizacion automatica via API (solo si hay service principal configurado) */}
      {powerbiOk && (
        <Card className="border-emerald-200 bg-gradient-to-br from-emerald-50 to-white">
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-600 text-white">
                <Cloud size={20} />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  Sincronizar con Power BI (automatico)
                </p>
                <p className="text-[13px] text-slate-500">
                  Trae los datos del Power BI Service. No requiere tener Power BI abierto.
                </p>
              </div>
            </div>
            <Button onClick={sincronizar} disabled={sincronizando}>
              <RefreshCw size={15} className={sincronizando ? "animate-spin" : ""} />
              {sincronizando ? "Sincronizando…" : "Sincronizar ahora"}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Subida manual: SOLO en modo local. En la nube se oculta para evitar que un
          Excel de la tabla base (sin medidas) pise los datos buenos por accidente. */}
      {apiEsLocal && (
      <div className="flex items-center gap-3 text-[12px] text-slate-400">
        <span className="h-px flex-1 bg-slate-200" />o sube un archivo manualmente
        <span className="h-px flex-1 bg-slate-200" />
      </div>
      )}

      {apiEsLocal && (
      <Card>
        <CardContent className="space-y-4">
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              const f = e.dataTransfer.files?.[0];
              if (f) setFile(f);
            }}
            className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
              drag ? "border-brand bg-brand-50" : "border-slate-300 bg-slate-50 hover:bg-slate-100"
            }`}
          >
            <input
              type="file"
              accept=".xlsx,.xlsm,.csv"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file ? (
              <>
                <FileSpreadsheet size={32} className="text-brand" />
                <span className="text-sm font-medium text-slate-900">{file.name}</span>
                <span className="text-[12px] text-slate-500">
                  {(file.size / 1024).toFixed(0)} KB · click para cambiar
                </span>
              </>
            ) : (
              <>
                <Upload size={32} className="text-slate-400" />
                <span className="text-sm font-medium text-slate-700">
                  Arrastra el archivo aqui o haz click
                </span>
                <span className="text-[12px] text-slate-500">.xlsx, .xlsm o .csv</span>
              </>
            )}
          </label>

          <Button onClick={subir} disabled={!file || cargando} className="w-full">
            {cargando ? "Cargando…" : "Cargar a la plataforma"}
          </Button>

          {error && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
          )}
        </CardContent>
      </Card>
      )}

      {resultado && (
        <Card className="border-emerald-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-emerald-700">
              <CheckCircle2 size={18} /> Carga exitosa
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-[13px] text-slate-700">
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-slate-50 p-3 text-center">
                <p className="tabular text-lg font-semibold text-slate-900">
                  {formatoNumero(resultado.filas_cargadas)}
                </p>
                <p className="text-[12px] text-slate-500">filas</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3 text-center">
                <p className="tabular text-lg font-semibold text-slate-900">
                  {formatoNumero(resultado.productos)}
                </p>
                <p className="text-[12px] text-slate-500">productos</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3 text-center">
                <p className="tabular text-lg font-semibold text-slate-900">
                  {formatoNumero(resultado.sucursales)}
                </p>
                <p className="text-[12px] text-slate-500">sucursales</p>
              </div>
            </div>

            {resultado.advertencias.length > 0 && (
              <div className="rounded-md bg-amber-50 px-3 py-2 text-amber-800">
                {resultado.advertencias.map((a, i) => (
                  <p key={i}>⚠ {a}</p>
                ))}
              </div>
            )}

            <details className="text-[12px] text-slate-500">
              <summary className="cursor-pointer">
                Ver columnas detectadas ({resultado.columnas_detectadas.length})
              </summary>
              <ul className="mt-1 space-y-0.5">
                {resultado.columnas_detectadas.map((c) => (
                  <li key={c} className="tabular">{c}</li>
                ))}
              </ul>
            </details>

            <Link href="/">
              <Button className="w-full">Ir al dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
