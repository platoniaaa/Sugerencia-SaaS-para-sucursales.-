"""Tests de smoke: al menos 1 por endpoint del API."""
import io

from openpyxl import Workbook


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_ok(client):
    r = client.post("/api/auth/login", json={"email": "test@curifor.com", "password": "123456"})
    assert r.status_code == 200
    assert r.json()["token"]
    assert r.json()["email"] == "test@curifor.com"


def test_login_password_incorrecta(client):
    r = client.post("/api/auth/login", json={"email": "test@curifor.com", "password": "mala"})
    assert r.status_code == 401


def test_login_usuario_inexistente(client):
    r = client.post("/api/auth/login", json={"email": "noexiste@curifor.com", "password": "123456"})
    assert r.status_code == 401


def test_login_registra_acceso_fuera_de_auditoria(client):
    r = client.post("/api/auth/login", json={"email": "test@curifor.com", "password": "123456"})
    assert r.status_code == 200
    # El acceso NO debe aparecer en la auditoria general (va en su vista restringida).
    aud = client.get("/api/auditoria").json()
    assert all(it["accion"] != "login" for it in aud["items"])


def test_accesos_requiere_autorizacion(client):
    # noadmin@curifor.com no es admin ni esta en la lista de emails autorizados -> 403.
    # (test@curifor.com ahora es admin en el seed, asi que se usa el otro usuario.)
    from src.main import app
    from src.services.auth import requiere_auth

    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        assert client.get("/api/auditoria/accesos").status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_accesos_lista_logins_para_autorizado(client, monkeypatch):
    from src.services import auth as auth_svc

    monkeypatch.setattr(auth_svc.settings, "emails_ver_accesos", "test@curifor.com")
    client.post("/api/auth/login", json={"email": "test@curifor.com", "password": "123456"})
    r = client.get("/api/auditoria/accesos")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and items[0]["accion"] == "login"
    assert items[0]["usuario_email"] == "test@curifor.com"


def test_auth_token_roundtrip():
    from src.services.auth import crear_token, verificar_token

    t = crear_token("alguien@curifor.com")
    assert verificar_token(t) == "alguien@curifor.com"
    assert verificar_token("token.invalido") is None


def test_endpoint_protegido_sin_token():
    # Sin el override de auth, un endpoint de datos debe responder 401.
    from fastapi.testclient import TestClient
    from src.main import app

    with TestClient(app) as c:
        assert c.get("/api/sucursales").status_code == 401


def test_excluye_productos_dp(client, db_session):
    from src.models import Sugerido

    db_session.add(Sugerido(
        tenant_id="curifor", producto="D&P REPTO-TALLER(R)", sucursal_id="LINDEROS",
        nombre_sucursal="Linderos", pedir="Si", total_sugerido_suc=5,
    ))
    db_session.commit()
    body = client.get("/api/sugerido").json()
    productos = [i["producto"] for i in body["items"]]
    assert "D&P REPTO-TALLER(R)" not in productos
    assert "20 BXO5W30AA" in productos
    assert body["total"] == 1


def test_listar_sugerido(client):
    r = client.get("/api/sugerido")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["producto"] == "20 BXO5W30AA"


def test_sugerido_filtro_abc(client):
    assert client.get("/api/sugerido", params={"abc": "A"}).json()["total"] == 1
    assert client.get("/api/sugerido", params={"abc": "C"}).json()["total"] == 0


def test_kpis(client):
    r = client.get("/api/sugerido/kpis")
    assert r.status_code == 200
    body = r.json()
    assert body["total_sugerido"] == 10
    assert body["valor_total_clp"] == 50000
    assert body["n_productos"] == 1


