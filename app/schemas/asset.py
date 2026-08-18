from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import List, Optional
from app.schemas.enums import AssetType, RiskTier, AssetStatus


class AssetBase(BaseModel):
    asset_name: str = Field(..., max_length=255)
    asset_type: AssetType
    namespace: str = Field(..., max_length=255)
    workload_kind: str = Field(..., max_length=100)
    workload_name: str = Field(..., max_length=255)
    image_references: List[str] = Field(default_factory=list)
    owner: str = Field(default="unassigned", max_length=255)
    owner_source: str = Field(default="unassigned", max_length=100)
    risk_tier: RiskTier = Field(default=RiskTier.LOW)
    risk_reasons: List[str] = Field(default_factory=list)
    detection_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    detection_evidence: List[str] = Field(default_factory=list)


class AssetCreate(AssetBase):
    cluster_id: UUID
    workload_uid: str = Field(..., max_length=255)


class AssetUpdate(BaseModel):
    asset_name: Optional[str] = Field(None, max_length=255)
    asset_type: Optional[AssetType] = None
    namespace: Optional[str] = Field(None, max_length=255)
    image_references: Optional[List[str]] = None
    owner: Optional[str] = Field(None, max_length=255)
    owner_source: Optional[str] = Field(None, max_length=100)
    risk_tier: Optional[RiskTier] = None
    risk_reasons: Optional[List[str]] = None
    detection_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    detection_evidence: Optional[List[str]] = None
    status: Optional[AssetStatus] = None
    last_active_at: Optional[datetime] = None


class AssetResponse(AssetBase):
    id: UUID
    cluster_id: UUID
    workload_uid: str
    status: AssetStatus
    first_seen_at: datetime
    last_active_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True
