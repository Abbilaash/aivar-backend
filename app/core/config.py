import os
from typing import Optional
from pydantic import Field, field_validator
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

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def convert_database_url(cls, v: str) -> str:
        if not isinstance(v, str):
            return v

        # Resolve correct scheme prefix
        if v.startswith("postgresql://"):
            prefix = "postgresql+asyncpg://"
            url_part = v[len("postgresql://"):]
        elif v.startswith("postgres://"):
            prefix = "postgresql+asyncpg://"
            url_part = v[len("postgres://"):]
        elif v.startswith("postgresql+asyncpg://"):
            prefix = "postgresql+asyncpg://"
            url_part = v[len("postgresql+asyncpg://"):]
        else:
            return v

        # Split by the last '@' to isolate credentials from host details
        if "@" in url_part:
            creds_part, host_part = url_part.rsplit("@", 1)
            if ":" in creds_part:
                username, password = creds_part.split(":", 1)
                import urllib.parse
                # Safely URL-encode the password to handle special characters like '@'
                safe_password = urllib.parse.quote_plus(password)
                return f"{prefix}{username}:{safe_password}@{host_part}"

        return f"{prefix}{url_part}"


    APP_ENV: str = Field(default="development", description="Application environment (development, production)")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")
    WATCHER_ENABLED: bool = Field(default=True, description="Whether to run the Kubernetes Discovery Watcher background task")
    CLUSTER_NAME: str = Field(default="local-cluster", description="Name of the current Kubernetes cluster")
    CLUSTER_ENVIRONMENT: str = Field(default="development", description="Environment status of the cluster (dev, staging, prod)")
    API_KEY: str = Field(default="aivar-dev-secret-key-12345", description="API key to protect REST endpoints")
    
    # EKS Chatbot Service — override after `kubectl get svc -n aivar-copilot`
    CHATBOT_SERVICE_URL: str = Field(
        default="http://localhost:8081/chat",
        description="Internal URL of the AIVAR Copilot chatbot pod (EKS LoadBalancer)"
    )

    # EKS / Custom K8s cluster configurations
    KUBECONFIG_PATH: Optional[str] = Field(default=None, description="Path to custom Kubeconfig file (local/EC2)")
    AWS_REGION: Optional[str] = Field(default=None, description="AWS Region for EKS authentication context")
    EKS_CLUSTER_NAME: Optional[str] = Field(default=None, description="EKS Cluster Name for EC2 IAM role mapping context")

    # Watcher reconciliation and retry settings

    RECONCILIATION_INTERVAL_SECS: int = Field(default=300, description="Interval in seconds between full Kubernetes cluster scans")
    WATCHER_RETRY_DELAY_SECS: int = Field(default=5, description="Initial retry delay in seconds for Watch connection failures")
    WATCHER_MAX_RETRY_DELAY_SECS: int = Field(default=60, description="Maximum retry delay in seconds for Watch connection failures")

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() in ("development", "dev", "local")


settings = Settings()
