import uuid
from typing import List, Optional, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.cluster import Cluster
from app.schemas.cluster import ClusterCreate, ClusterUpdate


class ClusterRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, cluster_id: uuid.UUID) -> Optional[Cluster]:
        result = await self.session.execute(select(Cluster).where(Cluster.id == cluster_id))
        return result.scalars().first()

    async def get_by_name(self, name: str) -> Optional[Cluster]:
        result = await self.session.execute(select(Cluster).where(Cluster.name == name))
        return result.scalars().first()

    async def list_all(self, username: Optional[str] = None) -> List[Cluster]:
        stmt = select(Cluster)
        if username:
            from sqlalchemy import or_
            stmt = stmt.where(or_(Cluster.created_by == username, Cluster.created_by == None))
        result = await self.session.execute(stmt.order_by(Cluster.created_at.desc()))
        return list(result.scalars().all())

    async def list_enabled_watchers(self) -> List[Cluster]:
        result = await self.session.execute(select(Cluster).where(Cluster.watch_enabled == True))
        return list(result.scalars().all())

    async def create(self, schema: ClusterCreate) -> Cluster:
        # Default watch_enabled to True for instant activation via Web UI registration.
        # Fallback kube_context to name if not provided.
        kube_context = schema.kube_context or (schema.name if schema.connection_type == "kubeconfig" else None)
        
        cluster = Cluster(
            name=schema.name,
            environment=schema.environment,
            api_server=schema.api_server,
            connection_type=schema.connection_type.value if hasattr(schema.connection_type, 'value') else schema.connection_type,
            kube_context=kube_context,
            aws_region=schema.aws_region,
            eks_cluster_name=schema.eks_cluster_name,
            watch_enabled=True,
            credential_reference=schema.credential_reference,
            aws_access_key_id=schema.aws_access_key_id,
            aws_secret_access_key=schema.aws_secret_access_key,
            created_by=schema.created_by,
            status="active",
            connection_status="disabled"
        )
        self.session.add(cluster)
        await self.session.commit()
        await self.session.refresh(cluster)
        return cluster

    async def update(self, cluster: Cluster, schema: ClusterUpdate) -> Cluster:
        update_data = schema.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                if key in ("connection_type", "connection_status") and hasattr(value, 'value'):
                    setattr(cluster, key, value.value)
                else:
                    setattr(cluster, key, value)
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

    async def update_connection_status(
        self, cluster_id: uuid.UUID, connection_status: str, last_error: Optional[str] = None
    ) -> Optional[Cluster]:
        cluster = await self.get_by_id(cluster_id)
        if cluster:
            cluster.connection_status = connection_status
            cluster.last_error = last_error
            if connection_status == "connected":
                cluster.last_sync_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(cluster)
        return cluster
