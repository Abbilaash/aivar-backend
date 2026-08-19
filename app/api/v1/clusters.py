import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.repositories.cluster import ClusterRepository
from app.schemas.cluster import ClusterResponse, ClusterCreate, ClusterUpdate
from app.core.security import verify_api_key

from fastapi import APIRouter, Depends, HTTPException, status, Header

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get(
    "",
    response_model=List[ClusterResponse],
    summary="List all registered Kubernetes clusters",
    dependencies=[Depends(verify_api_key)]
)
async def list_clusters(
    x_user_username: Optional[str] = Header(None, alias="X-User-Username"),
    db: AsyncSession = Depends(get_db_session)
):
    repo = ClusterRepository(db)
    clusters = await repo.list_all(username=x_user_username)
    return clusters


@router.post(
    "",
    response_model=ClusterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new cluster configuration profile",
    dependencies=[Depends(verify_api_key)]
)
async def create_cluster(
    schema: ClusterCreate,
    x_user_username: Optional[str] = Header(None, alias="X-User-Username"),
    db: AsyncSession = Depends(get_db_session)
):
    repo = ClusterRepository(db)
    
    # Check if name is already registered
    existing = await repo.get_by_name(schema.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cluster with name '{schema.name}' is already registered"
        )
        
    schema.created_by = x_user_username
    cluster = await repo.create(schema)
    
    # Trigger watch manager synchronization
    from app.discovery.manager import watch_manager
    await watch_manager.trigger_reloading()
    
    return cluster


@router.patch(
    "/{cluster_id}",
    response_model=ClusterResponse,
    summary="Update cluster or toggle watch_enabled status",
    dependencies=[Depends(verify_api_key)]
)
async def update_cluster(
    cluster_id: uuid.UUID,
    schema: ClusterUpdate,
    db: AsyncSession = Depends(get_db_session)
):
    repo = ClusterRepository(db)
    cluster = await repo.get_by_id(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cluster with ID '{cluster_id}' not found"
        )
        
    cluster = await repo.update(cluster, schema)
    
    # Trigger watch manager synchronization
    from app.discovery.manager import watch_manager
    await watch_manager.trigger_reloading()
    
    return cluster
