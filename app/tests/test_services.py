import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.services.asset import AssetService
from app.schemas.discovery import DiscoveryMessage
from app.models.asset import Asset
from app.models.cluster import Cluster


@pytest.mark.asyncio
async def test_asset_service_unassigned_owner_alert():
    # Setup mock db session
    session = AsyncMock()
    
    # Create service instance
    service = AssetService(session)
    
    # Mock repositories
    service.cluster_repo = AsyncMock()
    service.asset_repo = AsyncMock()
    service.event_repo = AsyncMock()
    service.alert_repo = AsyncMock()
    
    cluster_id = uuid.uuid4()
    service.cluster_repo.get_by_name.return_value = MagicMock(id=cluster_id)
    service.asset_repo.get_by_cluster_workload.return_value = None
    
    # Create mock Asset to be returned by create
    mock_asset = Asset(
        id=uuid.uuid4(),
        cluster_id=cluster_id,
        workload_uid="uid-123",
        asset_name="unassigned-llm",
        asset_type="model",
        namespace="default",
        workload_kind="Deployment",
        workload_name="unassigned-llm",
        owner="unassigned",
        owner_source="default",
        risk_tier="low"
    )
    service.asset_repo.create.return_value = mock_asset
    
    # Discovery Message for an AI workload without owner
    msg = DiscoveryMessage(
        cluster_name="test-cluster",
        workload_uid="uid-123",
        workload_kind="Deployment",
        workload_name="unassigned-llm",
        namespace="default",
        labels={"aivar.io/asset-type": "model"} # explicit type to pass detect
    )
    
    # Process message
    asset = await service.process_discovery_message(msg)
    
    # Check asset created
    assert asset is not None
    assert asset.owner == "unassigned"
    
    # Verify alert creation was called
    service.alert_repo.create.assert_called_once()
    alert_arg = service.alert_repo.create.call_args[0][0]
    assert alert_arg.type == "unassigned_owner"
    assert alert_arg.asset_id == mock_asset.id
