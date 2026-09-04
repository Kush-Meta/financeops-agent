"""Application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FinanceOps Agent"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api"

    database_url: str = f"sqlite:///{DATA_DIR / 'financeops.db'}"

    # LLM — leave empty to use deterministic mock planner/explainer
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    llm_enabled: bool = False

    # Matching thresholds
    reconcile_amount_tolerance: float = 0.01
    reconcile_date_window_days: int = 5
    reconcile_probable_amount_tolerance: float = 1.0
    anomaly_zscore_threshold: float = 3.0

    # CORS
    cors_origins: str = "http://localhost:3847,http://127.0.0.1:3847"

    log_level: str = "INFO"
    documents_dir: str = str(DATA_DIR / "documents")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
