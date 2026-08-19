import uuid
from typing import List, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.asset import Asset
from app.schemas.asset import AssetCreate, AssetUpdate


class AssetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, asset_id: uuid.UUID) -> Optional[Asset]:
        result = await self.session.execute(select(Asset).where(Asset.id == asset_id))
        return result.scalars().first()

    async def get_by_cluster_workload(self, cluster_id: uuid.UUID, workload_uid: str) -> Optional[Asset]:
        stmt = select(Asset).where(and_(Asset.cluster_id == cluster_id, Asset.workload_uid == workload_uid))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_name_kind_namespace(
        self, cluster_id: uuid.UUID, name: str, kind: str, namespace: str
    ) -> Optional[Asset]:
        stmt = select(Asset).where(
            and_(
                Asset.cluster_id == cluster_id,
                Asset.workload_name == name,
                Asset.workload_kind == kind,
                Asset.namespace == namespace
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()


    async def list_filtered(
        self,
        cluster_id: Optional[uuid.UUID] = None,
        namespace: Optional[str] = None,
        asset_type: Optional[str] = None,
        risk_tier: Optional[str] = None,
        owner: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        updated_after: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
        username: Optional[str] = None
    ) -> Tuple[List[Asset], int]:
        from app.models.cluster import Cluster
        stmt = select(Asset)
        
        # Apply filters
        filters = []
        if username:
            stmt = stmt.join(Cluster)
            filters.append(or_(Cluster.created_by == username, Cluster.created_by == None))
        if cluster_id is not None:
            filters.append(Asset.cluster_id == cluster_id)
        if namespace is not None:
            filters.append(Asset.namespace == namespace)
        if asset_type is not None:
            filters.append(Asset.asset_type == asset_type)
        if risk_tier is not None:
            filters.append(Asset.risk_tier == risk_tier)
        if owner is not None:
            filters.append(Asset.owner == owner)
        if status is not None:
            filters.append(Asset.status == status)
        if updated_after is not None:
            filters.append(Asset.updated_at >= updated_after)

            
        if search:
            search_clause = or_(
                Asset.asset_name.ilike(f"%{search}%"),
                Asset.workload_name.ilike(f"%{search}%"),
                Asset.owner.ilike(f"%{search}%")
            )
            filters.append(search_clause)

        if filters:
            stmt = stmt.where(and_(*filters))

        # Get count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar_one()

        # Get elements
        stmt = stmt.order_by(Asset.updated_at.desc()).offset(skip).limit(limit)
        results = await self.session.execute(stmt)
        return list(results.scalars().all()), total_count

    async def create(self, schema: AssetCreate) -> Asset:
        from sqlalchemy.exc import IntegrityError
        asset = Asset(
            cluster_id=schema.cluster_id,
            workload_uid=schema.workload_uid,
            asset_name=schema.asset_name,
            asset_type=schema.asset_type.value if hasattr(schema.asset_type, 'value') else schema.asset_type,
            namespace=schema.namespace,
            workload_kind=schema.workload_kind,
            workload_name=schema.workload_name,
            image_references=schema.image_references,
            owner=schema.owner,
            owner_source=schema.owner_source,
            risk_tier=schema.risk_tier.value if hasattr(schema.risk_tier, 'value') else schema.risk_tier,
            risk_reasons=schema.risk_reasons,
            detection_confidence=schema.detection_confidence,
            detection_evidence=schema.detection_evidence,
            status=schema.status.value if (schema.status and hasattr(schema.status, 'value')) else (schema.status or "active"),
            last_active_at=schema.last_active_at or datetime.now(timezone.utc)
        )

        try:
            self.session.add(asset)
            await self.session.commit()
            await self.session.refresh(asset)
            return asset
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get_by_cluster_workload(schema.cluster_id, schema.workload_uid)
            if existing:
                update_schema = AssetUpdate(
                    asset_name=schema.asset_name,
                    asset_type=schema.asset_type,
                    namespace=schema.namespace,
                    image_references=schema.image_references,
                    owner=schema.owner,
                    owner_source=schema.owner_source,
                    risk_tier=schema.risk_tier,
                    risk_reasons=schema.risk_reasons,
                    detection_confidence=schema.detection_confidence,
                    detection_evidence=schema.detection_evidence,
                    status=schema.status if (schema.status and hasattr(schema.status, 'value')) else (schema.status or "active"),
                    last_active_at=schema.last_active_at or datetime.now(timezone.utc)
                )
                return await self.update(existing, update_schema)
            raise

    async def upsert(self, schema: AssetCreate) -> Asset:
        from sqlalchemy.dialects.postgresql import insert
        
        insert_stmt = insert(Asset).values(
            id=uuid.uuid4(),
            cluster_id=schema.cluster_id,
            workload_uid=schema.workload_uid,
            asset_name=schema.asset_name,
            asset_type=schema.asset_type.value if hasattr(schema.asset_type, 'value') else schema.asset_type,
            namespace=schema.namespace,
            workload_kind=schema.workload_kind,
            workload_name=schema.workload_name,
            image_references=schema.image_references,
            owner=schema.owner,
            owner_source=schema.owner_source,
            risk_tier=schema.risk_tier.value if hasattr(schema.risk_tier, 'value') else schema.risk_tier,
            risk_reasons=schema.risk_reasons,
            detection_confidence=schema.detection_confidence,
            detection_evidence=schema.detection_evidence,
            status=schema.status.value if (schema.status and hasattr(schema.status, 'value')) else (schema.status or "active"),
            last_active_at=schema.last_active_at or datetime.now(timezone.utc)
        )
        
        update_cols = {
            'asset_name': insert_stmt.excluded.asset_name,
            'asset_type': insert_stmt.excluded.asset_type,
            'namespace': insert_stmt.excluded.namespace,
            'image_references': insert_stmt.excluded.image_references,
            'owner': insert_stmt.excluded.owner,
            'owner_source': insert_stmt.excluded.owner_source,
            'risk_tier': insert_stmt.excluded.risk_tier,
            'risk_reasons': insert_stmt.excluded.risk_reasons,
            'detection_confidence': insert_stmt.excluded.detection_confidence,
            'detection_evidence': insert_stmt.excluded.detection_evidence,
            'status': insert_stmt.excluded.status,
            'last_active_at': insert_stmt.excluded.last_active_at,
            'updated_at': datetime.now(timezone.utc)
        }
        
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=['cluster_id', 'workload_uid'],
            set_=update_cols
        ).returning(Asset)
        
        result = await self.session.execute(upsert_stmt)
        await self.session.commit()
        return result.scalars().first()

    async def update(self, asset: Asset, schema: AssetUpdate) -> Asset:
        update_data = schema.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                if key in ("asset_type", "risk_tier", "status") and hasattr(value, 'value'):
                    setattr(asset, key, value.value)
                else:
                    setattr(asset, key, value)
        
        asset.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

    async def list_recent_changes(self, since: datetime, username: Optional[str] = None) -> List[Asset]:
        stmt = select(Asset).where(Asset.updated_at >= since)
        if username:
            from app.models.cluster import Cluster
            stmt = stmt.join(Cluster).where(or_(Cluster.created_by == username, Cluster.created_by == None))
        result = await self.session.execute(stmt.order_by(Asset.updated_at.desc()))
        return list(result.scalars().all())
