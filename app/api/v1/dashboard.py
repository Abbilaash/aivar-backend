from fastapi import APIRouter, Depends, Header
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from typing import List, Any, Optional

from app.db.session import get_db_session
from app.repositories.asset import AssetRepository
from app.repositories.alert import AlertRepository
from app.core.security import verify_api_key
from app.models.asset import Asset
from app.models.alert import Alert
from app.models.cluster import Cluster

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    summary="Get summarized metrics for the AI registry dashboard",
    dependencies=[Depends(verify_api_key)]
)
async def get_dashboard_summary(
    x_user_username: Optional[str] = Header(None, alias="X-User-Username"),
    db: AsyncSession = Depends(get_db_session)
):
    # 1. Total assets count
    total_assets_stmt = select(func.count(Asset.id))
    if x_user_username:
        total_assets_stmt = total_assets_stmt.join(Cluster).where(or_(Cluster.created_by == x_user_username, Cluster.created_by == None))
    total_assets_res = await db.execute(total_assets_stmt)
    total_assets = total_assets_res.scalar_one() or 0

    # 2. High risk assets count
    high_risk_stmt = select(func.count(Asset.id)).where(Asset.risk_tier == 'high')
    if x_user_username:
        high_risk_stmt = high_risk_stmt.join(Cluster).where(or_(Cluster.created_by == x_user_username, Cluster.created_by == None))
    high_risk_res = await db.execute(high_risk_stmt)
    high_risk = high_risk_res.scalar_one() or 0

    # 3. Unassigned assets count
    unassigned_stmt = select(func.count(Asset.id)).where(Asset.owner == 'unassigned')
    if x_user_username:
        unassigned_stmt = unassigned_stmt.join(Cluster).where(or_(Cluster.created_by == x_user_username, Cluster.created_by == None))
    unassigned_res = await db.execute(unassigned_stmt)
    unassigned = unassigned_res.scalar_one() or 0

    # 4. Open alerts count
    open_alerts_stmt = select(func.count(Alert.id)).where(Alert.status == 'open')
    if x_user_username:
        open_alerts_stmt = open_alerts_stmt.join(Asset).join(Cluster).where(or_(Cluster.created_by == x_user_username, Cluster.created_by == None))
    open_alerts_res = await db.execute(open_alerts_stmt)
    open_alerts = open_alerts_res.scalar_one() or 0

    # 5. Last discovery timestamp
    last_discovery_stmt = select(func.max(Asset.created_at))
    if x_user_username:
        last_discovery_stmt = last_discovery_stmt.join(Cluster).where(or_(Cluster.created_by == x_user_username, Cluster.created_by == None))
    last_discovery_res = await db.execute(last_discovery_stmt)
    last_discovery_dt = last_discovery_res.scalar_one()
    if last_discovery_dt:
        last_discovery_at = last_discovery_dt.isoformat()
    else:
        last_discovery_at = datetime.now(timezone.utc).isoformat()

    # 6. Recent changes
    asset_repo = AssetRepository(db)
    # Query last 24 hours of changes to return in summary
    since = datetime.now(timezone.utc)
    recent_assets = await asset_repo.list_recent_changes(since, username=x_user_username)
    
    recent_changes = []
    for asset in recent_assets[:5]:
        recent_changes.append({
            "id": str(asset.id),
            "asset_name": asset.asset_name,
            "asset_type": asset.asset_type,
            "namespace": asset.namespace,
            "risk_tier": asset.risk_tier,
            "updated_at": asset.updated_at.isoformat()
        })

    return {
        "total_assets": total_assets,
        "high_risk_assets": high_risk,
        "unassigned_assets": unassigned,
        "open_alerts": open_alerts,
        "last_discovery_at": last_discovery_at,
        "recent_changes": recent_changes
    }
