import uuid
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alert import Alert
from app.schemas.alert import AlertCreate, AlertUpdate


class AlertRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, alert_id: uuid.UUID) -> Optional[Alert]:
        result = await self.session.execute(select(Alert).where(Alert.id == alert_id))
        return result.scalars().first()

    async def list_filtered(self, status: Optional[str] = None) -> List[Alert]:
        stmt = select(Alert)
        if status:
            stmt = stmt.where(Alert.status == status)
        stmt = stmt.order_by(Alert.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, schema: AlertCreate) -> Alert:
        alert = Alert(
            asset_id=schema.asset_id,
            severity=schema.severity.value if hasattr(schema.severity, 'value') else schema.severity,
            type=schema.type,
            title=schema.title,
            message=schema.message,
            status="open"
        )
        self.session.add(alert)
        await self.session.commit()
        await self.session.refresh(alert)
        return alert

    async def update(self, alert: Alert, schema: AlertUpdate) -> Alert:
        alert.status = schema.status.value if hasattr(schema.status, 'value') else schema.status
        if alert.status == "resolved":
            alert.resolved_at = datetime.now(timezone.utc)
        else:
            alert.resolved_at = None
        await self.session.commit()
        await self.session.refresh(alert)
        return alert
        
    async def get_open_alert_by_type(self, asset_id: uuid.UUID, alert_type: str) -> Optional[Alert]:
        stmt = select(Alert).where(and_(
            Alert.asset_id == asset_id,
            Alert.type == alert_type,
            Alert.status == "open"
        ))
        result = await self.session.execute(stmt)
        return result.scalars().first()
