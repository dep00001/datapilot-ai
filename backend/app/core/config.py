from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_name: str = 'DataPilot AI'
    app_env: str = 'development'
    app_secret_key: str = 'DATAPILOT_DEV_SECRET_KEY_CHANGE_IN_PRODUCTION_98234710293847'
    database_url: str = 'sqlite:///./datapilot.db'
    storage_dir: str = './storage'
    max_upload_mb: int = 25
    cookie_secure: bool = False
    cookie_samesite: str = 'lax'
    cors_origins: str = 'http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173'
    session_days: int = 7
    otp_ttl_minutes: int = 5
    otp_max_attempts: int = 5
    otp_resend_seconds: int = 60
    auth_rate_limit_per_minute: int = 20
    email_provider: str = 'resend'
    email_from: str = 'DataPilot AI <verify@datapilot.ai>'
    resend_api_key: str = ''
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_use_tls: bool = True
    openai_api_key: str = ''
    openai_model: str = 'gpt-4o-mini'
    gemini_api_key: str = ''
    gemini_model: str = 'gemini-2.5-flash'
    admin_emails: str = 'admin@datapilot.ai'

settings = Settings()
STORAGE_DIR = Path(settings.storage_dir).resolve()
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
