import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.repositories.asset import AssetRepository
from app.repositories.discovery_event import DiscoveryEventRepository
from app.schemas.asset import AssetResponse
from app.schemas.discovery_event import DiscoveryEventResponse
from app.schemas.enums import AssetType, RiskTier, AssetStatus
from app.schemas.discovery import DiscoveryMessage
from app.services.asset import AssetService
from app.core.security import verify_api_key


router = APIRouter(prefix="/assets", tags=["assets"])


@router.get(
    "",
    response_model=List[AssetResponse],
    summary="List and filter discovered AI assets",
    dependencies=[Depends(verify_api_key)]
)
async def list_assets(
    cluster_id: Optional[uuid.UUID] = Query(None, description="Filter by cluster ID"),
    namespace: Optional[str] = Query(None, description="Filter by Kubernetes namespace"),
    asset_type: Optional[AssetType] = Query(None, description="Filter by asset type (model, agent, tool)"),
    risk_tier: Optional[RiskTier] = Query(None, description="Filter by risk tier (low, medium, high)"),
    owner: Optional[str] = Query(None, description="Filter by owner"),
    status: Optional[AssetStatus] = Query(None, description="Filter by status (active, inactive)"),
    search: Optional[str] = Query(None, description="Search term for asset/workload name or owner"),
    skip: int = Query(0, ge=0, description="Offset index for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Limit count for pagination"),
    db: AsyncSession = Depends(get_db_session)
):
    repo = AssetRepository(db)
    assets, _ = await repo.list_filtered(
        cluster_id=cluster_id,
        namespace=namespace,
        asset_type=asset_type.value if asset_type else None,
        risk_tier=risk_tier.value if risk_tier else None,
        owner=owner,
        status=status.value if status else None,
        search=search,
        skip=skip,
        limit=limit
    )
    return assets


@router.get(
    "/{asset_id}",
    response_model=AssetResponse,
    summary="Get asset detail",
    dependencies=[Depends(verify_api_key)]
)
async def get_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session)
):
    repo = AssetRepository(db)
    asset = await repo.get_by_id(asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with ID '{asset_id}' not found"
        )
    return asset


@router.get(
    "/{asset_id}/events",
    response_model=List[DiscoveryEventResponse],
    summary="Get audit event logs for a specific asset",
    dependencies=[Depends(verify_api_key)]
)
async def get_asset_events(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session)
):
    # Verify asset exists first
    asset_repo = AssetRepository(db)
    asset = await asset_repo.get_by_id(asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with ID '{asset_id}' not found"
        )

    event_repo = DiscoveryEventRepository(db)
    events = await event_repo.list_by_asset(asset_id)
    return events


@router.post(
    "/discovery",
    response_model=Optional[AssetResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a normalized Kubernetes workload discovery message",
    dependencies=[Depends(verify_api_key)]
)
async def ingest_discovery_message(
    msg: DiscoveryMessage,
    db: AsyncSession = Depends(get_db_session)
):
    service = AssetService(db)
    asset = await service.process_discovery_message(msg)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail="Workload processed, but did not qualify as an AI asset"
        )
    return asset

