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
    assert len(body["meses"]) == 3
    assert body["meses"][0]["mes"] == "202503"  # orden ascendente
    assert body["total"] == 35


def test_ventas_12m_sin_datos(client):
    # Producto sin ventas: responde 200 con lista vacia (no 404).
    r = client.get("/api/sugerido/NOEXISTE/LINDEROS/ventas")
    assert r.status_code == 200
    assert r.json()["meses"] == []


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


def test_carros_export_excel(client):
    r = client.post("/api/compras/export-excel", json={"filtros": {"solo_pedir": True}})
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 0


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
    monkeypatch.setattr(powerbi_desktop_loader, "_ejecutar_script", lambda dax: fake)

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
        lambda dax: {"ok": False, "error": "El proveedor 'MSOLAP' no esta registrado"},
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
