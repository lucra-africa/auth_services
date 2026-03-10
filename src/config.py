from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # App
    app_name: str = "poruta-auth"
    app_env: str = "development"
    app_port: int = 5000
    app_debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/poruta_auth"

    # JWT
    jwt_secret_key: str = "1HEeHN81HTCSVYnzv4hIPgTTiBLXU3V7VoMuX351KS7"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # SMTP
    smtp_host: str = "smtp.zoho.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@poruta.com"
    smtp_from_name: str = "Poruta"

    # Frontend
    frontend_url: str = "http://localhost:9000"

    # Admin seed
    admin_email: str | None = None
    admin_password: str | None = None

    # CORS
    cors_origins: str = "http://localhost:9000,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    model_config = SettingsConfigDict(
        env_file=str(_BASE_DIR / ".env"),
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )


settings = Settings()
