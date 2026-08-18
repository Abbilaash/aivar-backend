from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """
    SQLAlchemy declarative Base class for all database tables.
    """
    pass

# Import models so they register on Base.metadata
from app.models.cluster import Cluster
from app.models.asset import Asset
from app.models.discovery_event import DiscoveryEvent
from app.models.alert import Alert

__all__ = ["Base", "Cluster", "Asset", "DiscoveryEvent", "Alert"]
