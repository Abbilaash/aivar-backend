from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.repositories.cluster import ClusterRepository
from app.schemas.cluster import ClusterResponse, ClusterCreate
from app.core.security import verify_api_key

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get(
    "",
    response_model=List[ClusterResponse],
    summary="List all registered Kubernetes clusters",
    dependencies=[Depends(verify_api_key)]
)
async def list_clusters(db: AsyncSession = Depends(get_db_session)):
    repo = ClusterRepository(db)
    clusters = await repo.list_all()
    return clusters


@router.post(
    "",
    response_model=ClusterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new cluster metadata endpoint",
    dependencies=[Depends(verify_api_key)]
)
async def create_cluster(
    schema: ClusterCreate,
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
        
    cluster = await repo.create(schema)
    return cluster
