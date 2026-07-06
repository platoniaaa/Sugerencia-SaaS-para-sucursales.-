"""Agente comprador (Nivel 1): arma carros de compra agrupando el sugerido por proveedor.

La cantidad a pedir a cada proveedor es la "compra neta" (lo que no se cubre con traslado
desde el CD): coalesce(sugerido_compra_neto, total_sugerido_suc). Se suma por producto a
traves de las sucursales -> una linea por producto por proveedor.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ProductoCatalogo, Sugerido, SugerenciaManual
from ..schemas import CarroProveedor, CarrosResponse, LineaCarro, SugeridoFiltros
from .sugerido_service import _apply_filters, _no_vencida


def _manuales_vigentes_subq():
    """Suma de unidades manuales vigentes (no archivadas) por producto x sucursal."""
    return (
        select(
            SugerenciaManual.producto.label("producto"),
            SugerenciaManual.sucursal_id.label("sucursal_id"),
            func.sum(SugerenciaManual.unidades).label("manual"),
        )
        .where(SugerenciaManual.archivada.is_(False), _no_vencida())
        .group_by(SugerenciaManual.producto, SugerenciaManual.sucursal_id)
        .subquery()
    )


def carros_por_proveedor(db: Session, f: SugeridoFiltros) -> CarrosResponse:
    man = _manuales_vigentes_subq()
    # Cantidad a comprar = compra neta del sistema + ajuste manual vigente del usuario.
    cant = func.coalesce(Sugerido.sugerido_compra_neto, Sugerido.total_sugerido_suc, 0) + func.coalesce(
        man.c.manual, 0
    )
    stmt = (
        _apply_filters(
            select(
                Sugerido.proveedor.label("proveedor"),
                Sugerido.producto.label("producto"),
                func.max(Sugerido.descripcion).label("descripcion"),
                func.max(Sugerido.clasificacion_abc).label("abc"),
                func.max(Sugerido.costo_unitario).label("costo"),
                func.sum(cant).label("cantidad"),
            ),
            f,
        )
        .join(
            man,
            (man.c.producto == Sugerido.producto) & (man.c.sucursal_id == Sugerido.sucursal_id),
            isouter=True,
        )
        .where(Sugerido.proveedor.isnot(None))
        .group_by(Sugerido.proveedor, Sugerido.producto)
        .having(func.sum(cant) > 0)
    )

    # Agrupar en Python por proveedor.
    carros: dict[str, CarroProveedor] = {}
    for row in db.execute(stmt).all():
        cantidad = float(row.cantidad or 0)
        costo = float(row.costo) if row.costo is not None else None
        subtotal = cantidad * (costo or 0)
        carro = carros.get(row.proveedor)
        if carro is None:
            carro = CarroProveedor(proveedor=row.proveedor, lineas=[])
            carros[row.proveedor] = carro
        carro.lineas.append(
            LineaCarro(
                producto=row.producto,
                descripcion=row.descripcion,
                clasificacion_abc=row.abc,
                cantidad=cantidad,
                costo_unitario=costo,
                subtotal_clp=subtotal,
            )
        )

    # Manuales-puras: pares (producto, sucursal) que tienen sugerencia manual vigente
    # pero NO existen en el sugerido del BI. Se agrupan bajo "Sin proveedor asignado"
    # con el costo del catalogo si esta disponible. Solo aplica cuando no hay filtros
    # de proveedor/marca/tipo_origen (en esos casos el comprador esta acotando).
    if not (f.proveedor or f.filtro1 or f.tipo_origen or f.abc):
        productos_sug = set(db.scalars(select(Sugerido.producto).distinct()).all())
        manual_rows = db.execute(
            select(
                SugerenciaManual.producto,
                func.sum(SugerenciaManual.unidades).label("manual"),
            )
            .where(SugerenciaManual.archivada.is_(False), _no_vencida())
            .group_by(SugerenciaManual.producto)
            .having(func.sum(SugerenciaManual.unidades) > 0)
        ).all()
        manual_solas = [(p, int(m)) for p, m in manual_rows if p not in productos_sug]
        if manual_solas:
            cat_map = {
                c.producto: c
                for c in db.scalars(
                    select(ProductoCatalogo).where(
                        ProductoCatalogo.producto.in_({p for p, _ in manual_solas})
                    )
                ).all()
            }
            proveedor_etq = "Sin proveedor asignado"
            carro_sp = carros.get(proveedor_etq) or CarroProveedor(
                proveedor=proveedor_etq, lineas=[]
            )
            carros[proveedor_etq] = carro_sp
            for prod, cantidad in manual_solas:
                cat = cat_map.get(prod)
                costo = float(cat.costo) if cat and cat.costo else None
                carro_sp.lineas.append(
                    LineaCarro(
                        producto=prod,
                        descripcion=cat.glosa if cat else None,
                        clasificacion_abc=None,
                        cantidad=float(cantidad),
                        costo_unitario=costo,
                        subtotal_clp=float(cantidad) * (costo or 0),
                    )
                )

    # Totales y orden.
    lista: list[CarroProveedor] = []
    for carro in carros.values():
        carro.lineas.sort(key=lambda x: x.subtotal_clp, reverse=True)
        carro.n_productos = len(carro.lineas)
        carro.total_unidades = sum(x.cantidad for x in carro.lineas)
        carro.total_clp = sum(x.subtotal_clp for x in carro.lineas)
        lista.append(carro)
    lista.sort(key=lambda c: c.total_clp, reverse=True)

    return CarrosResponse(
        carros=lista,
        total_proveedores=len(lista),
        total_clp=sum(c.total_clp for c in lista),
        total_unidades=sum(c.total_unidades for c in lista),
    )
