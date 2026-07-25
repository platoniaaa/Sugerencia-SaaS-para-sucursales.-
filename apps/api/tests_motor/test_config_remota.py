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
                  "Z_IMPORTADO_CD", "LT_FALLBACK_DIAS", "WINSOR_K",
                  "DIAS_HABILES_MES", "LT_CD_RM", "LT_CD_RESTO", "LT_TOPE_DIAS",
                  "TRANSITO_VENTANA_NACIONAL_DIAS", "TRANSITO_VENTANA_IMPORTADO_DIAS")
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


def test_aplicar_config_perillas_lead_time_y_transito(parametros_intactos):
    """Las perillas del modulo Lead time / transito tambien se aplican."""
    job.aplicar_config({
        "dias_habiles_mes": 20,
        "lt_cd_rm_dias": 2,
        "lt_cd_resto_dias": 3,
        "lt_tope_dias": 45,
        "transito_nacional_dias": 40,
        "transito_importado_dias": 200,
        "es_default": False,
    })
    assert P.DIAS_HABILES_MES == 20
    assert P.LT_CD_RM == 2 and P.LT_CD_RESTO == 3
    assert P.LT_TOPE_DIAS == 45
    assert P.TRANSITO_VENTANA_NACIONAL_DIAS == 40
    assert P.TRANSITO_VENTANA_IMPORTADO_DIAS == 200


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
