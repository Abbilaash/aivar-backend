import uuid
from datetime import datetime, timezone
from typing import List
from sqlalchemy import String, DateTime, ForeignKey, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cluster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    workload_uid: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)  # model, agent, tool
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    workload_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    workload_name: Mapped[str] = mapped_column(String(255), nullable=False)
    image_references: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    owner: Mapped[str] = mapped_column(String(255), default="unassigned", nullable=False)
    owner_source: Mapped[str] = mapped_column(String(100), default="unassigned", nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(50), default="low", nullable=False)  # low, medium, high
    risk_reasons: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    detection_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    detection_evidence: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)  # active, inactive
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("cluster_id", "workload_uid", name="uq_cluster_workload"),
    )

    # Relationships
    cluster = relationship("Cluster", back_populates="assets")
    events = relationship("DiscoveryEvent", back_populates="asset", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="asset", cascade="all, delete-orphan")
