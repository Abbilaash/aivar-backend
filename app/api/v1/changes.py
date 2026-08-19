from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional

from app.db.session import get_db_session
from app.repositories.asset import AssetRepository
from app.schemas.asset import AssetResponse
from app.core.security import verify_api_key

router = APIRouter(prefix="/changes", tags=["changes"])


class ChangesResponse(BaseModel):
    new_assets: List[AssetResponse]
    changed_assets: List[AssetResponse]
    inactive_assets: List[AssetResponse]


@router.get(
    "",
    response_model=ChangesResponse,
    summary="Get recent workload changes (new, changed, inactive assets)",
    dependencies=[Depends(verify_api_key)]
)
async def get_changes(
    since_hours: int = Query(24, ge=1, description="Lookup period in hours"),
    x_user_username: Optional[str] = Header(None, alias="X-User-Username"),
    db: AsyncSession = Depends(get_db_session)
):
    since_time = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    
    asset_repo = AssetRepository(db)
    assets = await asset_repo.list_recent_changes(since_time, username=x_user_username)
    
    new_assets = []
    changed_assets = []
    inactive_assets = []
    
    for asset in assets:
        if asset.status == "inactive":
            inactive_assets.append(asset)
        elif asset.first_seen_at >= since_time:
            new_assets.append(asset)
        else:
            changed_assets.append(asset)
            
    return ChangesResponse(
        new_assets=new_assets,
        changed_assets=changed_assets,
        inactive_assets=inactive_assets
    )
