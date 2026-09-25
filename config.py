"""Configurações centralizadas do projeto; nunca registra segredos em logs."""
from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')


@dataclass(frozen=True)
class Settings:
    google_api_key: str = os.getenv('GOOGLE_API_KEY', '')
    gemini_model: str = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash')
    # Ativado somente quando informado explicitamente no .env (pode gerar custo extra).
    gemini_fallback_model: str = os.getenv('GEMINI_FALLBACK_MODEL', '').strip()
    # Máximo de uma tentativa extra (pode gerar custo adicional de API).
    gemini_format_retry: bool = os.getenv('GEMINI_FORMAT_RETRY', 'true').strip().lower() == 'true'
    controls_source: str = os.getenv('CONTROLS_SOURCE', 'data/controles_demo.json')
    controls_sheet: str = os.getenv('CONTROLS_SHEET', 'PT-BR')
    max_image_bytes: int = int(os.getenv('MAX_IMAGE_BYTES', str(8 * 1024 * 1024)))
    audit_log_enabled: bool = os.getenv('AUDIT_LOG_ENABLED', 'false').lower() == 'true'
    cors_origins: tuple[str, ...] = tuple(
        o.strip() for o in os.getenv('CORS_ORIGINS', '').split(',') if o.strip()
    )

    @property
    def resolved_catalog_path(self) -> Path:
        path = Path(self.controls_source)
        return path if path.is_absolute() else ROOT / path

settings = Settings()
