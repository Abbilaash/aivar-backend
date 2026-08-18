import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/aivar",
        description="SQLAlchemy asyncpg connection URL for PostgreSQL"
    )
    APP_ENV: str = Field(default="development", description="Application environment (development, production)")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")
    WATCHER_ENABLED: bool = Field(default=True, description="Whether to run the Kubernetes Discovery Watcher background task")
    CLUSTER_NAME: str = Field(default="local-cluster", description="Name of the current Kubernetes cluster")
    CLUSTER_ENVIRONMENT: str = Field(default="development", description="Environment status of the cluster (dev, staging, prod)")
    API_KEY: str = Field(default="aivar-dev-secret-key-12345", description="API key to protect REST endpoints")
    
    # Watcher reconciliation and retry settings
    RECONCILIATION_INTERVAL_SECS: int = Field(default=300, description="Interval in seconds between full Kubernetes cluster scans")
    WATCHER_RETRY_DELAY_SECS: int = Field(default=5, description="Initial retry delay in seconds for Watch connection failures")
    WATCHER_MAX_RETRY_DELAY_SECS: int = Field(default=60, description="Maximum retry delay in seconds for Watch connection failures")

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() in ("development", "dev", "local")


settings = Settings()
