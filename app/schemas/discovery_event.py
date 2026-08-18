from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Dict, Any, Optional
from app.schemas.enums import DiscoveryEventType


class DiscoveryEventBase(BaseModel):
    event_type: DiscoveryEventType
    before_snapshot: Optional[Dict[str, Any]] = None
    after_snapshot: Optional[Dict[str, Any]] = None


class DiscoveryEventCreate(DiscoveryEventBase):
    asset_id: UUID


class DiscoveryEventResponse(DiscoveryEventBase):
    id: UUID
    asset_id: UUID
    observed_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True
        
        # Override json_encoders to handle datetime properly in JSON response
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
