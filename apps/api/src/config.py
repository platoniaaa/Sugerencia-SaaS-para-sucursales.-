"""Configuracion central de la app, leida desde variables de entorno (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Conexion a la base de datos. Por defecto SQLite local (Fase 0).
    # En produccion: postgresql+pg8000://usuario:clave@host:5432/postgres (Supabase).
    database_url: str = "sqlite:///./data/sugerido.db"

    # Usar SSL en conexiones PostgreSQL (Supabase lo exige). Poner false solo para
    # un Postgres local sin SSL.
    db_ssl: bool = True

    # Tenant por defecto (multi-tenant llega en Fase 2).
    default_tenant_id: str = "curifor"

    # Usuario admin placeholder (auth real llega despues).
    admin_email: str = "francisco@curifor.cl"

    # Origenes permitidos por CORS (separados por coma).
    cors_origins: str = "http://localhost:3000"

    # --- Power BI (ingesta automatica via API executeQueries) ---
    # Credenciales de un "service principal" (app registrada en Entra ID) con acceso
    # al workspace. Si quedan vacias, la sincronizacion con Power BI esta desactivada.
    powerbi_tenant_id: str = ""
    powerbi_client_id: str = ""
    powerbi_client_secret: str = ""
    powerbi_group_id: str = ""  # ID del workspace (group) en Power BI
    powerbi_dataset_id: str = ""  # ID del dataset publicado
    # Consulta DAX para extraer el sugerido. Trae las columnas base de la tabla
    # 'Sugerido por Sucursal' MAS las medidas calculadas (Total Sugerido, Stock Activo,
    # Traslado, etc.), porque esas son medidas del modelo, no columnas de la tabla.
    # Ajustada al modelo real de Curifor. Si los nombres cambian, editar aqui o en .env.
    powerbi_dax_query: str = """
EVALUATE
SUMMARIZECOLUMNS(
  'Sugerido por Sucursal'[Producto],
  'Sugerido por Sucursal'[SucursalID],
  'Sugerido por Sucursal'[Nombre Sucursal],
  'Sugerido por Sucursal'[Descripcion],
  'Sugerido por Sucursal'[Clasificacion ABC],
  'Sugerido por Sucursal'[Proveedor],
  'Sugerido por Sucursal'[FILTRO1_Final],
  'Sugerido por Sucursal'[Tipo Origen],
  'Sugerido por Sucursal'[Es Importado],
  'Sugerido por Sucursal'[Unidad de Medida],
  'Sugerido por Sucursal'[Lead Time Dias],
  'Sugerido por Sucursal'[LT Efectivo],
  'Sugerido por Sucursal'[LT CD a Sucursal Dias],
  'Sugerido por Sucursal'[LT Origen],
  'Sugerido por Sucursal'[Abastece CD],
  'Sugerido por Sucursal'[Prioridad CD],
  'Sugerido por Sucursal'[Tiene Stock CD],
  'Sugerido por Sucursal'[Demanda Mensual],
  'Sugerido por Sucursal'[Demanda Diaria],
  'Sugerido por Sucursal'[Desv Std Mensual],
  'Sugerido por Sucursal'[Stock de Seguridad],
  'Sugerido por Sucursal'[Punto de Pedido],
  'Sugerido por Sucursal'[Costo Unitario],
  'Sugerido por Sucursal'[Pedir],
  'Sugerido por Sucursal'[Reemplazos],
  "total_sugerido_suc", [Total Sugerido Suc],
  "total_valor_sugerido_clp", [Total Valor Sugerido Suc CLP],
  "sugerido_suc", [Sugerido Suc],
  "stock_activo_suc", [Stock Activo Suc],
  "stock_en_transito_suc", [Stock en Transito Suc],
  "stock_en_cd", [Stock en CD],
  "sugerido_traslado", [Sugerido Traslado],
  "sugerido_compra_neto", [Sugerido Compra Neto],
  "comprar_en_el_cd", [Comprar en el CD],
  "pedir_flag", [Pedir?]
)
""".strip()

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def powerbi_configurado(self) -> bool:
        return all(
            [
                self.powerbi_tenant_id,
                self.powerbi_client_id,
                self.powerbi_client_secret,
                self.powerbi_group_id,
                self.powerbi_dataset_id,
            ]
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
