"use client";

import type { ReactNode } from "react";
import { AlertTriangle, Sigma } from "lucide-react";

/* Documentación del modelo de cálculo del sugerido (Power BI de Curifor).
   Contenido estático: refleja las reglas y fórmulas vigentes del modelo.
   Fuente de verdad: "CLAUDE contexto modelo.md" en la raíz del repo. Si el
   modelo cambia, actualizar también acá. */

type Seccion = { id: string; titulo: string };

const SECCIONES: Seccion[] = [
  { id: "resumen", titulo: "Qué hace el modelo" },
  { id: "vistas", titulo: "Las 3 vistas del sugerido" },
  { id: "abastece-cd", titulo: 'Lógica "Abastece CD"' },
  { id: "formulas", titulo: "Fórmulas y medidas" },
  { id: "parametros", titulo: "Parámetros" },
  { id: "reglas", titulo: "Reglas de negocio" },
  { id: "ventas", titulo: "Datos de venta (VentasLimpias)" },
  { id: "sucursales", titulo: "Lógica de sucursales" },
  { id: "motivo", titulo: "Filtro de motivo (reposición)" },
  { id: "reemplazos", titulo: "Agrupaciones de reemplazo" },
  { id: "columnas", titulo: "Columnas clave" },
];

export default function ModeloPage() {
  return (
    <div className="space-y-8">
      {/* Encabezado */}
      <header className="border-b border-ink-200 pb-5">
        <p className="kicker mb-2 flex items-center gap-1.5">
          <Sigma size={13} className="text-accent-500" /> Documentación
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight text-ink-900">
          Modelo de cálculo del sugerido
        </h1>
        <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-ink-600">
          Cómo el modelo de Power BI calcula el sugerido de reposición: las reglas
          de negocio aplicadas, las fórmulas de cada medida y la lógica de las
          vistas. Esta es la fuente de referencia para entender de dónde sale cada
          número que ves en la plataforma.
        </p>
      </header>

      <div className="lg:grid lg:grid-cols-[220px_1fr] lg:gap-10">
        {/* Tabla de contenidos */}
        <nav className="mb-8 lg:mb-0">
          <div className="lg:sticky lg:top-24">
            <p className="kicker mb-3">En esta página</p>
            <ul className="space-y-1.5 border-l border-ink-200">
              {SECCIONES.map((s) => (
                <li key={s.id}>
                  <a
                    href={`#${s.id}`}
                    className="-ml-px block border-l-2 border-transparent py-0.5 pl-3 text-[13px] text-ink-600 transition-colors hover:border-accent-500 hover:text-ink-900"
                  >
                    {s.titulo}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </nav>

        {/* Contenido */}
        <div className="min-w-0 space-y-12">
          <Section id="resumen" titulo="Qué hace el modelo">
            <P>
              Es una herramienta de sugerido de reposición de compras. Calcula{" "}
              <strong>cuánto pedir por cada producto y sucursal</strong> para
              mantener el inventario en el nivel objetivo, considerando demanda,
              tiempos de entrega del proveedor, stock disponible y stock en
              tránsito.
            </P>
            <P>
              La tabla núcleo del modelo es{" "}
              <Code>Sugerido por Sucursal</Code>: una fila por producto × sucursal
              con todas las medidas precalculadas. La plataforma consume esos
              resultados; no recalcula nada por su cuenta (Fase 0).
            </P>
          </Section>

          <Section id="vistas" titulo="Las 3 vistas del sugerido">
            <P>
              El sugerido se divide en <strong>tres vistas disjuntas</strong> (sin
              toggle). Las tres suman exactamente al total:
            </P>
            <div className="space-y-3">
              <VistaCard
                n="1"
                titulo="Compra directa de sucursal"
                cond={
                  <>
                    <Code>Abastece CD = "No"</Code>,{" "}
                    <Code>SucursalID ≠ "CD REPUESTOS"</Code>,{" "}
                    <Code>Sugerido Suc &gt; 0</Code>
                  </>
                }
                desc="La sucursal compra directo al proveedor (nacional clase A/B en sucursales normales)."
              />
              <VistaCard
                n="2"
                titulo="Compra centralizada en CD"
                cond={
                  <>
                    <Code>SucursalID = "CD REPUESTOS"</Code>,{" "}
                    <Code>Sugerido Suc &gt; 0</Code>
                  </>
                }
                desc="La compra real del CD. Es la fila marcada como CD REPUESTOS."
              />
              <VistaCard
                n="3"
                titulo="Distribución / traslado"
                cond={
                  <>
                    <Code>Abastece CD = "Sí"</Code>,{" "}
                    <Code>Sugerido Traslado &gt; 0</Code>
                  </>
                }
                desc="Traslado desde el CD a la sucursal. Muestra Sugerido Traslado + Stock en CD + Necesidad Bruta Suc."
              />
            </div>
            <Callout>
              El antiguo toggle “Abastece CD” se eliminó por engañoso: las
              sucursales con <Code>"Sí"</Code> muestran sugerido cero, mientras la
              compra real del CD vive en la fila <Code>CD REPUESTOS</Code> marcada{" "}
              <Code>"No"</Code>.
            </Callout>
          </Section>

          <Section id="abastece-cd" titulo='Lógica "Abastece CD"'>
            <P>
              Define si un producto en una sucursal se abastece a través del Centro
              de Distribución o se compra directo:
            </P>
            <ul className="space-y-2 text-[14px] text-ink-700">
              <li className="flex gap-2">
                <Badge tono="si">Sí</Badge>
                <span>
                  cuando es <strong>Importado</strong>, <strong>Nacional clase C</strong>,
                  o la sucursal es{" "}
                  <Code>OFICINAS CENTRALES</Code>, <Code>CANAL DIGITAL</Code> o{" "}
                  <Code>LINDEROS VTA MOVIL</Code>.
                </span>
              </li>
              <li className="flex gap-2">
                <Badge tono="no">No</Badge>
                <span>
                  cuando es <strong>Nacional clase A/B</strong> en sucursales
                  normales (compran directo al proveedor).
                </span>
              </li>
            </ul>
          </Section>

          <Section id="formulas" titulo="Fórmulas y medidas">
            <P>Fórmula central del sugerido por sucursal:</P>
            <Formula
              titulo="Sugerido Suc"
              expr="DD × (CO + LT) + SS − SA − ST"
              donde={[
                ["DD", "Demanda diaria del producto en la sucursal"],
                ["CO", "Ciclo de orden (días hábiles entre pedidos)"],
                ["LT", "Lead Time efectivo (ver LT Efectivo abajo)"],
                ["SS", "Safety stock (stock de seguridad)"],
                ["SA", "Stock activo en la sucursal"],
                ["ST", "Stock en tránsito (OCs pendientes)"],
              ]}
            />
            <Formula
              titulo="LT Efectivo"
              expr={`IF( Abastece CD = "Sí", LT CD Sucursal, Lead Time Dias )`}
              nota="El SS y el Sugerido Suc usan LT Efectivo. Para productos que pasan por el CD, el tiempo CD→sucursal es constante (RM = 1d, resto = 2d); en compra directa se usa el Lead Time real del proveedor."
            />
            <P>Otras medidas del sistema (no se duplican; ya existen en el modelo):</P>
            <ul className="grid gap-2 sm:grid-cols-2">
              {[
                ["Stock Activo Suc", "Stock disponible en la sucursal"],
                ["Stock en Transito Suc", "OCs pendientes de recepción"],
                ["Stock en CD", "Stock disponible en el Centro de Distribución"],
                ["Sugerido Traslado", "Unidades a trasladar desde el CD"],
                ["Sugerido Compra Neto", "Compra neta tras descontar traslados"],
                ["Total Sugerido Suc", "Total sugerido de la sucursal"],
                ["Pedir?", "Marca Sí/No según si hay sugerido > 0"],
              ].map(([m, d]) => (
                <li
                  key={m}
                  className="rounded-sm border border-ink-200 bg-white px-3 py-2"
                >
                  <code className="text-[12.5px] font-semibold text-brand">{m}</code>
                  <p className="mt-0.5 text-[12.5px] text-ink-600">{d}</p>
                </li>
              ))}
            </ul>
          </Section>

          <Section id="parametros" titulo="Parámetros">
            <ul className="space-y-2">
              <ParamItem nombre="_CicloOrdenDias" valor="5">
                Días hábiles entre pedidos (= 1 semana).
              </ParamItem>
              <ParamItem nombre="_DiasHabilesMes" valor="22">
                Días hábiles por mes, para convertir demanda mensual a diaria.
              </ParamItem>
              <ParamItem nombre="_NivelServicioZ" valor="Z">
                Factor Z del nivel de servicio objetivo, usado en el safety stock.
              </ParamItem>
            </ul>
          </Section>

          <Section id="reglas" titulo="Reglas de negocio">
            <P className="text-ink-500 !mt-0 text-[12.5px]">
              Definidas por Abastecimiento (Mary Ramos), mayo 2026.
            </P>
            <ul className="space-y-3 text-[14px] text-ink-700">
              <Regla t="Proveedor">
                SIEMPRE el proveedor real. Nunca usar “CD REPUESTOS” como nombre de
                proveedor.
              </Regla>
              <Regla t="Lead Time">
                SIEMPRE el LT real del proveedor, nunca 1d. El tiempo CD→sucursal es
                constante (columna <Code>LT CD a Sucursal Dias</Code>): RM = 1d,
                resto = 2d.
              </Regla>
              <Regla t="Clases ABC">
                Las clases A, B y C calculan sugerido. La clase C usa una ventana de
                6 meses con la misma fórmula de safety stock.
              </Regla>
              <Regla t="NoRepresentados">
                Excluidos, EXCEPTO cuando son Importado + Stock CD.
              </Regla>
              <Regla t="Sucursales excluidas">
                9 sucursales se excluyen vía <Code>VentasLimpias</Code>: La Florida,
                Lira, Lo Blanco, 3 Mall Plaza, Ovalle 3, Gran Avenida y Coquimbo.
              </Regla>
            </ul>
          </Section>

          <Section id="ventas" titulo="Datos de venta (VentasLimpias)">
            <P>
              La demanda se calcula desde <Code>VentasLimpias</Code>, que limpia y
              consolida el histórico de ventas:
            </P>
            <ul className="list-disc space-y-1.5 pl-5 text-[14px] text-ink-700">
              <li>
                Excluye notas de crédito (<Code>EsNotaCredito = FALSE</Code>) y 6
                conceptos no comprables (taller, insumos pesados, incentivos, etc.).
              </li>
              <li>
                Usa <Code>CantidadAjustada</Code> en todo: resta NC y suma valores
                absolutos de otros tipos de documento (incl. cargo interno y
                garantías), alineado con Abastecimiento.
              </li>
              <li>
                Solo considera <strong>meses cerrados</strong> (fecha &lt; primer día
                del mes actual).
              </li>
              <li>
                Anti-duplicación entre el acumulado histórico, el SQL del mes reciente
                y la frontera.
              </li>
            </ul>
          </Section>

          <Section id="sucursales" titulo="Lógica de sucursales">
            <P>
              <Code>SUCURSAL_FINAL</Code> solo redirige{" "}
              <Code>LINDEROS + VTA MOVIL → "LINDEROS VTA MOVIL"</Code> (sucursal
              virtual). Todas las demás mantienen su sucursal original.
            </P>
            <P>
              OFICINAS CENTRALES, CANAL DIGITAL, LINDEROS y CD REPUESTOS son
              sucursales completas, con su propia demanda, safety stock y sugerido.
            </P>
            <Callout tono="info">
              En los visuales se usa la columna <Code>Nombre Sucursal</Code> (resuelta
              por <Code>LOOKUPVALUE</Code>), no <Code>Dim Sucursal[Nombre]</Code> que
              dejaba blancos por mismatch. Es cosmética: los cálculos siguen usando{" "}
              <Code>SucursalID</Code>.
            </Callout>
          </Section>

          <Section id="motivo" titulo="Filtro de motivo (reposición)">
            <P>Filtro base aplicado en TODO el modelo:</P>
            <Formula expr={`Origen <> "Curifor Nacional" OR Motivo = "reposicion"`} />
            <Callout tono="warn">
              El filtro de motivo va SIEMPRE en minúscula:{" "}
              <Code>"reposicion"</Code>. En mayúscula (<Code>"REPOSICION"</Code>) es un
              patrón de bug que devuelve cero resultados en silencio.
            </Callout>
            <P className="text-[13px] text-ink-600">
              Tratamiento de outliers en lead time: P90 por proveedor (excluye OCs por
              sobre el P90 del proveedor y promedia el resto), sin requisito de muestra
              mínima.
            </P>
          </Section>

          <Section id="reemplazos" titulo="Agrupaciones de reemplazo">
            <P>
              El modelo agrupa productos que se reemplazan entre sí (planilla “mix
              andres”): 64 grupos jerárquicos. Cada grupo tiene un{" "}
              <strong>producto master</strong> (el de más ventas), mapeado en{" "}
              <Code>Mapeo Producto Master</Code>.
            </P>
            <P>
              El sugerido se calcula por <strong>master × sucursal</strong>, y el
              stock (activo, en CD y en tránsito) suma a través de todo el grupo de
              reemplazo, para no pedir de más cuando un código sustituye a otro.
            </P>
          </Section>

          <Section id="columnas" titulo="Columnas clave">
            <Formula
              titulo="Pedir"
              expr={`VAR sug = CALCULATE([Sugerido Suc])\nRETURN IF( sug > 0, "Sí", "No" )`}
              nota="Columna física (necesaria para el slicer). Usa context transition para invocar la medida, así siempre coincide con Pedir? y los KPIs."
            />
            <Formula
              titulo="Prioridad CD"
              expr={`SWITCH( SucursalID, ... )`}
              nota="Orden de prioridad para repartir el stock del CD: 1 = Diez de Julio (2), 2 = Brasil 18, 3 = Linderos, 4 = Placilla, 5 = Rancagua… hasta 11 = Chillán Viejo. Sucursales especiales = 99."
            />
            <Formula
              titulo='Comprar en el CD = "Sí"'
              expr="Σ Sugerido(sucursales con prioridad ≤ propia) > Stock en CD"
              nota="El CD compra para una sucursal cuando la demanda acumulada de las sucursales con prioridad igual o mayor supera el stock disponible en el CD."
            />
          </Section>
        </div>
      </div>
    </div>
  );
}

/* ---------- Componentes de presentación ---------- */

function Section({
  id,
  titulo,
  children,
}: {
  id: string;
  titulo: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <h2 className="font-display text-xl font-medium tracking-tight text-ink-900 editorial-rule">
        {titulo}
      </h2>
      {children}
    </section>
  );
}

function P({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p className={`max-w-3xl text-[14px] leading-relaxed text-ink-700 ${className}`}>
      {children}
    </p>
  );
}

function Code({ children }: { children: ReactNode }) {
  return (
    <code className="rounded-sm bg-ink-100 px-1.5 py-0.5 font-mono text-[12.5px] text-ink-800">
      {children}
    </code>
  );
}

function Formula({
  titulo,
  expr,
  donde,
  nota,
}: {
  titulo?: string;
  expr: string;
  donde?: [string, string][];
  nota?: string;
}) {
  return (
    <div className="max-w-3xl overflow-hidden rounded-sm border border-ink-200 bg-white">
      {titulo && (
        <div className="border-b border-ink-200 bg-ink-50 px-4 py-2">
          <code className="text-[13px] font-semibold text-brand">{titulo}</code>
        </div>
      )}
      <pre className="overflow-x-auto px-4 py-3 font-mono text-[13px] leading-relaxed text-ink-900">
        {expr}
      </pre>
      {donde && (
        <dl className="border-t border-ink-100 px-4 py-3 text-[12.5px]">
          <dt className="kicker mb-2">Donde</dt>
          <div className="space-y-1">
            {donde.map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <code className="w-8 shrink-0 font-mono font-semibold text-accent-600">
                  {k}
                </code>
                <span className="text-ink-600">{v}</span>
              </div>
            ))}
          </div>
        </dl>
      )}
      {nota && (
        <p className="border-t border-ink-100 px-4 py-2.5 text-[12.5px] leading-relaxed text-ink-600">
          {nota}
        </p>
      )}
    </div>
  );
}

function Callout({
  children,
  tono = "warn",
}: {
  children: ReactNode;
  tono?: "warn" | "info";
}) {
  const estilos =
    tono === "warn"
      ? "border-accent-100 bg-accent-50/60 text-ink-700"
      : "border-brand-200 bg-brand-50/60 text-ink-700";
  const colorIcono = tono === "warn" ? "text-accent-600" : "text-brand";
  return (
    <div
      className={`flex max-w-3xl gap-2.5 rounded-sm border px-4 py-3 text-[13px] leading-relaxed ${estilos}`}
    >
      <AlertTriangle size={16} className={`mt-0.5 shrink-0 ${colorIcono}`} />
      <div>{children}</div>
    </div>
  );
}

function VistaCard({
  n,
  titulo,
  cond,
  desc,
}: {
  n: string;
  titulo: string;
  cond: ReactNode;
  desc: string;
}) {
  return (
    <div className="flex gap-3 rounded-sm border border-ink-200 bg-white p-4">
      <span className="figure shrink-0 text-2xl text-accent-500">{`0${n}.`}</span>
      <div className="min-w-0">
        <p className="text-[14px] font-semibold text-ink-900">{titulo}</p>
        <p className="mt-1 text-[13px] leading-relaxed text-ink-600">{cond}</p>
        <p className="mt-1.5 text-[12.5px] text-ink-500">{desc}</p>
      </div>
    </div>
  );
}

function Badge({
  children,
  tono,
}: {
  children: ReactNode;
  tono: "si" | "no";
}) {
  const cls =
    tono === "si"
      ? "bg-emerald-50 text-emerald-700"
      : "bg-slate-100 text-slate-600";
  return (
    <span
      className={`mt-0.5 inline-flex h-5 shrink-0 items-center rounded-sm px-1.5 text-[11px] font-semibold ${cls}`}
    >
      {children}
    </span>
  );
}

function ParamItem({
  nombre,
  valor,
  children,
}: {
  nombre: string;
  valor: string;
  children: ReactNode;
}) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-sm border border-ink-200 bg-white px-3 py-2">
      <code className="font-mono text-[13px] font-semibold text-brand">{nombre}</code>
      <code className="font-mono text-[13px] text-accent-600">= {valor}</code>
      <span className="text-[13px] text-ink-600">{children}</span>
    </li>
  );
}

function Regla({ t, children }: { t: string; children: ReactNode }) {
  return (
    <li className="border-l-2 border-ink-200 pl-3">
      <span className="font-semibold text-ink-900">{t}:</span>{" "}
      <span className="text-ink-700">{children}</span>
    </li>
  );
}
