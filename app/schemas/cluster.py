from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional
from enum import Enum


class ClusterConnectionType(str, Enum):
    KUBECONFIG = "kubeconfig"
    EKS_IAM = "eks_iam"
    OIDC = "oidc"


class ClusterConnectionStatus(str, Enum):
    CONNECTED = "connected"
    CONNECTING = "connecting"
    ERROR = "error"
    DISABLED = "disabled"


class ClusterBase(BaseModel):
    name: str = Field(..., max_length=255)
    environment: str = Field(..., max_length=100)
    api_server: str = Field(..., max_length=512)
    connection_type: ClusterConnectionType = Field(default=ClusterConnectionType.KUBECONFIG)
    kube_context: Optional[str] = Field(None, max_length=255)
    aws_region: Optional[str] = Field(None, max_length=100)
    eks_cluster_name: Optional[str] = Field(None, max_length=255)
    watch_enabled: bool = Field(default=False)
    credential_reference: Optional[str] = Field(None, max_length=512)
    aws_access_key_id: Optional[str] = Field(None, max_length=255)
    aws_secret_access_key: Optional[str] = Field(None, max_length=512)
    created_by: Optional[str] = Field(None, max_length=255)


class ClusterCreate(ClusterBase):
    pass


class ClusterUpdate(BaseModel):
    status: Optional[str] = Field(None, max_length=50)
    environment: Optional[str] = Field(None, max_length=100)
    api_server: Optional[str] = Field(None, max_length=512)
    connection_type: Optional[ClusterConnectionType] = None
    kube_context: Optional[str] = Field(None, max_length=255)
    aws_region: Optional[str] = Field(None, max_length=100)
    eks_cluster_name: Optional[str] = Field(None, max_length=255)
    watch_enabled: Optional[bool] = None
    connection_status: Optional[ClusterConnectionStatus] = None
    last_error: Optional[str] = None
    credential_reference: Optional[str] = Field(None, max_length=512)
    aws_access_key_id: Optional[str] = Field(None, max_length=255)
    aws_secret_access_key: Optional[str] = Field(None, max_length=512)


class ClusterResponse(ClusterBase):
    id: UUID
    status: str
    connection_status: ClusterConnectionStatus
    last_sync_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_seen_at: datetime
    created_at: datetime
    # Never expose secret key in response
    aws_secret_access_key: Optional[str] = Field(None, exclude=True)

    class Config:
        from_attributes = True
        populate_by_name = True
