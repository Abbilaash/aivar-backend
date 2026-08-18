from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class ContainerInfo(BaseModel):
    name: str
    image: str
    env: Dict[str, str] = Field(default_factory=dict)
    command: List[str] = Field(default_factory=list)
    args: List[str] = Field(default_factory=list)
    volume_mounts: List[str] = Field(default_factory=list)


class DiscoveryMessage(BaseModel):
    cluster_name: str = Field(..., max_length=255)
    workload_uid: str = Field(..., max_length=255)
    workload_kind: str = Field(..., max_length=100)
    workload_name: str = Field(..., max_length=255)
    namespace: str = Field(..., max_length=255)
    image_references: List[str] = Field(default_factory=list)
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    containers: List[ContainerInfo] = Field(default_factory=list)
    service_account_name: Optional[str] = Field(None, max_length=255)
    secret_references: List[str] = Field(default_factory=list)
    configmap_references: List[str] = Field(default_factory=list)
