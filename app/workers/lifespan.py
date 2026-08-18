import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.discovery.watcher import DiscoveryWatcher
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)

# Global watcher instance
watcher = DiscoveryWatcher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup phase
    setup_logging()
    logger.info("Initializing AIVAR application components...")
    
    # Start Kubernetes Watcher background task
    await watcher.start()
    
    yield
    
    # 2. Shutdown phase
    logger.info("Shutting down AIVAR application components...")
    await watcher.stop()
