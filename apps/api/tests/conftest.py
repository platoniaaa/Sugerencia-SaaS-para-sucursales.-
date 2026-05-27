"""Fixtures de pytest: base de datos SQLite en memoria + cliente de prueba con datos."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db import Base, get_db
from src.main import app
from src.models import (
    DimProducto,
    DimSucursal,
    PostVentaFila,
    PostVentaMeta,
    Sugerido,
    Usuario,
    VentaMensual,
)
from src.services.auth import hash_password, requiere_auth


@pytest.fixture()
def db_session():
    # StaticPool + una sola conexion compartida: necesario para que la DB en memoria
    # sea visible desde el thread del endpoint (FastAPI corre en un threadpool).
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    _seed(session)
    try:
        yield session
    finally:
        session.close()


def _seed(session):
    session.add(Usuario(email="test@curifor.com", password_hash=hash_password("123456"), nombre="Test"))
    session.add(DimSucursal(sucursal_id="LINDEROS", tenant_id="curifor", nombre="Linderos"))
    session.add(DimProducto(
        producto="20 BXO5W30AA", tenant_id="curifor", descripcion="ACEITE 5W30 LITRO FORD",
        filtro1_final="FORD", costo_unitario=5000, proveedor="Ford Motor Company Chile",
    ))
    session.add(Sugerido(
        tenant_id="curifor", producto="20 BXO5W30AA", descripcion="ACEITE 5W30 LITRO FORD",
        sucursal_id="LINDEROS", nombre_sucursal="Linderos", clasificacion_abc="A",
        proveedor="Ford Motor Company Chile", filtro1_final="FORD", tipo_origen="Importado",
        pedir="Si", costo_unitario=5000, total_sugerido_suc=10, total_valor_sugerido_clp=50000,
        sugerido_traslado=4, sugerido_compra_neto=6, pedir_flag="Si",
    ))
    for mes, cant in [("202503", 12), ("202504", 8), ("202505", 15)]:
        session.add(VentaMensual(
            tenant_id="curifor", producto="20 BXO5W30AA", sucursal_id="LINDEROS",
            mes=mes, cantidad=cant,
        ))
    # Post Venta: 3 filas (arreglo posicional) en 2 períodos / 2 sucursales.
    cols = ["Periodo", "SUCURSAL", "Producto", "Total"]
    pv = [
        ["202601", "LINDEROS", "P1", "100"],
        ["202601", "TALCA", "P2", "200"],
        ["202602", "LINDEROS", "P3", "300"],
    ]
    for fila in pv:
        session.add(PostVentaFila(
            tenant_id="curifor", periodo=fila[0], sucursal=fila[1],
            datos=json.dumps(fila, ensure_ascii=False),
        ))
    session.add(PostVentaMeta(
        tenant_id="curifor",
        columnas=json.dumps(cols),
        filas=3,
        periodos=json.dumps(["202601", "202602"]),
        sucursales=json.dumps(["LINDEROS", "TALCA"]),
    ))
    session.commit()


@pytest.fixture()
def client(db_session):
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    # Bypass de autenticacion en los tests (los endpoints de datos estan protegidos).
    app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
