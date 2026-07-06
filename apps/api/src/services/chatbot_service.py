"""Chatbot del sugerido — Gemini + tools que consultan la propia DB.

El LLM no toca SQL directo: solo puede invocar las herramientas definidas aqui.
Eso evita inyecciones, fugas de datos sensibles y alucinaciones sobre fuentes
que no existen. Cada tool delega en services ya probados (`sugerido_service`,
`stock_service`).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    ProductoCatalogo,
    Sugerido,
    SugerenciaManual,
    SugerenciaRecurrente,
)
from ..schemas import SugeridoFiltros
from . import stock_service, sugerido_service

settings = get_settings()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt: instrucciones de respuesta + contexto completo del modelo.
# ---------------------------------------------------------------------------
# Resumen corto de respaldo: solo se usa si no se encuentra el documento del
# modelo en el deploy. Mantiene al chatbot util aunque pierda el contexto largo.
_RESUMEN_FALLBACK = """REGLAS DE NEGOCIO IMPORTANTES (del modelo Power BI):
- Formula principal: Sugerido Suc = DD * (CO + LT) + SS - SA - ST
  donde DD=Demanda Diaria, CO=Ciclo de Orden (5 dias habiles),
  LT=Lead Time efectivo, SS=Stock Seguridad, SA=Stock Activo, ST=Stock en Transito.
- LT efectivo: si el producto se abastece via CD, usa 1-2 dias (CD->sucursal).
  Si no, usa el lead time real del proveedor.
- Demanda diaria se calcula con 22 dias habiles/mes (NO dias corridos).
- Clases ABC: A, B y C calculan sugerido. C usa ventana de 6 meses.
- "Pedir = Si" significa que el sugerido neto es > 0 despues de descontar stock.
- Las sugerencias manuales se SUMAN al sugerido del BI (no lo reemplazan)."""


def _cargar_contexto_modelo() -> str:
    """Carga el documento del modelo Power BI (DAX, medidas, reglas, vistas) que
    vive en la raiz del repo. Es la MISMA fuente que documenta el equipo, asi el
    chatbot razona sobre el modelo con el contexto completo. Si el deploy no
    incluye el archivo, cae al resumen corto para no quedar sin reglas."""
    try:
        ruta = Path(__file__).resolve().parents[4] / "CLAUDE contexto modelo.md"
        texto = ruta.read_text(encoding="utf-8").strip()
        if texto:
            return texto
    except Exception as e:
        logger.warning(
            "No se pudo cargar 'CLAUDE contexto modelo.md' (%s); uso resumen corto", e
        )
    return _RESUMEN_FALLBACK


_INSTRUCCIONES = """Sos el asistente del sugerido de compras de Curifor (repuestos automotrices, Chile).

OBJETIVO: ayudar al equipo de compras a entender el sugerido del Power BI y los
datos asociados (catalogo, stock, ventas, sugerencias manuales). Sos un asistente
de SOLO CONSULTA: respondes preguntas, no modificas datos.

COMO RESPONDER:
- En espanol de Chile, directo y breve.
- Cuando el usuario pregunta por un producto o sugerido, usa las herramientas
  para traer datos reales antes de responder. NO inventes valores.
- Tenes herramientas para: detalle de producto/sugerido, historico de ventas,
  busqueda, RANKINGS top-N por proveedor/sucursal/marca, TOTALES del sugerido,
  STOCK por sucursal y SUGERENCIAS manuales/recurrentes vigentes. Usalas en vez
  de estimar.
- Para preguntas sobre como funciona el modelo (formulas, medidas, reglas, clases
  ABC, vistas, gotchas de DAX), apoyate en el CONTEXTO DEL MODELO de mas abajo.
- El CONTEXTO DEL MODELO se mantiene a mano y puede no reflejar cambios muy
  recientes del Power BI. Si la pregunta depende de un detalle fino o reciente del
  modelo, responde con lo que sabes pero sugiere verificar con el equipo.
