import uuid
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.discovery_event import DiscoveryEvent
from app.schemas.discovery_event import DiscoveryEventCreate


class DiscoveryEventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_asset(self, asset_id: uuid.UUID) -> List[DiscoveryEvent]:
        stmt = select(DiscoveryEvent).where(DiscoveryEvent.asset_id == asset_id).order_by(DiscoveryEvent.observed_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, schema: DiscoveryEventCreate) -> DiscoveryEvent:
        event = DiscoveryEvent(
            asset_id=schema.asset_id,
            event_type=schema.event_type.value if hasattr(schema.event_type, 'value') else schema.event_type,
            before_snapshot=schema.before_snapshot,
            after_snapshot=schema.after_snapshot
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event
