"""Corre el motor con los crudos reales y manda el resultado a la plataforma.

Este es el job que reemplaza al Power BI. Lee los Excel que el usuario publica en
SharePoint (carpeta sincronizada localmente), calcula el sugerido con el motor
—el que tiene paridad demostrada contra el modelo— y sube el CSV a la nube.

    python -m src.jobs.correr_motor_real                # compara (modo sombra)
    python -m src.jobs.correr_motor_real --oficial      # carga de verdad

**Por defecto va en modo SOMBRA**: sube el resultado al endpoint de comparacion,
que contrasta contra lo que produjo el Power BI y guarda un reporte sin tocar la
tabla que ven los compradores. Recien cuando la paridad se sostenga varios dias
se corre con `--oficial`, y ahi el mismo CSV entra por el endpoint de carga.

Configuracion (por entorno, nunca en el repo):
    MOTOR_CRUDOS_DIR      carpeta con los Excel (la biblioteca de SharePoint sincronizada)
    MOTOR_SNAPSHOT_DIR    CSV congelados de las tablas chicas y estables
    PLATAFORMA_API_URL    URL del backend
    PLATAFORMA_EMAIL      credenciales de un usuario admin de la plataforma
    PLATAFORMA_PASSWORD
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

# El proxy corporativo intercepta el HTTPS con su propio certificado. truststore
# hace que Python confie en el almacen de certificados del sistema (Windows), donde
# TI instalo ese certificado, en vez del bundle propio de Python -> las llamadas a
# la plataforma dejan de fallar con "self-signed certificate in certificate chain".
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 - si no esta, se sigue con el bundle por defecto
    pass

_API_DIR = Path(__file__).resolve().parents[2]
# La carpeta de crudos la resuelve `motor.fuentes` (variable de entorno o .env).
# Tener aqui una copia de esa logica hacia que el job leyera el stock y el
# seguimiento de la carpeta buena y las VENTAS de la copia vieja de data/crudos.
from ..motor import fuentes as _fuentes  # noqa: E402

CRUDOS_DIR = _fuentes.CRUDOS_DIR
SNAPSHOT_DIR = Path(os.environ.get("MOTOR_SNAPSHOT_DIR", _API_DIR / "data" / "paridad"))
SALIDA = _API_DIR / "data" / "sugerido_motor.csv"
SALIDA_LT = _API_DIR / "data" / "lead_time_motor.csv"
SALIDA_STOCK = _API_DIR / "data" / "stock_unificado_motor.csv"
SALIDA_TRANSITO = _API_DIR / "data" / "stock_transito_motor.csv"


def _leer_env() -> dict[str, str]:
    """Variables PLATAFORMA_* del .env del repo. Vacio si no hay archivo."""
    env = _fuentes._REPO_DIR / ".env"
    if not env.exists():
        return {}
    valores = {}
    for linea in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        linea = linea.strip()
        if linea.startswith("PLATAFORMA_") and "=" in linea:
            k, v = linea.split("=", 1)
            valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


def _credenciales() -> tuple[str, str | None, str | None]:
    """(base_url, email, password) desde el entorno o el .env del repo."""
    cfg = {**_leer_env(), **{k: v for k, v in os.environ.items() if k.startswith("PLATAFORMA_")}}
    return (
        cfg.get("PLATAFORMA_API_URL", "http://localhost:8000").rstrip("/"),
        cfg.get("PLATAFORMA_EMAIL"),
        cfg.get("PLATAFORMA_PASSWORD"),
    )


def obtener_config() -> dict | None:
    """Pide a la plataforma la configuracion calibrable del modelo.

    Devuelve None si no se puede (sin credenciales, sin red, error): en ese caso
    el motor sigue con las constantes de `parametros.py`, que son iguales a los
    defaults de la config, asi que el resultado no cambia.
    """
    import httpx

    base, email, password = _credenciales()
    if not email or not password:
        return None
    try:
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{base}/api/auth/login", json={"email": email, "password": password})
            r.raise_for_status()
            token = r.json()["token"]
            r = c.get(f"{base}/api/admin/config-modelo", headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            return r.json()
    except Exception as e:  # noqa: BLE001
        print(f"  (config remota no disponible, se usan los valores del codigo: {e})")
        return None


def aplicar_config(cfg: dict) -> None:
    """Sobrescribe las constantes de `parametros.py` con la config remota.

    Los modulos del motor leen `P.X` en tiempo de ejecucion, asi que rebindear los
    atributos del modulo antes de correr el pipeline basta para calibrarlo sin
    tocar codigo. Solo se tocan las llaves presentes (robusto a versiones futuras).
    """
    from ..motor import parametros as P

    if "ciclo_orden_dias" in cfg:
        P.CICLO_ORDEN_DIAS = int(cfg["ciclo_orden_dias"])
    if "ciclo_orden_dias_cd" in cfg:
        P.CICLO_ORDEN_DIAS_CD = int(cfg["ciclo_orden_dias_cd"])
    if cfg.get("z_por_clase"):
        P.Z_POR_CLASE = {k: float(v) for k, v in cfg["z_por_clase"].items()}
    if cfg.get("z_importado_cd"):
        P.Z_IMPORTADO_CD = {k: float(v) for k, v in cfg["z_importado_cd"].items()}
    if "lead_time_fallback_dias" in cfg:
        P.LT_FALLBACK_DIAS = int(cfg["lead_time_fallback_dias"])
    if "winsor_k" in cfg:
        P.WINSOR_K = float(cfg["winsor_k"])
    if "dias_habiles_mes" in cfg:
        P.DIAS_HABILES_MES = int(cfg["dias_habiles_mes"])
    if "lt_cd_rm_dias" in cfg:
        P.LT_CD_RM = int(cfg["lt_cd_rm_dias"])
    if "lt_cd_resto_dias" in cfg:
        P.LT_CD_RESTO = int(cfg["lt_cd_resto_dias"])
    if "lt_tope_dias" in cfg:
        P.LT_TOPE_DIAS = int(cfg["lt_tope_dias"])
    if "transito_nacional_dias" in cfg:
        P.TRANSITO_VENTANA_NACIONAL_DIAS = int(cfg["transito_nacional_dias"])
    if "transito_importado_dias" in cfg:
        P.TRANSITO_VENTANA_IMPORTADO_DIAS = int(cfg["transito_importado_dias"])
    for clave, attr in (
        ("abc_umbral_a_m6", "ABC_UMBRAL_A_M6"),
        ("abc_umbral_b_m6", "ABC_UMBRAL_B_M6"),
        ("abc_umbral_c_m6", "ABC_UMBRAL_C_M6"),
        ("abc_umbral_c_m3", "ABC_UMBRAL_C_M3"),
        ("abc_umbral_c_m12", "ABC_UMBRAL_C_M12"),
    ):
        if clave in cfg:
            setattr(P, attr, int(cfg[clave]))
    origen = "default" if cfg.get("es_default") else f"editada por {cfg.get('creado_por')}"
    print(
        f"  config del modelo: ciclo {P.CICLO_ORDEN_DIAS}/{P.CICLO_ORDEN_DIAS_CD} dias, "
        f"Z {P.Z_POR_CLASE}, winsor k={P.WINSOR_K} ({origen})"
    )


def _fin_mes_cerrado(hoy: date) -> date:
    """Primer dia del mes en curso: el motor usa meses CERRADOS."""
    return hoy.replace(day=1)


def _buscar(fuente: str, obligatorio: bool = True) -> Path | None:
    """Archivo de una fuente declarada en `motor.fuentes.FUENTES`.

    Usa esas specs y NO patrones propios: ahi cada fuente ya trae sus exclusiones
    ("seguimiento" nacional excluye importado y frontera). Un patron ad-hoc como
    "*seguimiento*compras*" matchea las tres, y al desempatar por fecha el motor
    terminaba leyendo el importado como si fuera el nacional: 48.000 ordenes de
    compra quedaban fuera y casi todos los productos se quedaban sin proveedor.
    """
    from ..motor import fuentes

    try:
        return fuentes.ruta_de(fuente)
    except FileNotFoundError:
        if obligatorio:
            raise
        return None


def _archivos_de_ventas(fin_mes_cerrado: date) -> list[Path]:
    """Respaldos de venta que cubren la ventana de 12 meses que usa el motor.

    Los respaldos vienen por ano y el historico completo pesa cientos de MB, pero
    el sugerido solo mira los 12 meses cerrados: para jul-2026 alcanzan 2026 y
    2025. Cargar 2018-2024 ademas seria minutos de lectura para nada.
    """
    anios = {str(fin_mes_cerrado.year), str(fin_mes_cerrado.year - 1)}
    if not CRUDOS_DIR.exists():
        return []
    # Los respaldos se identifican POR DESCARTE: se llaman "2025 (4).xlsx" y no hay
    # patron que los reconozca, pero si se sabe que no son stock, ni seguimiento, ni
    # el mix, ni las ventas de Frontera (que tienen otro esquema y otros filtros).
    return sorted(
        p for p in CRUDOS_DIR.rglob("*.xlsx")
        if not p.name.startswith("~$")
        and not _fuentes.es_de_alguna_fuente(p.name, excepto="ventas")
        and any(a in p.name for a in anios)
    )


def construir_csv(hoy: date | None = None) -> Path:
    """Corre el pipeline completo con los crudos reales y escribe el CSV contrato."""
    from ..motor import fuentes_reales, lectores_excel, pipeline

    hoy = hoy or date.today()
    # Calibracion: si la plataforma tiene parametros configurados, se aplican antes
    # de calcular. Si no responde, se sigue con los valores del codigo.
    cfg = obtener_config()
    if cfg:
        aplicar_config(cfg)
    ventas = _archivos_de_ventas(_fin_mes_cerrado(hoy))
    # Se listan en el log a proposito: los respaldos se eligen POR DESCARTE, asi que
    # un archivo nuevo cualquiera con el ano en el nombre entra aca sin avisar. Ver
    # la lista es la unica forma barata de cachar que se colo algo que no es venta.
    print(f"  respaldos de venta: {[p.name for p in ventas] or '(ninguno)'}")
    # Ventas Frontera (E07): opcional, pero sin ellas el motor pierde los combos
    # que solo se venden ahi y subestima la demanda de los que venden en las dos.
    frontera_xlsx = _buscar("ventas_frontera", obligatorio=False)
    ventas_frontera = (
        lectores_excel.leer_ventas_frontera_excel(frontera_xlsx) if frontera_xlsx else None
    )
    fuentes = fuentes_reales.cargar_fuentes_reales(
        stock_curifor_xlsx=_buscar("stock_bodegas"),
        stock_frontera_xlsx=_buscar("stock_bodegas_frontera"),
        snapshot_dir=SNAPSHOT_DIR,
        seguimiento_nacional_xlsx=_buscar("seguimiento_curifor_nacional", obligatorio=False),
        seguimiento_importado_xlsx=_buscar("seguimiento_curifor_importado", obligatorio=False),
        seguimiento_frontera_xlsx=_buscar("seguimiento_frontera", obligatorio=False),
        ventas_xlsx=ventas or None,
        ventas_frontera_crudo=ventas_frontera,
        # Con estos dos el motor CALCULA las tablas chicas (categoria, catalogo,
        # grupos de reemplazo) en vez de leer el snapshot congelado del BI.
        listado_maestro=_buscar("catalogo", obligatorio=False),
        mix_reemplazos_xlsx=_buscar("mix_reemplazos", obligatorio=False),
        # Listas de precios de proveedor: dan el precio de venta para el margen.
        # Opcionales; sin ellas esas columnas salen vacias y el resto no cambia.
        precios_ford_xlsx=_buscar("precios_ford", obligatorio=False),
        precios_gildemeister_xlsx=_buscar("precios_gildemeister", obligatorio=False),
        fin_mes_cerrado=_fin_mes_cerrado(hoy),
    )
    df = pipeline.ejecutar(fuentes, fin_mes_cerrado=_fin_mes_cerrado(hoy), hoy=hoy)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    # El lead time calculado se guarda aparte para publicarlo a la plataforma: es
    # el "por que" detras del sugerido (de donde sale el LT de cada proveedor y con
    # cuantas muestras), y se mira cuando un sugerido se ve raro.
    _guardar_lead_time(fuentes)
    # El stock por bodega: la plataforma lo muestra en la ficha del catalogo. Antes
    # esa tabla la llenaba el Power BI Desktop y al retirarlo quedo congelada.
    _guardar_stock_unificado(fuentes)
    # El transito de TODOS los productos, no solo de los que el sugerido evalua.
    _guardar_transito(fuentes)
    # Las fuentes quedan a mano para que `run` publique la equivalencia de SKU
    # sin volver a leer los Excel (son minutos de lectura).
    globals()['_ULTIMAS_FUENTES'] = fuentes
    return pipeline.exportar_csv(df, SALIDA)


def _guardar_stock_unificado(fuentes: dict) -> Path | None:
    """Escribe el stock por producto x bodega de las dos empresas, con su origen."""
    import polars as pl

    partes = []
    for clave, origen in (("stock_bodegas", "CURIFOR"), ("stock_bodegas_frontera", "FRONTERA")):
        df = fuentes.get(clave)
        if df is None or df.is_empty():
            continue
        partes.append(
            df.select(
                pl.col("Producto").alias("producto"),
                pl.col("Bodega").alias("bodega"),
                pl.col("SucursalID").alias("sucursal_id"),
                pl.col("Stock").cast(pl.Float64).alias("stock"),
                pl.lit(origen).alias("origen"),
            )
        )
    if not partes:
        return None
    # Sin filas en cero: no aportan nada al catalogo y son la mayoria del archivo.
    pl.concat(partes).filter(pl.col("stock") != 0).write_csv(SALIDA_STOCK)
    return SALIDA_STOCK


def _guardar_transito(fuentes: dict) -> Path | None:
    """Escribe el transito vigente por (producto, sucursal) de TODO el seguimiento.

    El sugerido ya calcula este numero, pero solo lo publica pegado a sus propias
    filas (`sugerido.stock_en_transito_suc`), y el sugerido es un subconjunto chico
    del catalogo: 1.936 filas para Linderos de 409K productos. Cuando un vendedor
    pide un repuesto que no esta en el sugerido -que es el caso normal, porque pide
    justo lo que no se stockea-, el comprador no tenia forma de saber si ya venia
    en camino, y podia comprar de nuevo algo que ya estaba pedido.

    Se usa la MISMA funcion del motor (`_stock_transito`) a proposito: si aqui se
    reimplementara el filtro de "OC vigente", la plataforma mostraria un numero y
    el sugerido otro, y no habria forma de saber cual creer.
    """
    from datetime import date as _date

    from ..motor.sugerido import _stock_transito

    seg = fuentes.get("seguimiento_transito")
    if seg is None or seg.is_empty():
        return None
    df = _stock_transito(seg, _date.today(), con_fecha=True)
    if df.is_empty():
        return None
    df.rename(
        {"producto_master": "producto", "sucursal_final": "sucursal_id",
         "stock_transito": "cantidad"}
    ).write_csv(SALIDA_TRANSITO)
    return SALIDA_TRANSITO


def publicar_transito() -> dict | None:
    """Sube a la plataforma el transito vigente (reemplaza la foto anterior)."""
    import csv

    import httpx

    if not SALIDA_TRANSITO.exists():
        return None
    base, email, password = _credenciales()
    if not email or not password:
        return None
    with open(SALIDA_TRANSITO, encoding="utf-8", newline="") as f:
        filas = [
            {
                "producto": r["producto"],
                "sucursal_id": r["sucursal_id"] or None,
                "cantidad": float(r["cantidad"]),
                "pedido_desde": (r.get("pedido_desde") or "")[:10] or None,
            }
            for r in csv.DictReader(f)
            if r.get("producto") and r.get("cantidad")
        ]
    try:
        with httpx.Client(timeout=300) as c:
            r = c.post(f"{base}/api/auth/login", json={"email": email, "password": password})
            r.raise_for_status()
            token = r.json()["token"]
            r = c.post(
                f"{base}/api/admin/stock-transito",
                headers={"Authorization": f"Bearer {token}"},
                json={"filas": filas},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:  # noqa: BLE001 - publicar el transito nunca debe romper la carga
        print(f"  (no se pudo publicar el transito: {e})")
        return None


def publicar_ventas_historicas() -> dict | None:
    """Sube a la plataforma los MESES DE VENTA que le faltan.

    Esta tabla la usa la plataforma para la columna "Venta 12m", el grafico de
    consumo del requerimiento y la pantalla de Ventas historicas. Hasta ahora se
    cargaba con un job manual conectado directo a la base: el mes que se pegaba en
    el respaldo de Ventas no llegaba nunca, y esas vistas se quedaban atras sin
    avisar a nadie. Paso con julio-2026.

    Se publica SOLO lo que falta: se le pregunta a la plataforma hasta que periodo
    tiene y se suben los posteriores. En un dia normal no sube nada; cuando se
    pega un mes nuevo, sube ese mes.

    La sucursal va NORMALIZADA ("08 TALCA" -> "TALCA"), igual que hace el motor
    para sus propios calculos. El job manual copiaba la celda cruda, y por eso la
    tabla quedo con el mismo lugar bajo dos nombres.
    """
    import re

    import httpx
    import polars as pl

    base, email, password = _credenciales()
    if not email or not password:
        return None

    archivos = _archivos_de_ventas(_fin_mes_cerrado(date.today()))
    if not archivos:
        return None

    try:
        with httpx.Client(timeout=600) as c:
            r = c.post(f"{base}/api/auth/login", json={"email": email, "password": password})
            r.raise_for_status()
            token = r.json()["token"]
            cab = {"Authorization": f"Bearer {token}"}

            r = c.get(f"{base}/api/ventas-historicas/meta", headers=cab)
            r.raise_for_status()
            ultimo = r.json().get("periodo_max") or "000000"

            filas: list[dict] = []
            for ruta in archivos:
                df = pl.read_excel(
                    ruta, columns=["Periodo", "Producto", "SUCURSAL", "Cantidad", "Total Neta"]
                )
                df = (
                    df.with_columns(
                        pl.col("Periodo").cast(pl.Utf8).str.strip_chars(),
                        pl.col("SUCURSAL").cast(pl.Utf8)
                        .str.strip_chars()
                        .str.replace(r"^\d{1,2}\s+", ""),
                        pl.col("Producto").cast(pl.Utf8).str.strip_chars(),
                    )
                    .filter(pl.col("Periodo") > pl.lit(ultimo))
                    .group_by(["Periodo", "Producto", "SUCURSAL"])
                    .agg(
                        pl.col("Cantidad").sum().alias("cantidad"),
                        pl.col("Total Neta").sum().alias("neto"),
                        pl.len().alias("n_lineas"),
                    )
                )
                for p, prod, suc, cant, neto, n in df.iter_rows():
                    filas.append({
                        "periodo": p, "producto": prod, "sucursal": suc,
                        "cantidad": cant, "neto": neto, "n_lineas": n,
                    })

            if not filas:
                return {"filas_cargadas": 0, "periodos": [], "al_dia": True}

            # Un request POR MES, y no lotes de tamano fijo: el endpoint BORRA el
            # periodo antes de insertar, asi que partir un mes en dos requests
            # haria que el segundo se llevara por delante lo que subio el primero.
            # Un mes son ~15.000 filas agregadas: entra sin problema en una sola.
            por_mes: dict[str, list[dict]] = {}
            for f in filas:
                por_mes.setdefault(f["periodo"], []).append(f)

            cargadas, periodos = 0, []
            for periodo in sorted(por_mes):
                r = c.post(
                    f"{base}/api/admin/ventas-historicas",
                    headers=cab, json={"filas": por_mes[periodo]},
                )
                r.raise_for_status()
                d = r.json()
                cargadas += d.get("filas_cargadas", 0)
                periodos.extend(d.get("periodos", []))
            return {"filas_cargadas": cargadas, "periodos": periodos, "al_dia": False}
    except Exception as e:  # noqa: BLE001 - publicar las ventas nunca debe romper la carga
        print(f"  (no se pudieron publicar las ventas: {e})")
        return None


def publicar_stock_unificado() -> dict | None:
    """Sube a la plataforma el stock por bodega (reemplaza la foto vigente)."""
    import csv

    import httpx

    if not SALIDA_STOCK.exists():
        return None
    base, email, password = _credenciales()
    if not email or not password:
        return None
    with open(SALIDA_STOCK, encoding="utf-8", newline="") as f:
        filas = [
            {
                "producto": r["producto"],
                "bodega": r["bodega"] or None,
                "sucursal_id": r["sucursal_id"] or None,
                "stock": float(r["stock"]),
                "origen": r["origen"] or None,
            }
            for r in csv.DictReader(f)
            if r.get("producto")
        ]
    try:
        with httpx.Client(timeout=300) as c:
            r = c.post(f"{base}/api/auth/login", json={"email": email, "password": password})
            r.raise_for_status()
            token = r.json()["token"]
            r = c.post(
                f"{base}/api/admin/stock-unificado",
                headers={"Authorization": f"Bearer {token}"},
                json={"filas": filas},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:  # noqa: BLE001 - publicar el stock nunca debe romper la carga
        print(f"  (no se pudo publicar el stock: {e})")
        return None


def publicar_reemplazos(fuentes: dict) -> dict | None:
    """Sube la cadena de reemplazo de FORD para los codigos que Curifor tiene.

    La AGRUPACION (sumar el stock del viejo con el del nuevo) ya la hizo el motor
    al armar el mapeo. Esto es lo otro: avisarle al comprador que el codigo que le
    pidieron esta descontinuado y cual es el vigente, incluso cuando ese par no se
    agrupo. Por eso viaja `agrupado`, que distingue los dos casos.

    Se publica solo lo que toca al maestro de Curifor: de los 39.622 codigos de la
    lista, el resto no se puede mostrar en ninguna pantalla.
    """
    import httpx

    reem = fuentes.get("reemplazos_ford")
    mapeo = fuentes.get("mapeo")
    dim = fuentes.get("dim_producto")
    if reem is None or reem.is_empty() or dim is None:
        return None
    base, email, password = _credenciales()
    if not email or not password:
        return None

    from ..motor.lectores_excel import clave_precio

    por_clave: dict[str, str] = {}
    for (p,) in dim.select("Producto").unique().iter_rows():
        k = clave_precio(p)
        if k and k not in por_clave:
            por_clave[k] = p
    # Producto -> master, para saber si el par quedo efectivamente en un grupo.
    grupo = (
        dict(mapeo.select(["Producto", "Producto_Master"]).iter_rows())
        if mapeo is not None
        else {}
    )

    filas = []
    for f in reem.iter_rows(named=True):
        yo = por_clave.get(f["clave_precio"])
        if not yo:
            continue
        vigente = por_clave.get(f["clave_vigente"]) if f["clave_vigente"] else None
        viejos = [por_clave[k] for k in (f["reemplaza_a"] or []) if k in por_clave]
        viejos = [v for v in viejos if v != yo]
        if not vigente and not f["sku_vigente"] and not viejos:
            continue
        # Agrupado = el motor los dejo bajo el mismo master. Se mira contra el
        # vigente si lo hay, y si no contra el primero de los que esta pieza
        # reemplazo: en las dos direcciones el grupo es el mismo.
        otro = vigente or (viejos[0] if viejos else None)
        agrupado = bool(
            otro and yo in grupo and otro in grupo and grupo[yo] == grupo[otro]
        )
        filas.append({
            "producto": yo,
            "reemplazado_por": vigente,
            "reemplazado_por_ford": f["sku_vigente"],
            "cadena": f["cadena"],
            "reemplaza_a": viejos,
            "sucesor_confirmado": bool(f["sucesor_confirmado"]),
            "agrupado": agrupado,
            "aviso": f["aviso"],
        })
    if not filas:
        return None

    try:
        with httpx.Client(timeout=300) as c:
            r = c.post(f"{base}/api/auth/login", json={"email": email, "password": password})
            r.raise_for_status()
            token = r.json()["token"]
            r = c.post(
                f"{base}/api/admin/reemplazos-ford",
                headers={"Authorization": f"Bearer {token}"},
                json={"filas": filas},
            )
            r.raise_for_status()
            out = r.json()
            out["agrupados"] = sum(1 for f in filas if f["agrupado"])
            return out
    except Exception as e:  # noqa: BLE001 - publicar esto nunca debe romper la carga
        print(f"  (no se pudieron publicar los reemplazos: {e})")
        return None


def publicar_sku_proveedor(fuentes: dict) -> dict | None:
    """Sube la equivalencia codigo de Curifor -> SKU del portal del proveedor.

    Ford pide su codigo con barras ("SZ6Z/3B437/B/"), que separa prefijo, basico y
    sufijos y NO se deriva con una regla: hay que mirarlo en su lista. Antes el
    comprador hacia esa conversion con un BUSCARV contra una tabla de 111.773
    filas pegada en su Excel; ahora la plataforma arma el archivo del portal sola.

    Se publica la lista completa (no solo lo que el sugerido pide) porque un
    requerimiento de sucursal puede traer cualquier codigo.
    """
    import httpx

    lista = fuentes.get("precios_ford")
    if lista is None or lista.is_empty():
        return None
    base, email, password = _credenciales()
    if not email or not password:
        return None
    # `clave_precio` ya dejo la clave normalizada al leer la lista; el SKU es el
    # PartNumber original, que no se conserva. Se relee para tener los dos.
    from ..motor import lectores_excel as lx

    ruta = _buscar("precios_ford", obligatorio=False)
    if ruta is None:
        return None
    import polars as pl

    df = pl.read_excel(ruta, sheet_name="Precios").select("PartNumber").unique()
    filas = []
    for (sku,) in df.iter_rows():
        clave = lx.clave_precio(sku)
        if clave and sku:
            filas.append({"clave": clave, "sku": str(sku).strip()})
    if not filas:
        return None
    try:
        with httpx.Client(timeout=300) as c:
            r = c.post(f"{base}/api/auth/login", json={"email": email, "password": password})
            r.raise_for_status()
            token = r.json()["token"]
            r = c.post(
                f"{base}/api/requerimiento/sku-proveedor",
                headers={"Authorization": f"Bearer {token}"},
                json={"proveedor": "FORD", "filas": filas},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:  # noqa: BLE001 - nunca debe romper la carga del sugerido
        print(f"  (no se pudo publicar la equivalencia de SKU: {e})")
        return None


def _guardar_lead_time(fuentes: dict) -> Path | None:
    """Escribe el lead time por proveedor (global) y por proveedor x sucursal."""
    import polars as pl

    from ..motor.lead_time_proveedor import (
        calcular_lead_time_proveedor,
        calcular_lead_time_proveedor_sucursal,
    )

    seg = fuentes.get("seguimiento_lt")
    if seg is None:
        return None
    glob = calcular_lead_time_proveedor(seg).select(
        pl.col("Razon Social Proveedor").alias("proveedor"),
        pl.lit(None, dtype=pl.Utf8).alias("sucursal_id"),
        pl.col("Lead Time Dias").alias("lead_time_dias"),
        pl.lit(None, dtype=pl.Int64).alias("n_muestras"),
    )
    suc = calcular_lead_time_proveedor_sucursal(seg).select(
        pl.col("Razon Social Proveedor").alias("proveedor"),
        pl.col("SucursalID").alias("sucursal_id"),
        pl.col("Lead Time Dias").alias("lead_time_dias"),
        pl.col("N Muestras").cast(pl.Int64).alias("n_muestras"),
    )
    pl.concat([glob, suc]).write_csv(SALIDA_LT)
    return SALIDA_LT


def publicar_lead_time() -> dict | None:
    """Sube a la plataforma el lead time calculado (reemplaza la foto vigente)."""
    import csv

    import httpx

    if not SALIDA_LT.exists():
        return None
    base, email, password = _credenciales()
    if not email or not password:
        return None
    with open(SALIDA_LT, encoding="utf-8", newline="") as f:
        filas = [
            {
                "proveedor": r["proveedor"],
                "sucursal_id": r["sucursal_id"] or None,
                "lead_time_dias": float(r["lead_time_dias"]),
                "n_muestras": int(r["n_muestras"]) if r["n_muestras"] else None,
            }
            for r in csv.DictReader(f)
            if r.get("proveedor") and r.get("lead_time_dias")
        ]
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(f"{base}/api/auth/login", json={"email": email, "password": password})
            r.raise_for_status()
            token = r.json()["token"]
            r = c.post(
                f"{base}/api/admin/lead-time-proveedor",
                headers={"Authorization": f"Bearer {token}"},
                json={"filas": filas},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:  # noqa: BLE001 - publicar el LT nunca debe romper la carga
        print(f"  (no se pudo publicar el lead time: {e})")
        return None


def avisar_falla(motivo: str, detalle: str = "") -> bool:
    """Deja una incidencia en la plataforma cuando la corrida diaria falla.

    Hasta ago-2026 un fallo solo escribia "RESULTADO: FALLO" en un log local que
    no lee nadie. La carga estuvo rota del 31-jul al 03-ago (la plataforma
    devolvia un 500) y el equipo siguio comprando sobre el sugerido del 30-jul
    sin enterarse. La incidencia ademas dispara la campanita de los admin.

    Devuelve True si el aviso se pudo dejar. Nunca lanza: si la plataforma esta
    caida no hay nada que hacer, y este aviso jamas debe tapar el error original.
    """
    import httpx

    base, email, password = _credenciales()
    if not email or not password:
        return False
    hoy = date.today()
    try:
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{base}/api/auth/login", json={"email": email, "password": password})
            r.raise_for_status()
            token = r.json()["token"]
            r = c.post(
                f"{base}/api/incidencias",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "titulo": f"La actualizacion del sugerido fallo ({hoy:%d-%m-%Y})",
                    "descripcion": (
                        f"{motivo}\n\n{detalle}\n\n"
                        "El sugerido NO se actualizo: sigue mostrando la carga anterior. "
                        "Mientras no se corrija, lo que se compre sale de datos viejos."
                    ).strip(),
                    "pantalla": "cargar",
                },
            )
            r.raise_for_status()
            return True
    except Exception as e:  # noqa: BLE001 - avisar nunca puede romper mas de lo que ya esta roto
        print(f"  (ademas, no se pudo dejar la incidencia del fallo: {e})")
        return False


def enviar(csv_path: Path, oficial: bool = False) -> dict:
    """Sube el CSV a la plataforma: comparacion (sombra) o carga (oficial)."""
    import httpx

    # Las credenciales vienen del entorno o del .env del repo (donde las deja el
    # script de 1 clic). Sin esto el job solo servia lanzado desde ese script.
    base, email, password = _credenciales()
    if not email or not password:
        raise RuntimeError(
            "Faltan credenciales: define PLATAFORMA_EMAIL y PLATAFORMA_PASSWORD "
            "en el entorno (nunca en el repo)."
        )

    with httpx.Client(timeout=300) as c:
        r = c.post(f"{base}/api/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        token = r.json()["token"]
        ruta = "/api/admin/cargar-sugerido" if oficial else "/api/admin/motor/comparar"
        with open(csv_path, "rb") as f:
            r = c.post(
                f"{base}{ruta}",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (csv_path.name, f, "text/csv")},
            )
        r.raise_for_status()
        return r.json()


# Cuántos días puede tener un archivo antes de que su dato deje de servir. El
# stock y el seguimiento cambian todos los días; los respaldos de venta son
# mensuales y el maestro/mix cambian pocas veces al año.
FRESCURA_DIAS = {
    "stock_bodegas": 2,
    "stock_bodegas_frontera": 2,
    "seguimiento_curifor_nacional": 2,
    "seguimiento_curifor_importado": 7,
    "seguimiento_frontera": 7,
    "ventas_frontera": 35,
    "catalogo": 120,
    "mix_reemplazos": 120,
}


def revisar_frescura(hoy: date | None = None) -> list[str]:
    """Archivos que llevan demasiado sin actualizarse.

    Sin esto, olvidar una exportación no da ningún error: el motor calcula igual y
    publica un sugerido con el stock de la semana pasada. Nadie se entera hasta que
    alguien compra de más."""
    from ..motor import fuentes

    hoy = hoy or date.today()
    viejos = []
    for fuente, dias in FRESCURA_DIAS.items():
        try:
            ruta = fuentes.ruta_de(fuente)
        except FileNotFoundError:
            continue
        edad = (hoy - date.fromtimestamp(ruta.stat().st_mtime)).days
        if edad > dias:
            viejos.append(f"{ruta.name}: {edad} dias (se espera al dia cada {dias})")
    return viejos


def run(oficial: bool = False, ignorar_frescura: bool = False) -> int:
    print(f"Crudos: {CRUDOS_DIR}")

    viejos = revisar_frescura()
    for v in viejos:
        print(f"  DESACTUALIZADO: {v}")
    # Solo la corrida oficial avisa: el modo sombra es una prueba y ensuciaria
    # las incidencias del equipo.
    def _fallar(motivo: str, detalle: str = "") -> int:
        print(f"ERROR: {motivo}\n{detalle}".rstrip(), file=sys.stderr)
        if oficial and avisar_falla(motivo, detalle):
            print("  incidencia dejada en la plataforma (los admin ven la campanita).")
        return 1

    if viejos and oficial and not ignorar_frescura:
        return _fallar(
            "No se carga a produccion con archivos desactualizados.",
            "Archivos vencidos:\n  - " + "\n  - ".join(viejos)
            + "\n\nActualizalos en la carpeta de datos, o corre con "
            "--ignorar-frescura si sabes que asi corresponde.",
        )

    try:
        csv_path = construir_csv()
    except Exception as e:  # noqa: BLE001
        return _fallar("El motor no pudo calcular el sugerido.", f"{type(e).__name__}: {e}")
    print(f"CSV generado: {csv_path}")

    try:
        resultado = enviar(csv_path, oficial=oficial)
    except Exception as e:  # noqa: BLE001
        return _fallar(
            "El motor calculo bien, pero la plataforma rechazo la carga.",
            f"{type(e).__name__}: {e}",
        )

    if oficial:
        print(f"CARGA OFICIAL: {resultado.get('filas_cargadas')} filas.")
        for a in resultado.get("advertencias", []):
            print(f"  advertencia: {a}")
        # El detalle del lead time calculado, para verlo en Calibracion.
        lt = publicar_lead_time()
        if lt:
            print(f"  lead time publicado: {lt.get('filas_cargadas')} filas.")
        # El stock por bodega, para la ficha del catalogo.
        stk = publicar_stock_unificado()
        if stk:
            print(f"  stock publicado: {stk.get('filas_cargadas')} filas.")
        # El transito de todo el catalogo, para que el comprador no compre de nuevo
        # algo que ya viene en camino aunque no este en el sugerido.
        tra = publicar_transito()
        if tra:
            print(f"  transito publicado: {tra.get('filas_cargadas')} filas.")
        # Los meses de venta que la plataforma no tenga. Normalmente ninguno; al
        # pegar un mes nuevo en el respaldo, ese mes.
        vta = publicar_ventas_historicas()
        if vta and vta.get("al_dia"):
            print("  ventas: la plataforma ya esta al dia.")
        elif vta:
            print(f"  ventas publicadas: {vta.get('filas_cargadas')} filas "
                  f"(periodos {', '.join(vta.get('periodos') or [])}).")
        # Equivalencia codigo Curifor -> SKU del portal, para armar el archivo de
        # carga masiva sin que el comprador convierta codigos a mano.
        sku = publicar_sku_proveedor(globals().get("_ULTIMAS_FUENTES") or {})
        if sku:
            print(f"  equivalencias de SKU publicadas: {sku.get('filas_cargadas')} ({sku.get('proveedor')}).")
        # Que codigo esta descontinuado y cual lo reemplaza, para que el comprador
        # no compre uno muerto. La agrupacion ya ocurrio arriba, al armar el mapeo.
        rep = publicar_reemplazos(globals().get("_ULTIMAS_FUENTES") or {})
        if rep:
            print(f"  reemplazos FORD publicados: {rep.get('filas_cargadas')} filas "
                  f"({rep.get('agrupados')} agrupan stock, el resto solo avisa).")
    else:
        print(
            f"SOMBRA: paridad {resultado['paridad_pct']}% "
            f"({resultado['filas_comunes']} filas comunes, "
            f"{resultado['filas_solo_motor']} solo motor, "
            f"{resultado['filas_solo_bi']} solo BI)."
        )
        peores = [
            f"{e['producto']}/{e['sucursal_id']}" for e in resultado.get("ejemplos", [])[:5]
        ]
        if peores:
            print(f"  mayores divergencias: {', '.join(peores)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Corre el motor con los crudos reales.")
    ap.add_argument(
        "--oficial",
        action="store_true",
        help="Carga el resultado como sugerido oficial (por defecto solo compara).",
    )
    ap.add_argument(
        "--ignorar-frescura",
        action="store_true",
        help="Carga aunque haya archivos desactualizados (solo si sabes por que).",
    )
    args = ap.parse_args()
    raise SystemExit(run(oficial=args.oficial, ignorar_frescura=args.ignorar_frescura))
