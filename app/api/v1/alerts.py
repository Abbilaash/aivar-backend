import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.repositories.alert import AlertRepository
from app.schemas.alert import AlertResponse, AlertUpdate
from app.schemas.enums import AlertStatus
from app.core.security import verify_api_key

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "",
    response_model=List[AlertResponse],
    summary="List all alerts",
    dependencies=[Depends(verify_api_key)]
)
async def list_alerts(
    status: Optional[AlertStatus] = Query(None, description="Filter by status (open, resolved)"),
    db: AsyncSession = Depends(get_db_session)
):
    repo = AlertRepository(db)
    alerts = await repo.list_filtered(status=status.value if status else None)
    return alerts


@router.patch(
    "/{alert_id}",
    response_model=AlertResponse,
    summary="Resolve or update an alert's status",
    dependencies=[Depends(verify_api_key)]
)
async def update_alert(
    alert_id: uuid.UUID,
    schema: AlertUpdate,
    db: AsyncSession = Depends(get_db_session)
):
    repo = AlertRepository(db)
    alert = await repo.get_by_id(alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with ID '{alert_id}' not found"
        )
        
    updated_alert = await repo.update(alert, schema)
    return updated_alert
