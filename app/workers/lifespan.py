import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.discovery.manager import watch_manager
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup phase
    setup_logging()
    logger.info("Initializing AIVAR application components...")
    
    # Start database-driven, multi-cluster Kubernetes watch orchestration.
    await watch_manager.start()
    
    yield
    
    # 2. Shutdown phase
    logger.info("Shutting down AIVAR application components...")
    await watch_manager.stop()
