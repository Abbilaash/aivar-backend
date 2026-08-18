import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.discovery import DiscoveryMessage
from app.schemas.enums import DiscoveryEventType, AssetStatus, RiskTier, AlertSeverity
from app.schemas.asset import AssetCreate, AssetUpdate
from app.schemas.discovery_event import DiscoveryEventCreate
from app.schemas.alert import AlertCreate
from app.repositories.cluster import ClusterRepository
from app.repositories.asset import AssetRepository
from app.repositories.discovery_event import DiscoveryEventRepository
from app.repositories.alert import AlertRepository
from app.discovery.detector import AIDetector
from app.models.asset import Asset
from app.schemas.cluster import ClusterCreate
import logging

logger = logging.getLogger(__name__)


class AssetService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.cluster_repo = ClusterRepository(session)
        self.asset_repo = AssetRepository(session)
        self.event_repo = DiscoveryEventRepository(session)
        self.alert_repo = AlertRepository(session)

    async def get_or_create_cluster(self, cluster_name: str) -> uuid.UUID:
        cluster = await self.cluster_repo.get_by_name(cluster_name)
        if not cluster:
            # Create a default registration for the cluster
            from app.core.config import settings
            schema = ClusterCreate(
                name=cluster_name,
                environment=settings.CLUSTER_ENVIRONMENT,
                api_server="in-cluster" if settings.WATCHER_ENABLED else "external-registry"
            )
            cluster = await self.cluster_repo.create(schema)
        else:
            await self.cluster_repo.update_last_seen(cluster.id)
        return cluster.id

    async def process_discovery_message(self, msg: DiscoveryMessage) -> Optional[Asset]:
        """
        Receives normalized DiscoveryMessage, runs detector, updates/creates asset,
        logs discovery events, and creates unassigned alerts.
        """
        cluster_id = await self.get_or_create_cluster(msg.cluster_name)
        
        is_ai, asset_type, confidence, evidence = AIDetector.detect(msg)
        if not is_ai:
            # If the workload was previously tracked, we might want to deactivate it
            existing = await self.asset_repo.get_by_cluster_workload(cluster_id, msg.workload_uid)
            if existing and existing.status == "active":
                await self.deactivate_asset(cluster_id, msg.workload_uid)
            return None

        # Determine attributes
        owner, owner_source = AIDetector.infer_owner(msg)
        risk_tier, risk_reasons = AIDetector.calculate_risk(msg)

        existing = await self.asset_repo.get_by_cluster_workload(cluster_id, msg.workload_uid)
        
        if existing:
            # Build before/after snapshots for audit trail
            before_snapshot = self._build_snapshot(existing)
            
            # Update the asset
            update_schema = AssetUpdate(
                asset_name=msg.workload_name,
                asset_type=asset_type,
                namespace=msg.namespace,
                image_references=msg.image_references,
                owner=owner,
                owner_source=owner_source,
                risk_tier=risk_tier,
                risk_reasons=risk_reasons,
                detection_confidence=confidence,
                detection_evidence=evidence,
                status=AssetStatus.ACTIVE,
                last_active_at=datetime.now(timezone.utc)
            )
            
            updated_asset = await self.asset_repo.update(existing, update_schema)
            after_snapshot = self._build_snapshot(updated_asset)

            # Check what changed to emit the right event types
            event_types = []
            if before_snapshot.get("status") == "inactive":
                event_types.append(DiscoveryEventType.UPDATED) # reactivated
            if before_snapshot.get("risk_tier") != risk_tier.value:
                event_types.append(DiscoveryEventType.RISK_CHANGED)
            if before_snapshot.get("owner") != owner:
                event_types.append(DiscoveryEventType.OWNER_CHANGED)
            
            if not event_types:
                # If there are metadata updates
                if before_snapshot != after_snapshot:
                    event_types.append(DiscoveryEventType.UPDATED)

            for et in event_types:
                await self.event_repo.create(DiscoveryEventCreate(
                    asset_id=updated_asset.id,
                    event_type=et,
                    before_snapshot=before_snapshot,
                    after_snapshot=after_snapshot
                ))

            # Handle Alerts for existing assets:
            # If the owner became unassigned (changed from an owner to unassigned), raise alert
            if owner == "unassigned" and before_snapshot.get("owner") != "unassigned":
                await self._trigger_unassigned_owner_alert(updated_asset)
                
            return updated_asset

        else:
            # Create new Asset
            create_schema = AssetCreate(
                cluster_id=cluster_id,
                workload_uid=msg.workload_uid,
                asset_name=msg.workload_name,
                asset_type=asset_type,
                namespace=msg.namespace,
                workload_kind=msg.workload_kind,
                workload_name=msg.workload_name,
                image_references=msg.image_references,
                owner=owner,
                owner_source=owner_source,
                risk_tier=risk_tier,
                risk_reasons=risk_reasons,
                detection_confidence=confidence,
                detection_evidence=evidence
            )
            
            new_asset = await self.asset_repo.create(create_schema)
            after_snapshot = self._build_snapshot(new_asset)

            # Create DiscoveryEvent
            await self.event_repo.create(DiscoveryEventCreate(
                asset_id=new_asset.id,
                event_type=DiscoveryEventType.DISCOVERED,
                before_snapshot=None,
                after_snapshot=after_snapshot
            ))

            # Check if owner is unassigned to trigger alert
            if owner == "unassigned":
                await self._trigger_unassigned_owner_alert(new_asset)

            return new_asset

    async def deactivate_asset(self, cluster_id: uuid.UUID, workload_uid: str) -> None:
        """
        Deactivates an asset when deleted or no longer containing AI components.
        """
        asset = await self.asset_repo.get_by_cluster_workload(cluster_id, workload_uid)
        if asset and asset.status == "active":
            before_snapshot = self._build_snapshot(asset)
            update_schema = AssetUpdate(status=AssetStatus.INACTIVE)
            updated_asset = await self.asset_repo.update(asset, update_schema)
            after_snapshot = self._build_snapshot(updated_asset)

            await self.event_repo.create(DiscoveryEventCreate(
                asset_id=updated_asset.id,
                event_type=DiscoveryEventType.DEACTIVATED,
                before_snapshot=before_snapshot,
                after_snapshot=after_snapshot
            ))

    async def _trigger_unassigned_owner_alert(self, asset: Asset) -> None:
        """
        Automatically creates a high-severity unassigned_owner alert.
        """
        # Ensure we don't open duplicate alerts for the same asset
        existing_alert = await self.alert_repo.get_open_alert_by_type(asset.id, "unassigned_owner")
        if not existing_alert:
            alert_schema = AlertCreate(
                asset_id=asset.id,
                severity=AlertSeverity.HIGH,
                type="unassigned_owner",
                title=f"AI Asset without owner: {asset.asset_name}",
                message=(
                    f"Asset '{asset.asset_name}' ({asset.asset_type}) in namespace '{asset.namespace}' "
                    f"was discovered without an assigned owner. Risk tier: {asset.risk_tier}."
                )
            )
            await self.alert_repo.create(alert_schema)

    def _build_snapshot(self, asset: Asset) -> Dict[str, Any]:
        return {
            "id": str(asset.id),
            "cluster_id": str(asset.cluster_id),
            "workload_uid": asset.workload_uid,
            "asset_name": asset.asset_name,
            "asset_type": asset.asset_type,
            "namespace": asset.namespace,
            "workload_kind": asset.workload_kind,
            "workload_name": asset.workload_name,
            "image_references": asset.image_references,
            "owner": asset.owner,
            "owner_source": asset.owner_source,
            "risk_tier": asset.risk_tier,
            "risk_reasons": asset.risk_reasons,
            "detection_confidence": asset.detection_confidence,
            "detection_evidence": asset.detection_evidence,
            "status": asset.status,
            "last_active_at": asset.last_active_at.isoformat() if asset.last_active_at else None
        }
