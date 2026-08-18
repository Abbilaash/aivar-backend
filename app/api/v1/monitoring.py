from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

from app.db.session import get_db_session
from app.workers.lifespan import watcher

router = APIRouter(tags=["monitoring"])

# Simple Prometheus Counters
DISCOVERY_PROCESSED_TOTAL = Counter(
    "aivar_discovery_processed_total",
    "Total number of K8s workload discovery messages processed",
    ["status"]
)


@router.get("/healthz", summary="Health check endpoint")
async def healthz():
    """
    Basic health check verifying the application container is running.
    """
    return {"status": "healthy", "service": "aivar-backend"}


@router.get("/readyz", summary="Readiness check endpoint")
async def readyz(db: AsyncSession = Depends(get_db_session)):
    """
    Readiness check verifying database connectivity and watcher configuration status.
    """
    # Test DB
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        return Response(
            content=f"Database connection failed: {e}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    return {
        "status": "ready",
        "database": "connected",
        "kubernetes_watcher_enabled": watcher.k8s_configured
    }


@router.get("/metrics", response_class=PlainTextResponse, summary="Prometheus metrics")
def metrics():
    """
    Exposes application metrics in Prometheus format.
    """
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
