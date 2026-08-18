from pydantic import BaseModel, Field, HttpUrl
from uuid import UUID
from datetime import datetime
from typing import Optional


class ClusterBase(BaseModel):
    name: str = Field(..., max_length=255)
    environment: str = Field(..., max_length=100)
    api_server: str = Field(..., max_length=512)


class ClusterCreate(ClusterBase):
    pass


class ClusterUpdate(BaseModel):
    status: Optional[str] = Field(None, max_length=50)
    environment: Optional[str] = Field(None, max_length=100)
    api_server: Optional[str] = Field(None, max_length=512)


class ClusterResponse(ClusterBase):
    id: UUID
    status: str
    last_seen_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True
