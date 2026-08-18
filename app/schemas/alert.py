from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional
from app.schemas.enums import AlertSeverity, AlertStatus


class AlertBase(BaseModel):
    severity: AlertSeverity
    type: str = Field(..., max_length=100)
    title: str = Field(..., max_length=255)
    message: str


class AlertCreate(AlertBase):
    asset_id: UUID


class AlertUpdate(BaseModel):
    status: AlertStatus


class AlertResponse(AlertBase):
    id: UUID
    asset_id: UUID
    status: AlertStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True
