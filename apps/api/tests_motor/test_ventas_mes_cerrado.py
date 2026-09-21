"""No publicar un sugerido calculado con el ultimo mes cerrado sin ventas.

Paso del 01 al 21-09-2026 sin que nadie lo notara: el respaldo `2026 (6).xlsx`
terminaba el 31-07, el motor tomo agosto como ultimo mes cerrado y las 17.102
filas salieron con `Venta Mes 01 = 0`. Tres semanas pidiendo de menos.

Lo que estos tests cuidan:

1. Que la guarda mire el EFECTO en el CSV (la columna del ultimo mes), no el
   archivo de origen.
2. Que los primeros dias del mes solo avise -el respaldo puede no estar
   exportado todavia- y desde el dia 4 frene.
3. Que una corrida oficial con el mes vacio NO llegue a la plataforma, y que
   `--ignorar-frescura` la deje pasar a proposito.
"""
import csv
from datetime import date

from src.jobs import correr_motor_real as job


def _csv(tmp_path, venta_mes_01, periodo="202608", filas=3):
    ruta = tmp_path / "sugerido_motor.csv"
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Producto", "SucursalID", "Periodo Ultimo Mes",
                                          "Venta Mes 01", "Venta Mes 02"])
        w.writeheader()
        for i in range(filas):
            w.writerow({"Producto": f"17 P{i}", "SucursalID": "LINDEROS",
                        "Periodo Ultimo Mes": periodo, "Venta Mes 01": venta_mes_01,
                        "Venta Mes 02": 5})
    return ruta


def test_con_ventas_en_el_mes_cerrado_no_pasa_nada(tmp_path):
    aviso, bloqueo = job.revisar_ventas_mes_cerrado(_csv(tmp_path, 2), date(2026, 9, 21))

    assert aviso is None and bloqueo is None


def test_el_mes_cerrado_en_cero_frena_desde_el_dia_4(tmp_path):
    aviso, bloqueo = job.revisar_ventas_mes_cerrado(_csv(tmp_path, 0), date(2026, 9, 21))

    assert aviso is None
    assert "08-2026" in bloqueo
    assert "Ventas" in bloqueo


def test_los_primeros_dias_del_mes_solo_avisa(tmp_path):
    """El respaldo del mes recien cerrado puede no estar exportado el dia 1."""
    aviso, bloqueo = job.revisar_ventas_mes_cerrado(_csv(tmp_path, 0), date(2026, 10, 2))

    assert bloqueo is None
    assert "08-2026" in aviso and "frena" in aviso


def test_un_csv_vacio_no_frena(tmp_path):
    """Sin filas no hay sugerido que proteger; de eso se encarga otro control."""
    assert job.revisar_ventas_mes_cerrado(_csv(tmp_path, 0, filas=0), date(2026, 9, 21)) == (None, None)


def test_la_venta_en_blanco_cuenta_como_cero(tmp_path):
    aviso, bloqueo = job.revisar_ventas_mes_cerrado(_csv(tmp_path, "", ), date(2026, 9, 21))

    assert bloqueo is not None


# --- La corrida oficial ---------------------------------------------------------


def _corrida(monkeypatch, tmp_path, venta, ignorar=False):
    ruta = _csv(tmp_path, venta)
    enviados = []
    monkeypatch.setattr(job, "revisar_frescura", lambda hoy=None: [])
    monkeypatch.setattr(job, "construir_csv", lambda hoy=None: ruta)
    monkeypatch.setattr(job, "enviar", lambda p, oficial=False: enviados.append(p) or {"filas_cargadas": 3, "advertencias": []})
    monkeypatch.setattr(job, "avisar_falla", lambda *a, **k: False)
    monkeypatch.setattr(job, "CANDADO", tmp_path / "motor.lock")

    # Un dia fijo pasado el 4: si no, el test cambiaria de resultado los primeros
    # dias de cada mes.
    class _Hoy(date):
        @classmethod
        def today(cls):
            return date(2026, 9, 21)
    monkeypatch.setattr(job, "date", _Hoy)
    # Los pasos posteriores no importan aca: se apagan.
    for nombre in ("publicar_lead_time", "publicar_stock_unificado", "publicar_transito",
                   "publicar_ventas_historicas", "publicar_sku_proveedor",
                   "publicar_proveedor_producto", "publicar_reemplazos", "recargar_instock",
                   "publicar_costos_precios", "publicar_compras_precios", "publicar_lista_erp",
                   "recalcular_precios"):
        if hasattr(job, nombre):
            monkeypatch.setattr(job, nombre, lambda *a, **k: None)
    codigo = job.run(oficial=True, ignorar_frescura=ignorar)
    return codigo, enviados


def test_la_corrida_oficial_no_publica_con_el_mes_vacio(monkeypatch, tmp_path):
    codigo, enviados = _corrida(monkeypatch, tmp_path, venta=0)

    assert codigo == 1
    assert enviados == [], "llego a la plataforma un sugerido con agosto en cero"


def test_con_ventas_la_corrida_publica(monkeypatch, tmp_path):
    codigo, enviados = _corrida(monkeypatch, tmp_path, venta=3)

    assert codigo == 0
    assert len(enviados) == 1


def test_ignorar_frescura_deja_pasar_a_proposito(monkeypatch, tmp_path):
    codigo, enviados = _corrida(monkeypatch, tmp_path, venta=0, ignorar=True)

    assert codigo == 0 and len(enviados) == 1
