import uuid
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.cluster import Cluster
from app.schemas.cluster import ClusterCreate


class ClusterRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, cluster_id: uuid.UUID) -> Optional[Cluster]:
        result = await self.session.execute(select(Cluster).where(Cluster.id == cluster_id))
        return result.scalars().first()

    async def get_by_name(self, name: str) -> Optional[Cluster]:
        result = await self.session.execute(select(Cluster).where(Cluster.name == name))
        return result.scalars().first()

    async def list_all(self) -> List[Cluster]:
        result = await self.session.execute(select(Cluster).order_by(Cluster.created_at.desc()))
        return list(result.scalars().all())

    async def create(self, schema: ClusterCreate) -> Cluster:
        cluster = Cluster(
            name=schema.name,
            environment=schema.environment,
            api_server=schema.api_server,
            status="active"
        )
        self.session.add(cluster)
        await self.session.commit()
        await self.session.refresh(cluster)
        return cluster

    async def update_last_seen(self, cluster_id: uuid.UUID) -> Optional[Cluster]:
        cluster = await self.get_by_id(cluster_id)
        if cluster:
            cluster.last_seen_at = datetime.now(timezone.utc)
            cluster.status = "active"
            await self.session.commit()
            await self.session.refresh(cluster)
        return cluster
