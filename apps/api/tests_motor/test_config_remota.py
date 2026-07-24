"""La config remota de la plataforma sobrescribe las constantes del modelo."""
import pytest

from src.jobs import correr_motor_real as job
from src.motor import parametros as P


@pytest.fixture()
def parametros_intactos():
    """Guarda y restaura las constantes que aplicar_config toca (el modulo es global)."""
    snap = {
        k: getattr(P, k)
        for k in ("CICLO_ORDEN_DIAS", "CICLO_ORDEN_DIAS_CD", "Z_POR_CLASE",
                  "Z_IMPORTADO_CD", "LT_FALLBACK_DIAS", "WINSOR_K")
    }
    yield
    for k, v in snap.items():
        setattr(P, k, v)


def test_aplicar_config_sobrescribe_los_parametros(parametros_intactos):
    job.aplicar_config({
        "ciclo_orden_dias": 5,
        "ciclo_orden_dias_cd": 7,
        "z_por_clase": {"A": 2.0, "B": 1.5, "C": 1.0, "D": 0.0},
        "z_importado_cd": {"A": 1.5, "B": 1.2},
        "lead_time_fallback_dias": 10,
        "winsor_k": 2.5,
        "es_default": False,
        "creado_por": "jefa@curifor.com",
    })
    assert P.CICLO_ORDEN_DIAS_CD == 7
    assert P.Z_POR_CLASE == {"A": 2.0, "B": 1.5, "C": 1.0, "D": 0.0}
    assert P.Z_IMPORTADO_CD == {"A": 1.5, "B": 1.2}
    assert P.LT_FALLBACK_DIAS == 10 and P.WINSOR_K == 2.5


def test_aplicar_config_solo_toca_lo_que_viene(parametros_intactos):
    """Una config parcial no borra los otros parametros."""
    antes_ciclo = P.CICLO_ORDEN_DIAS
    job.aplicar_config({"ciclo_orden_dias_cd": 9, "es_default": False})
    assert P.CICLO_ORDEN_DIAS_CD == 9
    assert P.CICLO_ORDEN_DIAS == antes_ciclo  # intacto


def test_sin_credenciales_obtener_config_devuelve_none(monkeypatch):
    """Sin credenciales no revienta: devuelve None y el motor usa las constantes."""
    monkeypatch.setattr(job, "_credenciales", lambda: ("http://x", None, None))
    assert job.obtener_config() is None
