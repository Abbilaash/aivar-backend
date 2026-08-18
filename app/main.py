import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.workers.lifespan import lifespan
from app.api.v1.assets import router as assets_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.clusters import router as clusters_router
from app.api.v1.changes import router as changes_router
from app.api.v1.monitoring import router as monitoring_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AIVAR — Autonomous AI Asset Registry",
    version="1.0.0",
    description="A centralized system for detecting, registering, and monitoring AI workloads on Kubernetes.",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routes
# Resource routes under /api/v1
app.include_router(assets_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(clusters_router, prefix="/api/v1")
app.include_router(changes_router, prefix="/api/v1")

# Monitoring routes mounted directly at root
app.include_router(monitoring_router)


# Centralized Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception in request {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred. Please contact system administrator."
        }
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning(f"Value error in request {request.method} {request.url}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "ValidationError",
            "message": str(exc)
        }
    )
