from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Dict, List


class UserBase(BaseModel):
    username: str = Field(..., max_length=255)


class UserCreate(UserBase):
    password: str = Field(..., min_length=4)



class UserLogin(UserBase):
    password: str


class UpdateMonitoringSettings(BaseModel):
    # Mapping of cluster_name or cluster_id to list of namespace names
    monitored_namespaces: Dict[str, List[str]]


class UserChangePassword(BaseModel):
    password: str = Field(..., min_length=4)


class UserResponse(UserBase):
    id: UUID
    monitored_namespaces: Dict[str, List[str]]
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True
