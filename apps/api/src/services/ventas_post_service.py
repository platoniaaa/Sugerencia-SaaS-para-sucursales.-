"""Consultas sobre el resumen pre-calculado de la Planilla Post Venta.

Los datos detallados viven en post_venta_fila (JSON posicional), pero los
KPIs y graficos los leemos de post_venta_resumen para ser rapidos.
"""
from __future__ import annotations

import json

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import PostVentaFila, PostVentaMeta, PostVentaResumen

settings = get_settings()


def _tenant() -> str:
    return settings.default_tenant_id


def periodos_disponibles(db: Session) -> list[str]:
    """Lista los periodos (YYYYMM) que tienen datos, ordenados ascendentemente."""
    rows = db.execute(
        select(PostVentaResumen.periodo)
        .where(PostVentaResumen.tenant_id == _tenant())
        .distinct()
        .order_by(PostVentaResumen.periodo.asc())
    ).all()
    return [r[0] for r in rows if r[0]]


def kpis(db: Session) -> dict:
    """Totales del periodo mas reciente + el anterior + variacion %."""
    periodos = periodos_disponibles(db)
    if not periodos:
        return {
            "periodo_actual": None, "periodo_anterior": None,
            "actual": {"clp": 0, "unidades": 0, "n_lineas": 0},
            "anterior": {"clp": 0, "unidades": 0, "n_lineas": 0},
            "var_clp_pct": None, "var_unidades_pct": None,
        }
    p_actual = periodos[-1]
    p_anterior = periodos[-2] if len(periodos) > 1 else None

    def _totales(periodo: str | None) -> dict:
        if not periodo:
            return {"clp": 0.0, "unidades": 0.0, "n_lineas": 0}
        row = db.execute(
            select(
                func.coalesce(func.sum(PostVentaResumen.total_clp), 0),
                func.coalesce(func.sum(PostVentaResumen.total_unidades), 0),
                func.coalesce(func.sum(PostVentaResumen.n_lineas), 0),
            )
            .where(
                PostVentaResumen.tenant_id == _tenant(),
                PostVentaResumen.periodo == periodo,
            )
        ).first()
        clp, unid, nl = row or (0, 0, 0)
        return {"clp": float(clp), "unidades": float(unid), "n_lineas": int(nl)}

    act = _totales(p_actual)
    ant = _totales(p_anterior)

    def _var(a: float, b: float) -> float | None:
        if not b:
            return None
        return ((a - b) / b) * 100.0

    return {
        "periodo_actual": p_actual,
        "periodo_anterior": p_anterior,
        "actual": act,
        "anterior": ant,
        "var_clp_pct": _var(act["clp"], ant["clp"]),
        "var_unidades_pct": _var(act["unidades"], ant["unidades"]),
    }


def serie_mensual(db: Session, meses: int = 12) -> list[dict]:
    """Serie por periodo: ultimos N meses con totales CLP + unidades."""
    rows = db.execute(
        select(
            PostVentaResumen.periodo,
            func.coalesce(func.sum(PostVentaResumen.total_clp), 0),
            func.coalesce(func.sum(PostVentaResumen.total_unidades), 0),
        )
        .where(PostVentaResumen.tenant_id == _tenant())
        .group_by(PostVentaResumen.periodo)
        .order_by(PostVentaResumen.periodo.asc())
    ).all()
    serie = [
        {"periodo": p, "clp": float(c), "unidades": float(u)}
        for p, c, u in rows if p
    ]
    return serie[-meses:]


def listar_lineas(
    db: Session,
    *,
    periodo_desde: str | None = None,
    periodo_hasta: str | None = None,
    sucursal: str | None = None,
    q: str | None = None,
    page: int = 1,
    limit: int = 100,
) -> tuple[list[dict], int, list[str]]:
    """Devuelve lineas detalladas de Post Venta como dicts {columna: valor}.

    Parsea el JSON posicional usando el orden guardado en PostVentaMeta.columnas.
    Si q tiene valor, filtra por LIKE en el JSON crudo (rapido, no muy preciso pero
    sirve para buscar texto: producto, descripcion, cliente, etc.).
    """
    meta = db.get(PostVentaMeta, _tenant())
    if not meta:
        return [], 0, []
    columnas = json.loads(meta.columnas)

    base = select(PostVentaFila).where(PostVentaFila.tenant_id == _tenant())
    if periodo_desde:
        base = base.where(PostVentaFila.periodo >= periodo_desde)
    if periodo_hasta:
        base = base.where(PostVentaFila.periodo <= periodo_hasta)
    if sucursal:
        base = base.where(PostVentaFila.sucursal == sucursal)
    if q and q.strip():
        like = f"%{q.strip()}%"
        base = base.where(PostVentaFila.datos.ilike(like))

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = (
        base.order_by(desc(PostVentaFila.periodo), desc(PostVentaFila.id))
        .offset((page - 1) * limit)
        .limit(limit)
    )
    filas = list(db.scalars(stmt).all())

    items: list[dict] = []
    for f in filas:
        try:
            valores = json.loads(f.datos)
        except Exception:
            valores = []
        d: dict = {"_id": f.id}
        for i, col in enumerate(columnas):
            d[col] = valores[i] if i < len(valores) else None
        items.append(d)

    return items, total, columnas


def por_sucursal(db: Session, periodo: str) -> list[dict]:
    """Lista de sucursales con sus totales para un periodo dado, orden por CLP desc."""
    rows = db.execute(
        select(
            PostVentaResumen.sucursal,
            func.coalesce(func.sum(PostVentaResumen.total_clp), 0),
            func.coalesce(func.sum(PostVentaResumen.total_unidades), 0),
            func.coalesce(func.sum(PostVentaResumen.n_lineas), 0),
        )
        .where(
            PostVentaResumen.tenant_id == _tenant(),
            PostVentaResumen.periodo == periodo,
        )
        .group_by(PostVentaResumen.sucursal)
        .order_by(desc(func.sum(PostVentaResumen.total_clp)))
    ).all()
    return [
        {
            "sucursal": s or "(sin sucursal)",
            "clp": float(c),
            "unidades": float(u),
            "n_lineas": int(n),
        }
        for s, c, u, n in rows
    ]