def test_agrupado_por_sucursal(client):
    r = client.get("/api/sugerido/agrupado", params={"por": "sucursal"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["grupo"] == "Linderos"
    assert body[0]["total_sugerido"] == 10
    assert body[0]["valor_clp"] == 50000


def test_agrupado_dimension_invalida(client):
    assert client.get("/api/sugerido/agrupado", params={"por": "xyz"}).status_code == 400


def test_detalle_sugerido(client):
    r = client.get("/api/sugerido/20 BXO5W30AA/LINDEROS")
    assert r.status_code == 200
    assert r.json()["clasificacion_abc"] == "A"


def test_detalle_sugerido_404(client):
    assert client.get("/api/sugerido/NOEXISTE/LINDEROS").status_code == 404


def test_ventas_12m(client):
    r = client.get("/api/sugerido/20 BXO5W30AA/LINDEROS/ventas")
    assert r.status_code == 200
    body = r.json()
    assert body["producto"] == "20 BXO5W30AA"
    # Dos series: general (todas las sucursales) y la sucursal especifica.
    assert len(body["meses_general"]) == 3
    assert len(body["meses_sucursal"]) == 3
    assert body["meses_general"][0]["mes"] == "202503"
    # En el seed solo hay datos para LINDEROS, asi que ambas series suman lo mismo.
    assert body["total_general"] == 35
    assert body["total_sucursal"] == 35


def test_ventas_12m_sin_datos(client):
    r = client.get("/api/sugerido/NOEXISTE/LINDEROS/ventas")
    assert r.status_code == 200
    body = r.json()
    assert body["meses_general"] == []
    assert body["meses_sucursal"] == []


def test_export_excel(client):
    r = client.post("/api/sugerido/export-excel", json={"filtros": {"solo_pedir": True}})
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 0


def test_listar_productos(client):
    r = client.get("/api/productos")
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_detalle_producto(client):
    r = client.get("/api/productos/20 BXO5W30AA")
    assert r.status_code == 200
    assert r.json()["filtro1_final"] == "FORD"


def test_listar_sucursales(client):
    r = client.get("/api/sucursales")
    assert r.status_code == 200
    assert r.json()[0]["sucursal_id"] == "LINDEROS"


def test_crud_sugerencia_manual(client):
    # crear
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS", "unidades": 5, "motivo": "promo",
    })
    assert r.status_code == 201
    sid = r.json()["id"]

    # listar
    r = client.get("/api/sugerencias-manuales", params={"producto": "20 BXO5W30AA"})
    assert r.status_code == 200
    assert len(r.json()) == 1

    # patch (aprobar)
    r = client.patch(f"/api/sugerencias-manuales/{sid}", json={"aprobado": True})
    assert r.status_code == 200
    assert r.json()["aprobado"] is True

    # delete
    assert client.delete(f"/api/sugerencias-manuales/{sid}").status_code == 204
    assert len(client.get("/api/sugerencias-manuales").json()) == 0


def test_crear_sugerencia_masiva(client):
    # Aplica 3 unidades a todos los productos que cumplen el filtro (aqui: 1 fila).
    r = client.post(
        "/api/sugerencias-manuales/masiva",
        json={"filtros": {"solo_pedir": True}, "unidades": 3, "motivo": "carga masiva"},
    )
    assert r.status_code == 201
    assert r.json()["creadas"] == 1
    # Se creo y es consultable.
    assert len(client.get("/api/sugerencias-manuales").json()) == 1


def test_carros_compra(client):
    r = client.get("/api/compras/carros")
    assert r.status_code == 200
    body = r.json()
    assert body["total_proveedores"] == 1
    carro = body["carros"][0]
    assert carro["proveedor"] == "Ford Motor Company Chile"
    # cantidad = sugerido_compra_neto del seed (6)
    assert carro["lineas"][0]["cantidad"] == 6
    assert carro["lineas"][0]["producto"] == "20 BXO5W30AA"


def test_carro_incluye_manual_vigente(client):
    # Sin manual: la cantidad del carro es 6 (sugerido_compra_neto del seed).
    assert client.get("/api/compras/carros").json()["carros"][0]["lineas"][0]["cantidad"] == 6
    # Al agregar una sugerencia manual de +5, el carro pasa a 11.
    client.post(
        "/api/sugerencias-manuales",
        json={"producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS", "unidades": 5},
    )
    body = client.get("/api/compras/carros").json()
    assert body["carros"][0]["lineas"][0]["cantidad"] == 11


