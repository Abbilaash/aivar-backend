import pytest
from app.discovery.detector import AIDetector
from app.schemas.discovery import DiscoveryMessage, ContainerInfo
from app.schemas.enums import AssetType, RiskTier


def test_ai_detector_explicit_label():
    msg = DiscoveryMessage(
        cluster_name="test-cluster",
        workload_uid="uid-1",
        workload_kind="Deployment",
        workload_name="some-app",
        namespace="default",
        labels={"aivar.io/asset-type": "agent"},
        annotations={}
    )
    is_ai, asset_type, confidence, evidence = AIDetector.detect(msg)
    assert is_ai is True
    assert asset_type == AssetType.AGENT
    assert confidence == 1.0
    assert "Explicit detection label" in evidence[0]


def test_ai_detector_keywords():
    msg = DiscoveryMessage(
        cluster_name="test-cluster",
        workload_uid="uid-2",
        workload_kind="Deployment",
        workload_name="openai-integration-service",
        namespace="default",
        labels={},
        annotations={},
        containers=[
            ContainerInfo(
                name="app",
                image="python:3.12-slim",
                env={"OPENAI_API_KEY": "[PRESENT]"}
            )
        ]
    )
    is_ai, asset_type, confidence, evidence = AIDetector.detect(msg)
    assert is_ai is True
    assert asset_type == AssetType.MODEL
    assert confidence >= 0.7
    assert len(evidence) >= 2


def test_owner_inference():
    # Precedence 1: Annotation
    msg1 = DiscoveryMessage(
        cluster_name="test-cluster",
        workload_uid="uid-3",
        workload_kind="Deployment",
        workload_name="ai-service",
        namespace="marketing-team",
        labels={"owner": "sales-team"},
        annotations={"aivar.io/owner": "billing-team"},
        service_account_name="admin-sa"
    )
    owner, source = AIDetector.infer_owner(msg1)
    assert owner == "billing-team"
    assert source == "annotation:aivar.io/owner"

    # Precedence 2: Labels
    msg2 = DiscoveryMessage(
        cluster_name="test-cluster",
        workload_uid="uid-3",
        workload_kind="Deployment",
        workload_name="ai-service",
        namespace="marketing-team",
        labels={"owner": "sales-team"},
        annotations={},
        service_account_name="admin-sa"
    )
    owner, source = AIDetector.infer_owner(msg2)
    assert owner == "sales-team"
    assert source == "label:owner"

    # Precedence 3: Namespace
    msg3 = DiscoveryMessage(
        cluster_name="test-cluster",
        workload_uid="uid-3",
        workload_kind="Deployment",
        workload_name="ai-service",
        namespace="marketing-team",
        labels={},
        annotations={},
        service_account_name="admin-sa"
    )
    owner, source = AIDetector.infer_owner(msg3)
    assert owner == "marketing-team"
    assert source == "namespace"


def test_risk_scoring():
    # Low Risk
    msg_low = DiscoveryMessage(
        cluster_name="test-cluster",
        workload_uid="uid-4",
        workload_kind="Deployment",
        workload_name="ai-model",
        namespace="default"
    )
    tier, reasons = AIDetector.calculate_risk(msg_low)
    assert tier == RiskTier.LOW
    assert len(reasons) == 1

    # Medium Risk (ConfigMaps/Secrets)
    msg_med = DiscoveryMessage(
        cluster_name="test-cluster",
        workload_uid="uid-5",
        workload_kind="Deployment",
        workload_name="ai-model",
        namespace="default",
        secret_references=["some-db-url"]
    )
    tier, reasons = AIDetector.calculate_risk(msg_med)
    assert tier == RiskTier.MEDIUM

    # High Risk
    msg_high = DiscoveryMessage(
        cluster_name="test-cluster",
        workload_uid="uid-6",
        workload_kind="Deployment",
        workload_name="ai-model",
        namespace="default",
        secret_references=["pii-encryption-key"],
        containers=[
            ContainerInfo(
                name="c1",
                image="vllm",
                env={"AWS_SECRET_ACCESS_KEY": "[PRESENT]"}
            )
        ]
    )
    tier, reasons = AIDetector.calculate_risk(msg_high)
    assert tier == RiskTier.HIGH
