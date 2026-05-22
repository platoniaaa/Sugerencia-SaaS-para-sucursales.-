import { VistaDetalleProducto } from "@/components/vista-detalle-producto";

export default function ProductoPage({
  params,
  searchParams,
}: {
  params: { producto: string };
  searchParams: { sucursal?: string };
}) {
  const producto = decodeURIComponent(params.producto);
  const sucursal = searchParams.sucursal ?? "";

  if (!sucursal) {
    return (
      <p className="text-slate-500">
        Falta la sucursal. Vuelve al dashboard y haz click en una fila.
      </p>
    );
  }

  return <VistaDetalleProducto producto={producto} sucursalId={sucursal} />;
}
