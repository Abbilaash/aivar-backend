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

    async def list_filtered(
        self,
        cluster_id: Optional[uuid.UUID] = None,
        namespace: Optional[str] = None,
        asset_type: Optional[str] = None,
        risk_tier: Optional[str] = None,
        owner: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Asset], int]:
        stmt = select(Asset)
        
        # Apply filters
        filters = []
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
            status="active"
        )
        self.session.add(asset)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

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

    async def list_recent_changes(self, since: datetime) -> List[Asset]:
        stmt = select(Asset).where(Asset.updated_at >= since).order_by(Asset.updated_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