def test_manual_con_fecha_limite_vence_y_se_archiva(client, db_session):
    from datetime import date, datetime, timedelta, timezone

    from src.models import SugerenciaManual
    from src.services import recurrentes_service
    from sqlalchemy import select

    # Manual con fecha límite futura: mientras esté vigente suma al carro (6 -> 11).
    sid = client.post(
        "/api/sugerencias-manuales",
        json={"producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS",
              "unidades": 5, "expira_en": (date.today() + timedelta(days=7)).isoformat()},
    ).json()["id"]
    assert client.get("/api/compras/carros").json()["carros"][0]["lineas"][0]["cantidad"] == 11

    # Forzar que ya venció: deja de sumar al instante, aunque aún no esté archivada.
    s = db_session.get(SugerenciaManual, sid)
    s.expira_en = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    assert client.get("/api/compras/carros").json()["carros"][0]["lineas"][0]["cantidad"] == 6

    # El cron la archiva (limpieza); sale del listado vigente pero queda en historial.
    assert recurrentes_service.archivar_expiradas(db_session) == 1
    assert len(client.get("/api/sugerencias-manuales").json()) == 0
    archivadas = db_session.scalars(
        select(SugerenciaManual).where(SugerenciaManual.archivada.is_(True))
    ).all()
    assert len(archivadas) == 1


def test_recurrente_crea_aplica_y_suma_al_carro(client):
    r = client.post(
        "/api/sugerencias-manuales/recurrentes",
        json={"modo": "individual", "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS",
              "unidades": 5, "cada_dias": 7},
    )
    assert r.status_code == 201
    # Aparece en la lista de recurrentes activas.
    assert len(client.get("/api/sugerencias-manuales/recurrentes").json()) == 1
    # Aplicó de inmediato: el carro pasa de 6 a 11.
    assert client.get("/api/compras/carros").json()["carros"][0]["lineas"][0]["cantidad"] == 11


def test_recurrente_eliminar_archiva_su_aporte(client):
    rid = client.post(
        "/api/sugerencias-manuales/recurrentes",
        json={"modo": "individual", "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS",
              "unidades": 5, "cada_dias": 7},
    ).json()["id"]
    assert client.delete(f"/api/sugerencias-manuales/recurrentes/{rid}").status_code == 204
    assert client.get("/api/sugerencias-manuales/recurrentes").json() == []
    # Su aporte fue archivado: el carro vuelve a 6.
    assert client.get("/api/compras/carros").json()["carros"][0]["lineas"][0]["cantidad"] == 6


def test_recurrente_procesar_reemplaza_instancia(client, db_session):
    from datetime import date

    from src.models import SugerenciaManual, SugerenciaRecurrente
    from src.schemas import RecurrenteCreate
    from src.services import recurrentes_service
    from sqlalchemy import select

    rec = recurrentes_service.crear(
        db_session,
        RecurrenteCreate(modo="individual", producto="20 BXO5W30AA",
                         sucursal_id="LINDEROS", unidades=5, cada_dias=7),
    )
    # Forzar que toque hoy y procesar.
    db_session.get(SugerenciaRecurrente, rec.id).proxima_ejecucion = date.today()
    db_session.commit()
    recurrentes_service.procesar(db_session, date.today())
    vigentes = db_session.scalars(
        select(SugerenciaManual).where(
            SugerenciaManual.recurrente_id == rec.id, SugerenciaManual.archivada.is_(False)
        )
    ).all()
    assert len(vigentes) == 1  # mantiene una sola vigente (no acumula)


def test_cron_requiere_secret(client):
    assert client.post("/api/cron/procesar-recurrentes").status_code == 403


def test_cron_con_secret_ok(client, monkeypatch):
    from src.routers import cron

    monkeypatch.setattr(cron.settings, "cron_secret", "s3cr3t")
    r = client.post("/api/cron/procesar-recurrentes", headers={"X-Cron-Secret": "s3cr3t"})
    assert r.status_code == 200
    assert "sugerencias_creadas" in r.json()


def test_carros_export_excel(client):
    r = client.post("/api/compras/export-excel", json={"filtros": {"solo_pedir": True}})
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 0


