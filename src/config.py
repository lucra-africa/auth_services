from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # App
    app_name: str = "poruta-auth"
    app_env: str = "development"
    app_port: int = 8050
    app_debug: bool = True

    # Database — MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_uri_fallback: str = ""
    mongo_db: str = "poruta_auth"

    # MinIO
    minio_endpoint: str = "http://localhost:9002"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_chat_bucket: str = "chat-attachments"

    # JWT
    jwt_secret_key: str = "1HEeHN81HTCSVYnzv4hIPgTTiBLXU3V7VoMuX351KS7"
    jwt_algorithm: str = "RS256"
    jwt_private_key_path: str = ""
    jwt_public_key_path: str = ""
    jwt_private_key: str = ""  # PEM content directly (for platforms without persistent filesystem)
    jwt_public_key: str = ""   # PEM content directly
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # SMTP — Zoho Mail (SSL/TLS on port 465)
    smtp_host: str = "smtp.zoho.com"
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    smtp_username: str = "support@poruta.com"
    smtp_password: str = ""
    smtp_from_email: str = "support@poruta.com"
    smtp_from_name: str = "Poruta"

    # Frontend
    frontend_url: str = "http://localhost:9000"

    # Admin seed
    admin_email: str | None = None
    admin_password: str | None = None

    # CORS
    cors_origins: str = "http://localhost:9000,http://localhost:3000"

    # Notification push API key (for external services like poruta-backend)
    notification_api_key: str = ""

    # Service-to-service API key (for poruta-backend internal calls)
    service_api_key: str = ""

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
