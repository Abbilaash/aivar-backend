import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


from typing import Optional

class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    environment: Mapped[str] = mapped_column(String(100), nullable=False)
    api_server: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    
    # Dynamic Multi-Cluster Configurations
    connection_type: Mapped[str] = mapped_column(String(50), default="kubeconfig", nullable=False)
    kube_context: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    aws_region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    eks_cluster_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    watch_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    connection_status: Mapped[str] = mapped_column(String(50), default="disabled", nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(nullable=True)
    credential_reference: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    aws_access_key_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    aws_secret_access_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )


    # Relationships
    assets = relationship("Asset", back_populates="cluster", cascade="all, delete-orphan")
