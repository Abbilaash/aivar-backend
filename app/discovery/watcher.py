import asyncio
import logging
import traceback
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.discovery import DiscoveryMessage, ContainerInfo
from app.db.session import AsyncSessionLocal
from app.services.asset import AssetService

logger = logging.getLogger(__name__)


class DiscoveryWatcher:
    def __init__(self):
        self.k8s_configured = False
        self.apps_v1 = None
        self.batch_v1 = None
        self.core_v1 = None
        self.tasks: List[asyncio.Task] = []
        self._running = False

    def initialize_client(self) -> bool:
        """
        Attempts to initialize Kubernetes client using in-cluster config first,
        falling back to local kubeconfig, and finally logging a warning if neither works.
        """
        if self.k8s_configured:
            return True

        try:
            config.load_in_cluster_config()
            logger.info("Successfully loaded in-cluster Kubernetes configuration.")
            self.k8s_configured = True
        except config.config_exception.ConfigException:
            try:
                config.load_kube_config()
                logger.info("Successfully loaded local kubeconfig fallback configuration.")
                self.k8s_configured = True
            except Exception as e:
                logger.warning(
                    f"Kubernetes client configuration failed: {e}. "
                    "Watcher will not start. Remote ingestion API remains active."
                )
                self.k8s_configured = False
                return False

        if self.k8s_configured:
            self.apps_v1 = client.AppsV1Api()
            self.batch_v1 = client.BatchV1Api()
            self.core_v1 = client.CoreV1Api()
            return True
        return False

    async def start(self):
        """
        Starts the watcher background loops.
        """
        if not settings.WATCHER_ENABLED:
            logger.info("Kubernetes Watcher is disabled by configuration (WATCHER_ENABLED=false).")
            return

        if not self.initialize_client():
            return

        self._running = True
        logger.info("Starting AIVAR Kubernetes Discovery Watcher loops...")
        
        # Start watching resources in the background
        self.tasks.append(asyncio.create_task(self._watch_loop("Deployment")))
        self.tasks.append(asyncio.create_task(self._watch_loop("StatefulSet")))
        self.tasks.append(asyncio.create_task(self._watch_loop("Job")))
        self.tasks.append(asyncio.create_task(self._watch_loop("CronJob")))
        
        # Start periodic reconciliation loop
        self.tasks.append(asyncio.create_task(self._reconciliation_loop()))

    async def stop(self):
        """
        Stops the watcher tasks and cleans up.
        """
        logger.info("Stopping Kubernetes Discovery Watcher tasks...")
        self._running = False
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        logger.info("Kubernetes Discovery Watcher tasks stopped.")

    async def _reconciliation_loop(self):
        """
        Periodically performs a full sync of all workloads.
        """
        while self._running:
            try:
                logger.info("Starting periodic full cluster reconciliation scan...")
                await self.reconcile_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error during periodic cluster reconciliation: {e}", exc_info=True)
            
            await asyncio.sleep(settings.RECONCILIATION_INTERVAL_SECS)

    async def reconcile_all(self):
        """
        Queries all workloads across all namespaces and processes them.
        """
        if not self.k8s_configured:
            return

        # Fetch all deployments
        deployments = self.apps_v1.list_deployment_for_all_namespaces()
        for dep in deployments.items:
            await self._process_resource(dep, "Deployment", "ADDED")

        # Fetch statefulsets
        statefulsets = self.apps_v1.list_stateful_set_for_all_namespaces()
        for ss in statefulsets.items:
            await self._process_resource(ss, "StatefulSet", "ADDED")

        # Fetch jobs
        jobs = self.batch_v1.list_job_for_all_namespaces()
        for job in jobs.items:
            await self._process_resource(job, "Job", "ADDED")

        # Fetch cronjobs
        cronjobs = self.batch_v1.list_cron_job_for_all_namespaces()
        for cj in cronjobs.items:
            await self._process_resource(cj, "CronJob", "ADDED")

    async def _watch_loop(self, resource_kind: str):
        """
        Watches resource events using exponential backoff on failure/expiration.
        """
        delay = settings.WATCHER_RETRY_DELAY_SECS
        w = watch.Watch()

        while self._running:
            try:
                logger.info(f"Starting Watch stream for K8s resource: {resource_kind}...")
                
                # Get the watch function
                if resource_kind == "Deployment":
                    func = self.apps_v1.list_deployment_for_all_namespaces
                elif resource_kind == "StatefulSet":
                    func = self.apps_v1.list_stateful_set_for_all_namespaces
                elif resource_kind == "Job":
                    func = self.batch_v1.list_job_for_all_namespaces
                elif resource_kind == "CronJob":
                    func = self.batch_v1.list_cron_job_for_all_namespaces
                else:
                    logger.error(f"Unknown watch resource kind: {resource_kind}")
                    return

                # Read events from stream. timeout_seconds=0 blocks until closed or expired.
                # Use a periodic timeout to let watch reconnect and check if self._running is false
                for event in w.stream(func, timeout_seconds=60):
                    if not self._running:
                        break
                    
                    obj = event['object']
                    event_type = event['type']  # ADDED, MODIFIED, DELETED
                    
                    await self._process_resource(obj, resource_kind, event_type)
                    
                    # Reset backoff on successful event receipt
                    delay = settings.WATCHER_RETRY_DELAY_SECS

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Watch stream for {resource_kind}: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
                delay = min(settings.WATCHER_MAX_RETRY_DELAY_SECS, delay * 2)

    async def _process_resource(self, obj: Any, kind: str, event_type: str):
        """
        Parses K8s resource object, extracts metadata safely, and triggers asset service.
        """
        try:
            metadata = obj.metadata
            uid = metadata.uid
            name = metadata.name
            namespace = metadata.namespace
            labels = metadata.labels or {}
            annotations = metadata.annotations or {}
            
            # Map containers, images, configmaps, secrets, volumes safely
            containers_info: List[ContainerInfo] = []
            image_references = []
            secret_references = []
            configmap_references = []
            service_account_name = None

            # Drill down based on resource schema
            spec = getattr(obj, "spec", None)
            if spec:
                # If Job or CronJob or Deployment/StatefulSet
                template = getattr(spec, "template", None)
                job_spec = None
                
                if kind == "CronJob":
                    job_template = getattr(spec, "job_template", None)
                    if job_template:
                        job_spec = getattr(job_template, "spec", None)
                elif kind == "Job":
                    template = spec
                
                # If CronJob had job template -> resolve templates spec
                if job_spec:
                    template = getattr(job_spec, "template", None)

                if template:
                    pod_spec = getattr(template, "spec", None)
                    if pod_spec:
                        service_account_name = getattr(pod_spec, "service_account_name", None)
                        
                        # Inspect volumes for Secrets and ConfigMaps references
                        volumes = getattr(pod_spec, "volumes", None) or []
                        for vol in volumes:
                            if getattr(vol, "secret", None):
                                secret_references.append(vol.secret.secret_name)
                            if getattr(vol, "config_map", None):
                                configmap_references.append(vol.config_map.name)

                        # Inspect containers
                        containers = getattr(pod_spec, "containers", None) or []
                        for container in containers:
                            # Extract env variables safely (excluding values)
                            env_dict = {}
                            env = getattr(container, "env", None) or []
                            for e in env:
                                name_env = getattr(e, "name", None)
                                if name_env:
                                    # Never store or log the secret value, only record presence
                                    env_dict[name_env] = "[PRESENT]"

                            # Extract volume mounts
                            vol_mounts = []
                            mounts = getattr(container, "volume_mounts", None) or []
                            for m in mounts:
                                vol_mounts.append(m.name)

                            containers_info.append(ContainerInfo(
                                name=container.name,
                                image=container.image,
                                env=env_dict,
                                command=list(getattr(container, "command", None) or []),
                                args=list(getattr(container, "args", None) or []),
                                volume_mounts=vol_mounts
                            ))
                            image_references.append(container.image)

            # Build Normalized message
            msg = DiscoveryMessage(
                cluster_name=settings.CLUSTER_NAME,
                workload_uid=uid,
                workload_kind=kind,
                workload_name=name,
                namespace=namespace,
                image_references=image_references,
                labels=labels,
                annotations=annotations,
                containers=containers_info,
                service_account_name=service_account_name,
                secret_references=secret_references,
                configmap_references=configmap_references
            )

            # Invoke asset service
            async with AsyncSessionLocal() as session:
                asset_service = AssetService(session)
                if event_type == "DELETED":
                    cluster_id = await asset_service.get_or_create_cluster(msg.cluster_name)
                    await asset_service.deactivate_asset(cluster_id, msg.workload_uid)
                else:
                    await asset_service.process_discovery_message(msg)

        except Exception as e:
            logger.error(f"Failed to process resource {kind}/{getattr(obj.metadata, 'name', 'unknown')}: {e}")
            logger.debug(traceback.format_exc())
