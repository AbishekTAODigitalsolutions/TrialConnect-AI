import re

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    PROJECT_NAME: str = "Clinical Connect AI"
    APP_ENV: str = "development"
    APP_VERSION: str = "0.1.0"
    LOG_LEVEL: str = "INFO"
    CORE_API_HOST: str = "0.0.0.0"
    CORE_API_PORT: int = 8000
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:3001,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001"
    )
    POSTGRES_HOST: str = "clinical-data-store"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "trialconnect"
    POSTGRES_USER: str = "trialconnect_app"
    POSTGRES_PASSWORD: str = "replace_me"
    POSTGRES_SCHEMA: str = "public"
    REQUIRE_PGVECTOR: bool = True
    AUTH_SECRET: str = ""
    AUTH_TOKEN_TTL_SECONDS: int = 3600
    PATIENT_INVITE_TTL_HOURS: int = 72
    DEFAULT_STUDY_ID: str = "STUDY-001"
    DEFAULT_SITE_ID: str = "SITE-01"
    APPOINTMENT_REMINDER_POLL_SECONDS: int = 60
    REDIS_HOST: str = "task-broker"
    REDIS_PORT: int = 6379
    LLM_ENABLED: bool = False
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> URL:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.POSTGRES_SCHEMA):
            raise ValueError("POSTGRES_SCHEMA must be a valid unquoted PostgreSQL identifier")
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
            query={"options": f"-c search_path={self.POSTGRES_SCHEMA}"},
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
