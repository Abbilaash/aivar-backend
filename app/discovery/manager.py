import asyncio
import logging
import uuid
from typing import Dict, List, Optional
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.cluster import Cluster
from app.repositories.cluster import ClusterRepository
from app.discovery.watcher import DiscoveryWatcher

logger = logging.getLogger(__name__)


class ClusterWatchManager:
    _instance: Optional['ClusterWatchManager'] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ClusterWatchManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self.watchers: Dict[uuid.UUID, DiscoveryWatcher] = {}
        self.manager_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """
        Starts the background orchestration sync task.
        """
        if self._running:
            return
        self._running = True
        logger.info("Initializing ClusterWatchManager daemon...")
        self.manager_task = asyncio.create_task(self._management_loop())

    async def stop(self):
        """
        Gracefully terminates all active watchers and the orchestration loop.
        """
        logger.info("Shutting down ClusterWatchManager and all active watchers...")
        self._running = False
        if self.manager_task:
            self.manager_task.cancel()
            try:
                await self.manager_task
            except asyncio.CancelledError:
                pass
            self.manager_task = None

        # Stop all watchers
        active_ids = list(self.watchers.keys())
        for cid in active_ids:
            await self.stop_watcher(cid)
        logger.info("ClusterWatchManager shutdown complete.")

    async def trigger_reloading(self):
        """
        Manually triggers a full synchronization scan across database clusters.
        """
        logger.info("Manual reload triggered for ClusterWatchManager.")
        await self._sync_watchers()

    async def _management_loop(self):
        """
        Periodic orchestration loop running every 30 seconds.
        """
        while self._running:
            try:
                await self._sync_watchers()
            except Exception as e:
                logger.error(f"Error in ClusterWatchManager sync loop: {e}", exc_info=True)
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break

    async def _sync_watchers(self):
        """
        Queries enabled clusters in the database, starts new watchers, stops disabled ones.
        """
        async with AsyncSessionLocal() as session:
            repo = ClusterRepository(session)
            db_clusters = await repo.list_enabled_watchers()
            
            db_cluster_ids = {c.id for c in db_clusters}
            active_watcher_ids = set(self.watchers.keys())

            # 1. Stop watchers that are no longer enabled/present in DB
            for cid in active_watcher_ids - db_cluster_ids:
                logger.info(f"Cluster '{cid}' watch disabled or removed. Stopping watcher...")
                await self.stop_watcher(cid)
                await repo.update_connection_status(cid, "disabled")

            # 2. Start or update watchers
            for cluster in db_clusters:
                cid = cluster.id
                if cid not in self.watchers:
                    logger.info(f"Cluster '{cluster.name}' watch enabled. Initializing watcher...")
                    await self.start_watcher(cluster, repo)
                else:
                    # Check if connection parameters changed
                    watcher = self.watchers[cid]
                    if (watcher.cluster.connection_type != cluster.connection_type or
                        watcher.cluster.kube_context != cluster.kube_context or
                        watcher.cluster.aws_region != cluster.aws_region or
                        watcher.cluster.eks_cluster_name != cluster.eks_cluster_name or
                        watcher.cluster.api_server != cluster.api_server):
                        
                        logger.info(f"Configuration update detected for cluster '{cluster.name}'. Restarting watcher...")
                        await self.stop_watcher(cid)
                        await self.start_watcher(cluster, repo)

    async def start_watcher(self, cluster: Cluster, repo: ClusterRepository):
        cid = cluster.id
        watcher = DiscoveryWatcher(cluster)
        
        # Update status to connecting in DB
        await repo.update_connection_status(cid, "connecting")
        
        try:
            initialized = watcher.initialize_client()
            if not initialized:
                raise ConnectionError("Kubernetes client initialization failed.")
                
            # Start loop
            watcher.start_loops(asyncio.get_running_loop())
            self.watchers[cid] = watcher
            
            # Update status to connected in DB
            await repo.update_connection_status(cid, "connected")
            logger.info(f"Watcher for cluster '{cluster.name}' successfully connected and started.")
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Failed to start watcher for cluster '{cluster.name}': {err_msg}")
            await repo.update_connection_status(cid, "error", last_error=err_msg)

    async def stop_watcher(self, cid: uuid.UUID):
        if cid in self.watchers:
            watcher = self.watchers[cid]
            await watcher.stop()
            del self.watchers[cid]
            logger.info(f"Watcher for cluster ID '{cid}' stopped.")


# Global instance
watch_manager = ClusterWatchManager()