def test_post_venta_meta(client):
    r = client.get("/api/post-venta/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["filas"] == 3
    assert body["periodos"] == ["202601", "202602"]
    assert "LINDEROS" in body["sucursales"]
    assert body["columnas"] == ["Periodo", "SUCURSAL", "Producto", "Total"]


def test_post_venta_contar_filtrado(client):
    assert client.get("/api/post-venta/contar", params={"periodo_desde": "202601", "periodo_hasta": "202601"}).json()["filas"] == 2
    assert client.get("/api/post-venta/contar", params={"sucursal": "LINDEROS"}).json()["filas"] == 2
    assert client.get("/api/post-venta/contar", params={"periodo_desde": "202601", "periodo_hasta": "202601", "sucursal": "TALCA"}).json()["filas"] == 1


def test_post_venta_export_excel(client):
    r = client.post("/api/post-venta/export-excel", json={"sucursal": "LINDEROS"})
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 0


def test_post_venta_export_sin_filas_404(client):
    assert client.post("/api/post-venta/export-excel", json={"sucursal": "NOEXISTE"}).status_code == 404


def test_powerbi_transformar_columnas():
    # Las claves "Tabla[Columna]" / "'Tabla'[Columna]" / "[Medida]" se reducen a la columna.
    from src.services.powerbi_loader import transformar

    rows = [
        {
            "Sugerido por Sucursal[producto]": "20 BXO5W30AA",
            "'Sugerido por Sucursal'[sucursal_id]": "LINDEROS",
            "[total_sugerido_suc]": 10,
        }
    ]
    out = transformar(rows)
    assert out == [
        {"producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS", "total_sugerido_suc": 10}
    ]


def test_powerbi_estado_no_configurado(client):
    assert client.get("/api/admin/powerbi/estado").json() == {"configurado": False}


def test_cargar_desde_powerbi_no_configurado(client):
    # Sin credenciales POWERBI_*, el endpoint responde 503 (no 500).
    assert client.post("/api/admin/cargar-desde-powerbi").status_code == 503


def test_sync_desktop_carga(client, db_session, monkeypatch, tmp_path):
    # Mockea el script de PowerShell: genera un CSV como el que produce el script real
    # (cabeceras ya limpias) y devuelve su ruta.
    from src.services import powerbi_desktop_loader

    csv = tmp_path / "pbi.csv"
    csv.write_text(
        "Producto,SucursalID,Nombre Sucursal,total_sugerido_suc,Pedir\n"
        "PBI-1,LINDEROS VTA MOVIL,Linderos Vta Movil,8,Si\n",
        encoding="utf-8",
    )
    fake = {"ok": True, "port": 5000, "rows": 1, "csv": str(csv)}
    monkeypatch.setattr(
        powerbi_desktop_loader, "_ejecutar_script", lambda dax, timeout=600: fake
    )

    r = client.post("/api/admin/cargar-desde-powerbi-desktop")
    assert r.status_code == 200
    assert r.json()["filas_cargadas"] == 1
    assert client.get("/api/sugerido").json()["items"][0]["producto"] == "PBI-1"


def test_sync_desktop_error_msolap(client, monkeypatch):
    # Si el script reporta que falta MSOLAP, el endpoint responde 502 con guia.
    from src.services import powerbi_desktop_loader

    monkeypatch.setattr(
        powerbi_desktop_loader,
        "_ejecutar_script",
        lambda dax, timeout=600: {"ok": False, "error": "El proveedor 'MSOLAP' no esta registrado"},
    )
    r = client.post("/api/admin/cargar-desde-powerbi-desktop")
    assert r.status_code == 502
    assert "MSOLAP" in r.json()["detail"]


def test_cargar_sugerido_excel(client):
    wb = Workbook()
    ws = wb.active
    ws.append(["producto", "sucursal_id", "nombre_sucursal", "clasificacion_abc",
               "total_sugerido_suc", "total_valor_sugerido_clp", "pedir"])
    ws.append(["NUEVO-1", "RANCAGUA", "Rancagua", "B", 7, 14000, "Si"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    r = client.post(
        "/api/admin/cargar-sugerido",
        files={"file": ("sugerido.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    assert r.json()["filas_cargadas"] == 1

    # La carga reemplaza la tabla: ahora solo existe el producto nuevo.
    r = client.get("/api/sugerido", params={"solo_pedir": True})
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["producto"] == "NUEVO-1"


def test_listar_por_ids_suma_manuales_y_enriquece_catalogo(db_session):
    """El export por IDs debe devolver lo mismo que la grilla: suma de
    sugerencias manuales vigentes y campo `reemplazos` del catalogo."""
    from src.models import ProductoCatalogo, Sugerido, SugerenciaManual
    from src.services.sugerido_service import listar_por_ids

    # Catalogo con reemplazo declarado para el producto del seed.
    db_session.add(ProductoCatalogo(
        producto="20 BXO5W30AA", tenant_id="curifor",
        glosa="ACEITE 5W30 LITRO FORD", costo=5000.0,
        reemplazo="20 BXO5W30BB",
    ))
    # Sugerencia manual vigente: +15 unidades sobre la fila del seed (10 unidades).
    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto="20 BXO5W30AA", sucursal_id="LINDEROS",
        unidades=15, motivo="prueba", creado_por="test@curifor.com",
    ))
    db_session.commit()

    sugerido_id = db_session.query(Sugerido).first().id
    items = listar_por_ids(db_session, [sugerido_id])

    assert len(items) == 1
    item = items[0]
    # 10 (BI) + 15 (manual) = 25
    assert item["total_sugerido_suc"] == 25
    # sugerido_compra_neto = 6 (BI) + 15 (manual) = 21
    assert item["sugerido_compra_neto"] == 21
    # valor = 50000 (BI) + 15 * 5000 = 125000
    assert item["total_valor_sugerido_clp"] == 125000
    assert item["pedir"] == "Si"
    # Enriquecido desde el catalogo.
    assert item["reemplazos"] == "20 BXO5W30BB"


def test_excel_labels_cubren_columnas_del_frontend():
    """Toda columna del frontend (apps/web/lib/columnas.ts) debe tener etiqueta
    en excel_export.LABELS. Si no, el export descarta esa columna silenciosamente.
    Este test es un fusible para que no vuelva a pasar."""
    import re
    from pathlib import Path

    from src.services.excel_export import LABELS

    columnas_ts = Path(__file__).resolve().parents[2] / "web" / "lib" / "columnas.ts"
    if not columnas_ts.exists():
        # Si los tests se corren sin el repo del frontend al lado, no fallar.
        return
    keys_web = set(re.findall(r'key:\s*"(\w+)"', columnas_ts.read_text(encoding="utf-8")))
    faltan = sorted(keys_web - set(LABELS))
    assert not faltan, (
        f"Columnas del frontend sin etiqueta en LABELS del Excel: {faltan}. "
        f"Agregalas a apps/api/src/services/excel_export.py."
    )


def test_regla_stock_sin_venta_marca_pedir_no(db_session):
    """Regla: si stock_activo >= demanda_mensual y no hubo venta el mes anterior,
    la plataforma fuerza pedir='No' aunque el BI haya sugerido comprar."""
    from src.models import Sugerido, VentaMensual
    from src.services.sugerido_service import (
        _aplicar_regla_stock_sin_venta,
        _mes_anterior_yyyymm,
    )

    # La fila del seed tiene venta en 202503-04-05; vamos a usar otro producto/sucursal
    # para evitar pisar el helper con las ventas existentes.
    db_session.add(Sugerido(
        tenant_id="curifor", producto="TEST-REGLA-1", descripcion="Test",
        sucursal_id="LINDEROS", nombre_sucursal="Linderos",
        clasificacion_abc="B", pedir="Si", pedir_flag="Si",
        demanda_mensual=10.0, stock_activo_suc=50, total_sugerido_suc=5,
    ))
    db_session.add(Sugerido(
        tenant_id="curifor", producto="TEST-REGLA-2", descripcion="Test 2",
        sucursal_id="LINDEROS", nombre_sucursal="Linderos",
        clasificacion_abc="B", pedir="Si", pedir_flag="Si",
        demanda_mensual=10.0, stock_activo_suc=50, total_sugerido_suc=5,
    ))
    # TEST-REGLA-2 SI tuvo venta el mes anterior -> NO se debe aplicar la regla.
    db_session.add(VentaMensual(
        tenant_id="curifor", producto="TEST-REGLA-2", sucursal_id="LINDEROS",
        mes=_mes_anterior_yyyymm(), cantidad=3,
    ))
    db_session.commit()

    items = [
        # Cumple ambas condiciones: stock 50 >= demanda 10, sin venta mes anterior.
        {
            "producto": "TEST-REGLA-1", "sucursal_id": "LINDEROS",
            "stock_activo_suc": 50, "demanda_mensual": 10.0,
            "pedir": "Si", "pedir_flag": "Si",
        },
        # Tiene venta mes anterior -> NO debe cambiar.
        {
            "producto": "TEST-REGLA-2", "sucursal_id": "LINDEROS",
            "stock_activo_suc": 50, "demanda_mensual": 10.0,
            "pedir": "Si", "pedir_flag": "Si",
        },
        # Stock insuficiente -> NO debe cambiar.
        {
            "producto": "TEST-REGLA-1", "sucursal_id": "TALCA",
            "stock_activo_suc": 5, "demanda_mensual": 10.0,
            "pedir": "Si", "pedir_flag": "Si",
        },
    ]
    _aplicar_regla_stock_sin_venta(items, db_session)

    assert items[0]["pedir"] == "No", "stock cubre + sin venta -> debe forzar pedir=No"
    assert items[0]["pedir_flag"] == "No"
    assert items[1]["pedir"] == "Si", "con venta mes anterior, no aplicar la regla"
    assert items[2]["pedir"] == "Si", "stock insuficiente, no aplicar la regla"


MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_sugerido(filas):
    """Arma un xlsx en memoria con cabeceras tipo BI y las filas dadas (listas)."""
    wb = Workbook()
    ws = wb.active
    ws.append(filas[0])
    for fila in filas[1:]:
        ws.append(fila)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_stock_por_bodega_y_trasladar_desde_fluyen(client):
    """Las columnas de stock por bodega y 'trasladar_desde' del BI llegan a la API
    (y con eso a la grilla y al export Excel) tras la carga."""
    buf = _xlsx_sugerido([
        ["producto", "sucursal_id", "pedir", "total_sugerido_suc",
         "Stock LINDEROS", "Stock TALCA (2)", "Stock CD REPUESTOS", "trasladar_desde"],
        ["STK-1", "CHILLAN", "Si", 5, 3, 2, 101,
         "3 unidades desde Linderos; 2 unidades desde Talca (2)"],
    ])
    r = client.post("/api/admin/cargar-sugerido", files={"file": ("s.xlsx", buf, MIME_XLSX)})
    assert r.status_code == 200

    item = client.get("/api/sugerido").json()["items"][0]
    assert item["stock_linderos"] == 3
    assert item["stock_talca_2"] == 2
    assert item["stock_cd_repuestos"] == 101
    assert item["trasladar_desde"].startswith("3 unidades desde Linderos")


def test_carga_abortada_si_snapshot_encoge_demasiado(client):
    """Guardrail: una carga con muchas menos filas que el snapshot vigente se
    aborta con 400 y el snapshot anterior queda intacto."""
    cabecera = ["producto", "sucursal_id", "pedir", "total_sugerido_suc"]
    diez = _xlsx_sugerido([cabecera] + [[f"P-{i}", "RANCAGUA", "Si", 1] for i in range(10)])
    r = client.post("/api/admin/cargar-sugerido", files={"file": ("a.xlsx", diez, MIME_XLSX)})
    assert r.status_code == 200
    assert r.json()["filas_cargadas"] == 10

    dos = _xlsx_sugerido([cabecera] + [[f"Q-{i}", "RANCAGUA", "Si", 1] for i in range(2)])
    r = client.post("/api/admin/cargar-sugerido", files={"file": ("b.xlsx", dos, MIME_XLSX)})
    assert r.status_code == 400
    assert "abortada" in r.json()["detail"].lower()
    # El snapshot anterior sigue vivo.
    assert client.get("/api/sugerido").json()["total"] == 10


def test_advertencia_por_sugerido_anomalo(client):
    """Un Total Sugerido gigante (unidad de medida corrupta, ej. mL) genera
    advertencia en la carga, sin bloquearla."""
    buf = _xlsx_sugerido([
        ["producto", "sucursal_id", "pedir", "total_sugerido_suc"],
        ["ACEITE-ML", "LINDEROS", "Si", 765058],
    ])
    r = client.post("/api/admin/cargar-sugerido", files={"file": ("c.xlsx", buf, MIME_XLSX)})
    assert r.status_code == 200
    advertencias = " | ".join(r.json()["advertencias"])
    assert "ACEITE-ML" in advertencias
    assert "corrupta" in advertencias


def test_csv_comillas_dobles_no_pierde_filas():
    """El parser CSV con dialecto fijo no descuadra filas con comillas embebidas
    (descripciones tipo 15\"/16), que con csv.Sniffer se perdian."""
    from src.services.excel_loader import _rows_from_csv

    contenido = (
        '"producto","sucursal_id","descripcion","total_sugerido_suc"\n'
        'ABR-1,RANCAGUA,"LLAVE 15""/16",4\n'
        "ABR-2,TALCA,TUERCA 1/2,2\n"
    ).encode("utf-8")
    headers, rows = _rows_from_csv(contenido)
    assert headers == ["producto", "sucursal_id", "descripcion", "total_sugerido_suc"]
    assert len(rows) == 2
    assert rows[0][2] == 'LLAVE 15"/16'


def test_vista_distribucion_solo_filas_accionables(client, db_session):
    """La vista distribucion solo trae filas con traslado > 0 o sugerido directo > 0
    (contrato del modelo BI); las filas en cero no aportan decision."""
    from src.models import Sugerido

    db_session.add(Sugerido(
        tenant_id="curifor", producto="DIST-CERO", sucursal_id="TALCA",
        nombre_sucursal="Talca", abastece_cd="Si", pedir="No",
        sugerido_traslado=0, total_sugerido_suc=0,
    ))
    db_session.add(Sugerido(
        tenant_id="curifor", producto="DIST-OK", sucursal_id="TALCA",
        nombre_sucursal="Talca", abastece_cd="Si", pedir="No",
        sugerido_traslado=7, total_sugerido_suc=0,
    ))
    db_session.commit()

    r = client.get("/api/sugerido", params={"vista": "distribucion", "solo_pedir": False})
    productos = {i["producto"] for i in r.json()["items"]}
    assert "DIST-OK" in productos
    assert "DIST-CERO" not in productos


def test_admin_endpoint_rechaza_no_admin(db_session):
    """Un usuario autenticado pero sin es_admin recibe 403 en /api/admin/*."""
    from fastapi.testclient import TestClient

    from src.db import get_db
    from src.main import app
    from src.services.auth import requiere_auth

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        with TestClient(app) as c:
            r = c.get("/api/admin/powerbi/estado")
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_expira_en_fecha_pasada_rechazada(client):
    """Crear una sugerencia con fecha limite en el pasado devuelve 422 (naceria vencida)."""
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS",
        "unidades": 5, "expira_en": "2020-01-01",
    })
    assert r.status_code == 422
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS",
        "unidades": 5, "expira_en": "9999-12-31",
    })
    assert r.status_code == 422


def test_manual_vencida_no_suma_en_chatbot_tool(db_session):
    """La tool del chatbot excluye manuales vencidas igual que la grilla y el carro."""
    from datetime import datetime, timedelta, timezone

    from src.models import SugerenciaManual
    from src.services.chatbot_service import _tool_obtener_sugerido

    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto="20 BXO5W30AA", sucursal_id="LINDEROS",
        unidades=99, creado_por="test@curifor.com",
        expira_en=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    db_session.commit()
    out = _tool_obtener_sugerido(db_session, "20 BXO5W30AA", "LINDEROS")
    assert out["ajuste_manual_vigente"] == 0
