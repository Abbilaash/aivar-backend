from enum import Enum


class AssetType(str, Enum):
    MODEL = "model"
    AGENT = "agent"
    TOOL = "tool"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AssetStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class DiscoveryEventType(str, Enum):
    DISCOVERED = "discovered"
    UPDATED = "updated"
    RISK_CHANGED = "risk_changed"
    OWNER_CHANGED = "owner_changed"
    DEACTIVATED = "deactivated"


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