- El CONTEXTO DEL MODELO nombra a personas del proyecto (Francisco, Marilyn "la
  Mary", Andres). Son referencias del negocio, NO necesariamente quien te escribe.
  No trates al usuario por ninguno de esos nombres ni asumas quien es; si no sabes
  su nombre, simplemente no lo uses.
- Si te falta un dato, pedi clarificacion (codigo de producto, sucursal, etc.).
- Para explicar "por que tal sugerido", trae los numeros reales con las tools y
  explica el calculo usando las reglas del modelo.
"""

SYSTEM_PROMPT = (
    _INSTRUCCIONES
    + "\n=== CONTEXTO DEL MODELO POWER BI (referencia completa) ===\n"
    + _cargar_contexto_modelo()
)


# ---------------------------------------------------------------------------
# Tools: cada una recibe argumentos serializables, devuelve dict/str para el LLM.
# ---------------------------------------------------------------------------
def _tool_obtener_producto(db: Session, codigo: str) -> dict:
    """Trae catalogo + stock total + cuantas sucursales lo piden."""
    cat = db.scalars(
        select(ProductoCatalogo).where(ProductoCatalogo.producto == codigo)
    ).first()
    if not cat:
        return {"error": f"Producto '{codigo}' no encontrado en el catalogo."}
    # Cuantas sucursales lo tienen en el sugerido y suma total
    agg = db.execute(
        select(
            func.count().label("n_sucs"),
            func.coalesce(func.sum(Sugerido.total_sugerido_suc), 0).label("total"),
        ).where(Sugerido.producto == codigo)
    ).one()
    return {
        "producto": cat.producto,
        "descripcion": cat.glosa,
        "familia": cat.familia,
        "procedencia": cat.procedencia,
        "costo_unitario": cat.costo,
        "stock_total_catalogo": cat.stock_total,
        "reemplazo": cat.reemplazo,
        "unidad": cat.unidad,
        "en_sugerido_sucursales": int(agg.n_sucs or 0),
        "total_sugerido_todas_sucursales": float(agg.total or 0),
    }


def _tool_obtener_sugerido(db: Session, producto: str, sucursal: str) -> dict:
    """Trae la fila del sugerido del BI + ajuste por sugerencias manuales vigentes."""
    s = sugerido_service.detalle(db, producto, sucursal)
    if not s:
        return {
            "error": (
                f"No hay sugerido del BI para producto='{producto}', sucursal='{sucursal}'. "
                f"Verifica codigo y nombre exacto de sucursal."
            )
        }
    # Sumar manuales vigentes (mismo helper que usa la plataforma)
    manual = db.scalar(
        select(func.coalesce(func.sum(SugerenciaManual.unidades), 0))
        .where(
            SugerenciaManual.producto == producto,
            SugerenciaManual.sucursal_id == sucursal,
            SugerenciaManual.archivada.is_(False),
            sugerido_service._no_vencida(),
        )
    ) or 0
    return {
        "producto": s.producto,
        "descripcion": s.descripcion,
        "sucursal": s.nombre_sucursal,
        "sucursal_id": s.sucursal_id,
        "empresa": s.empresa,
        "abc": s.clasificacion_abc,
        "proveedor": s.proveedor,
        "marca": s.filtro1_final,
        "tipo_origen": s.tipo_origen,
        "abastece_cd": s.abastece_cd,
        "lead_time_dias": s.lead_time_dias,
        "lt_efectivo": s.lt_efectivo,
        "demanda_mensual": s.demanda_mensual,
        "demanda_diaria": s.demanda_diaria,
        "stock_seguridad": s.stock_seguridad,
        "punto_de_pedido": s.punto_de_pedido,
        "stock_activo": s.stock_activo_suc,
        "stock_en_transito": s.stock_en_transito_suc,
        "stock_en_cd": s.stock_en_cd,
        "sugerido_compra_neto": s.sugerido_compra_neto,
        "sugerido_traslado": s.sugerido_traslado,
        "total_sugerido_bi": s.total_sugerido_suc,
        "ajuste_manual_vigente": int(manual),
        "total_sugerido_con_manual": float(s.total_sugerido_suc or 0) + int(manual),
        "pedir": s.pedir,
        "costo_unitario": s.costo_unitario,
    }


def _tool_historico_ventas(
    db: Session, producto: str, sucursal: str | None = None
) -> dict:
    """Ultimos 12 meses de venta. sucursal opcional (si no, suma de todas)."""
    return sugerido_service.ventas_12m(db, producto, sucursal)


def _tool_buscar_productos(db: Session, texto: str, limite: int = 10) -> dict:
    """Busqueda fuzzy en codigo o descripcion del catalogo."""
    like = f"%{texto}%"
    rows = db.scalars(
        select(ProductoCatalogo)
        .where(
            (ProductoCatalogo.producto.ilike(like))
            | (ProductoCatalogo.glosa.ilike(like))
        )
        .limit(limite)
    ).all()
    return {
        "encontrados": len(rows),
        "items": [
            {
                "producto": r.producto,
                "descripcion": r.glosa,
                "familia": r.familia,
                "costo": r.costo,
            }
            for r in rows
        ],
    }


def _tool_ranking_sugerido(
    db: Session, por: str, limite: int = 10, vista: str = "todas"
) -> dict:
    """Top-N grupos (proveedor/sucursal/marca) por monto sugerido, ordenado por valor CLP."""
    if por not in sugerido_service.DIMENSIONES:
        return {
            "error": (
                f"Dimension '{por}' no valida. Usa una de: "
                f"{', '.join(sugerido_service.DIMENSIONES)}."
            )
        }
    limite = max(1, min(int(limite or 10), 50))
    grupos = sugerido_service.agrupado(db, SugeridoFiltros(vista=vista), por, limite=limite)
    return {"por": por, "vista": vista, "grupos": grupos}


def _tool_resumen_sugerido(
    db: Session, vista: str = "todas", proveedor: str | None = None
) -> dict:
    """Totales del sugerido (monto, valor CLP, n productos/proveedores) con filtros opcionales."""
    filtros = SugeridoFiltros(vista=vista, proveedor=proveedor)
    return {
        "vista": vista,
        "proveedor": proveedor,
        **sugerido_service.kpis(db, filtros),
    }


def _tool_stock_producto(db: Session, producto: str) -> dict:
    """Stock de un producto desglosado por sucursal/bodega, mas el total."""
    filas = stock_service.stock_por_sucursal(db, producto)
    if not filas:
        return {
            "producto": producto,
            "stock_total": 0,
            "detalle": [],
            "nota": "Sin stock cargado para este producto (revisa el codigo exacto).",
        }
    total = sum(f["stock"] for f in filas)
    return {"producto": producto, "stock_total": total, "detalle": filas}


def _tool_sugerencias_vigentes(
    db: Session, producto: str | None = None, sucursal: str | None = None
) -> dict:
    """Sugerencias manuales vigentes y recurrencias activas para un producto/sucursal."""
    mq = select(SugerenciaManual).where(
        SugerenciaManual.archivada.is_(False), sugerido_service._no_vencida()
    )
    rq = select(SugerenciaRecurrente).where(SugerenciaRecurrente.activa.is_(True))
    if producto:
        mq = mq.where(SugerenciaManual.producto == producto)
        rq = rq.where(SugerenciaRecurrente.producto == producto)
    if sucursal:
        mq = mq.where(SugerenciaManual.sucursal_id == sucursal)
        rq = rq.where(SugerenciaRecurrente.sucursal_id == sucursal)
    manuales = [
        {
            "producto": m.producto,
            "sucursal_id": m.sucursal_id,
            "unidades": m.unidades,
            "motivo": m.motivo,
            "creado_por": m.creado_por,
        }
        for m in db.scalars(mq.limit(50)).all()
    ]
    recurrentes = [
        {
            "producto": r.producto,
            "sucursal_id": r.sucursal_id,
            "modo": r.modo,
            "unidades": r.unidades,
            "cada_dias": r.cada_dias,
            "proxima_ejecucion": str(r.proxima_ejecucion),
            "motivo": r.motivo,
        }
        for r in db.scalars(rq.limit(50)).all()
    ]
    return {"manuales_vigentes": manuales, "recurrencias_activas": recurrentes}


TOOLS = {
    "obtener_producto": _tool_obtener_producto,
    "obtener_sugerido": _tool_obtener_sugerido,
    "historico_ventas": _tool_historico_ventas,
    "buscar_productos": _tool_buscar_productos,
    "ranking_sugerido": _tool_ranking_sugerido,
    "resumen_sugerido": _tool_resumen_sugerido,
    "stock_producto": _tool_stock_producto,
    "sugerencias_vigentes": _tool_sugerencias_vigentes,
}


def _tool_declarations():
    """Schema OpenAPI/JSON de las tools para Gemini (function calling)."""
    from google.genai import types

    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="obtener_producto",
                    description=(
                        "Obtiene la info de catalogo de un producto: descripcion, "
                        "familia, costo, stock total, reemplazo. Usar cuando el "
                        "usuario pregunta 'que producto es X' o pide info general."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "codigo": types.Schema(
                                type=types.Type.STRING,
                                description="Codigo exacto del producto (ej. '20 BXO5W30AA')",
                            )
                        },
                        required=["codigo"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="obtener_sugerido",
                    description=(
                        "Trae la fila del sugerido del BI para un par producto/sucursal "
                        "con TODAS las medidas (DD, LT, SS, Stock, etc.) y el ajuste "
                        "por sugerencias manuales. Usar para explicar 'por que el "
                        "sugerido es X' o ver el detalle de calculo."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "producto": types.Schema(
                                type=types.Type.STRING,
                                description="Codigo del producto",
                            ),
                            "sucursal": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "ID de la sucursal (LINDEROS, CURICO, "
                                    "RANCAGUA, etc.) - en mayusculas"
                                ),
                            ),
                        },
                        required=["producto", "sucursal"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="historico_ventas",
                    description=(
                        "Devuelve la venta mensual de un producto en los ultimos 12 "
                        "meses (general y por sucursal si se especifica). Usar para "
                        "preguntas tipo 'cuanto vendi de X' o 'tendencia de venta'."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "producto": types.Schema(type=types.Type.STRING),
                            "sucursal": types.Schema(
                                type=types.Type.STRING,
                                description="Opcional. Si no se pasa, suma todas las sucursales.",
                            ),
                        },
                        required=["producto"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="buscar_productos",
                    description=(
                        "Busqueda parcial por codigo o descripcion. Devuelve hasta N "
                        "productos. Usar cuando el usuario no recuerda el codigo exacto."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "texto": types.Schema(type=types.Type.STRING),
                            "limite": types.Schema(
                                type=types.Type.INTEGER,
                                description="Default 10",
                            ),
                        },
                        required=["texto"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="ranking_sugerido",
                    description=(
                        "Ranking top-N por monto sugerido (valor CLP) agrupado por "
                        "proveedor, sucursal o marca. Usar para 'que proveedores hay que "
                        "comprar mas', 'top 10 sucursales por sugerido', etc."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "por": types.Schema(
                                type=types.Type.STRING,
                                description="Dimension: 'proveedor', 'sucursal' o 'marca'.",
                            ),
                            "limite": types.Schema(
                                type=types.Type.INTEGER,
                                description="Cuantos grupos traer (default 10, max 50).",
                            ),
                            "vista": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "Vista del proceso: 'todas' (default), 'sucursales' "
                                    "(compra directa), 'cd' (compra del CD) o "
                                    "'distribucion' (traslados CD->sucursal)."
                                ),
                            ),
                        },
                        required=["por"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="resumen_sugerido",
                    description=(
                        "Totales agregados del sugerido: monto total, valor total en CLP, "
                        "cantidad de productos y de proveedores. Usar para 'cuanto suma el "
                        "sugerido', 'cuantos productos hay que pedir', etc."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "vista": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "'todas' (default), 'sucursales', 'cd' o 'distribucion'."
                                ),
                            ),
                            "proveedor": types.Schema(
                                type=types.Type.STRING,
                                description="Opcional. Acota a un proveedor (busqueda parcial).",
                            ),
                        },
                    ),
                ),
                types.FunctionDeclaration(
                    name="stock_producto",
                    description=(
                        "Stock fisico de un producto desglosado por sucursal/bodega, mas el "
                        "total. Usar para 'cuanto stock hay de X' o 'en que sucursales hay X'."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "producto": types.Schema(
                                type=types.Type.STRING,
                                description="Codigo exacto del producto.",
                            )
                        },
                        required=["producto"],
                    ),
                ),
                types.FunctionDeclaration(
                    name="sugerencias_vigentes",
                    description=(
                        "Lista las sugerencias manuales vigentes y las recurrencias activas, "
                        "opcionalmente filtradas por producto y/o sucursal. Usar para 'que "
                        "sugerencias manuales hay para X' o 'que recurrencias estan activas'."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "producto": types.Schema(
                                type=types.Type.STRING,
                                description="Opcional. Codigo del producto.",
                            ),
                            "sucursal": types.Schema(
                                type=types.Type.STRING,
                                description="Opcional. ID de la sucursal en mayusculas.",
                            ),
                        },
                    ),
                ),
            ]
        )
    ]


# ---------------------------------------------------------------------------
# Loop de agent: pregunta -> Gemini -> (tool_call -> ejecutar -> seguir) -> respuesta
# ---------------------------------------------------------------------------
class GeminiNoConfigurado(Exception):
    """API key vacia. El endpoint lo traduce a 503."""


def responder(
    db: Session,
    pregunta: str,
    historial: list[dict] | None = None,
    max_iter: int = 5,
) -> str:
    """Procesa una pregunta y devuelve la respuesta final del modelo.

    `historial` es opcional: lista de {role: "user"|"model", text: str} para mantener
    el hilo. Si viene None, es una conversacion nueva.
    """
    if not settings.gemini_api_key:
        raise GeminiNoConfigurado(
            "Falta GEMINI_API_KEY. Generala gratis en https://aistudio.google.com "
            "y configurala en Render."
        )

    # Import lazy: la dependencia es opcional (si falla, no rompe el resto del backend)
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)

    # Construir historial en el formato del SDK
    contents: list[types.Content] = []
    for m in historial or []:
        role = "user" if m.get("role") == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part(text=m.get("text", ""))])
        )
    contents.append(types.Content(role="user", parts=[types.Part(text=pregunta)]))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=_tool_declarations(),
        temperature=0.2,
    )

    # Loop: si Gemini pide ejecutar una tool, la corremos y volvemos a llamar.
    for _ in range(max_iter):
        response = client.models.generate_content(
            model=settings.gemini_modelo,
            contents=contents,
            config=config,
        )
        candidate = response.candidates[0] if response.candidates else None
        if not candidate or not candidate.content or not candidate.content.parts:
            return "(No recibi respuesta del modelo)"

        # Recolectar texto y/o tool calls
        tool_calls = []
        text_partes = []
        for part in candidate.content.parts:
            if getattr(part, "function_call", None):
                tool_calls.append(part.function_call)
            elif getattr(part, "text", None):
                text_partes.append(part.text)

        if not tool_calls:
            # Respuesta final
            return "".join(text_partes).strip() or "(respuesta vacia)"

        # Agregar el turno del modelo (con sus tool_calls) al historial
        contents.append(candidate.content)
        # Ejecutar cada tool y agregar la respuesta
        for call in tool_calls:
            args = dict(call.args or {})
            fn = TOOLS.get(call.name)
            if not fn:
                resultado: Any = {"error": f"Tool desconocida: {call.name}"}
            else:
                try:
                    resultado = fn(db, **args)
                except TypeError as e:
                    resultado = {"error": f"Argumentos invalidos: {e}"}
                except Exception as e:
                    resultado = {"error": f"Fallo la tool: {e}"}
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=call.name,
                                response={"result": json.loads(json.dumps(resultado, default=str))},
                            )
                        )
                    ],
                )
            )

    return "(El modelo no pudo terminar la respuesta en el limite de iteraciones)"
