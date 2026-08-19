import asyncio
import logging
import os
import traceback
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from kubernetes import client, watch
from kubernetes.client.rest import ApiException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.discovery import DiscoveryMessage, ContainerInfo
from app.db.session import AsyncSessionLocal
from app.services.asset import AssetService
from app.models.cluster import Cluster

logger = logging.getLogger(__name__)


class DiscoveryWatcher:
    def __init__(self, cluster: Cluster):
        self.cluster = cluster
        self.k8s_configured = False
        self.apps_v1 = None
        self.batch_v1 = None
        self.core_v1 = None
        self.tasks: List[asyncio.Task] = []
        self._running = False

    def initialize_client(self, force: bool = False) -> bool:
        """
        Dynamically initializes the cluster-specific Kubernetes clients.
        """
        if self.k8s_configured and not force:
            return True

        try:
            from app.discovery.factory import ClusterConnectionFactory
            api_client = ClusterConnectionFactory.create_api_client(self.cluster)
            self.apps_v1 = client.AppsV1Api(api_client)
            self.batch_v1 = client.BatchV1Api(api_client)
            self.core_v1 = client.CoreV1Api(api_client)
            self.k8s_configured = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes API clients for cluster {self.cluster.name}: {e}")
            self.k8s_configured = False
            return False

    def start_loops(self, loop: asyncio.AbstractEventLoop):
        """
        Starts the watcher background loops for this specific cluster.
        """
        if not self.k8s_configured:
            logger.warning(f"Cannot start loops: Kubernetes client for {self.cluster.name} is not configured.")
            return

        self._running = True
        logger.info(f"Starting Discovery Watcher loops for cluster: {self.cluster.name} ({self.cluster.id})")
        
        # Start watching resources in background threads to avoid blocking the main event loop
        self.tasks.append(asyncio.create_task(asyncio.to_thread(self._sync_watch_loop, "Deployment", loop)))
        self.tasks.append(asyncio.create_task(asyncio.to_thread(self._sync_watch_loop, "StatefulSet", loop)))
        self.tasks.append(asyncio.create_task(asyncio.to_thread(self._sync_watch_loop, "Job", loop)))
        self.tasks.append(asyncio.create_task(asyncio.to_thread(self._sync_watch_loop, "CronJob", loop)))
        self.tasks.append(asyncio.create_task(asyncio.to_thread(self._sync_watch_loop, "Pod", loop)))
        
        # Start periodic reconciliation loop
        self.tasks.append(asyncio.create_task(self._reconciliation_loop()))

    async def _update_db_status(self, status: str, last_error: Optional[str] = None):
        try:
            async with AsyncSessionLocal() as session:
                from app.repositories.cluster import ClusterRepository
                repo = ClusterRepository(session)
                await repo.update_connection_status(self.cluster.id, status, last_error)
        except Exception as e:
            logger.error(f"Failed to update cluster status in DB: {e}")

    async def stop(self):
        """
        Stops the watcher tasks and cleans up.
        """
        logger.info(f"Stopping Discovery Watcher tasks for cluster {self.cluster.name}...")
        self._running = False
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        logger.info(f"Discovery Watcher tasks for cluster {self.cluster.name} stopped.")

    async def _reconciliation_loop(self):
        """
        Periodically performs a full sync of all workloads.
        """
        recon_secs = int(os.environ.get("RECONCILIATION_INTERVAL_SECS", settings.RECONCILIATION_INTERVAL_SECS or 300))
        while self._running:
            try:
                logger.info(f"Starting periodic full cluster reconciliation scan for {self.cluster.name}...")
                await self.reconcile_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error during periodic cluster reconciliation on {self.cluster.name}: {e}", exc_info=True)
            
            await asyncio.sleep(recon_secs)

    async def reconcile_all(self):
        """
        Queries all workloads across all namespaces and processes them.
        Deactivates any asset that is no longer present on the cluster.
        """
        if self.cluster.connection_type == "eks_iam":
            try:
                await asyncio.to_thread(self.initialize_client, True)
            except Exception as e:
                logger.error(f"Failed to initialize EKS client: {e}")
                await self._update_db_status("error", str(e))
                return

        if not self.k8s_configured:
            return

        try:
            active_uids = set()

            deployments = await asyncio.to_thread(self.apps_v1.list_deployment_for_all_namespaces)
            for dep in deployments.items:
                if dep.metadata and dep.metadata.uid:
                    active_uids.add(dep.metadata.uid)
                await self._process_resource(dep, "Deployment", "ADDED")

            statefulsets = await asyncio.to_thread(self.apps_v1.list_stateful_set_for_all_namespaces)
            for ss in statefulsets.items:
                if ss.metadata and ss.metadata.uid:
                    active_uids.add(ss.metadata.uid)
                await self._process_resource(ss, "StatefulSet", "ADDED")

            jobs = await asyncio.to_thread(self.batch_v1.list_job_for_all_namespaces)
            for job in jobs.items:
                if job.metadata and job.metadata.uid:
                    active_uids.add(job.metadata.uid)
                await self._process_resource(job, "Job", "ADDED")

            cronjobs = await asyncio.to_thread(self.batch_v1.list_cron_job_for_all_namespaces)
            for cj in cronjobs.items:
                if cj.metadata and cj.metadata.uid:
                    active_uids.add(cj.metadata.uid)
                await self._process_resource(cj, "CronJob", "ADDED")

            # Deactivate database assets that are no longer active on the cluster
            async with AsyncSessionLocal() as session:
                asset_service = AssetService(session)
                assets, _ = await asset_service.asset_repo.list_filtered(
                    cluster_id=self.cluster.id,
                    status=None
                )
                for asset in assets:
                    if asset.status != "inactive" and asset.workload_uid not in active_uids:
                        logger.info(f"Reconciliation: deactivating workload {asset.workload_name} as it no longer exists on cluster {self.cluster.name}")
                        await asset_service.deactivate_asset(self.cluster.id, asset.workload_uid)

            await self._update_db_status("connected")

        except Exception as e:
            logger.error(f"Error during full K8s reconciliation on {self.cluster.name}: {e}")
            await self._update_db_status("error", str(e))


    def _sync_watch_loop(self, resource_kind: str, loop: asyncio.AbstractEventLoop):
        """
        Synchronous loop running in a background thread to read K8s watches.
        Passes events back to the main thread's async event loop.
        """
        import os
        delay = int(os.environ.get("WATCHER_RETRY_DELAY_SECS", settings.WATCHER_RETRY_DELAY_SECS or 5))
        max_delay = int(os.environ.get("WATCHER_MAX_RETRY_DELAY_SECS", settings.WATCHER_MAX_RETRY_DELAY_SECS or 60))
        w = watch.Watch()

        while self._running:
            try:
                if self.cluster.connection_type == "eks_iam":
                    try:
                        self.initialize_client(force=True)
                    except Exception as e:
                        logger.error(f"Failed to initialize EKS watch client: {e}")
                        asyncio.run_coroutine_threadsafe(self._update_db_status("error", str(e)), loop)
                        import time
                        time.sleep(delay)
                        continue

                logger.info(f"Starting Watch stream for {self.cluster.name} K8s resource: {resource_kind}...")
                
                if resource_kind == "Deployment":
                    func = self.apps_v1.list_deployment_for_all_namespaces
                elif resource_kind == "StatefulSet":
                    func = self.apps_v1.list_stateful_set_for_all_namespaces
                elif resource_kind == "Job":
                    func = self.batch_v1.list_job_for_all_namespaces
                elif resource_kind == "CronJob":
                    func = self.batch_v1.list_cron_job_for_all_namespaces
                elif resource_kind == "Pod":
                    func = self.core_v1.list_pod_for_all_namespaces
                else:
                    return

                # Read events from blocking generator
                for event in w.stream(func, timeout_seconds=30):
                    if not self._running:
                        break
                    
                    obj = event['object']
                    event_type = event['type']
                    
                    # Schedule coroutine execution back on the main async event loop
                    asyncio.run_coroutine_threadsafe(
                        self._process_resource(obj, resource_kind, event_type),
                        loop
                    )
                    delay = int(os.environ.get("WATCHER_RETRY_DELAY_SECS", settings.WATCHER_RETRY_DELAY_SECS or 5))

            except Exception as e:
                if not self._running:
                    break
                logger.error(f"Error in Watch stream for {resource_kind} on {self.cluster.name}: {e}. Retrying in {delay}s...")
                asyncio.run_coroutine_threadsafe(self._update_db_status("error", str(e)), loop)
                import time
                time.sleep(delay)
                delay = min(max_delay, delay * 2)

    def _determine_detailed_status(self, kind: str, obj: any, pods: list) -> str:
        if not pods:
            spec = getattr(obj, "spec", None)
            replicas = getattr(spec, "replicas", None) if spec else None
            if replicas == 0:
                return "inactive"
            return "inactive"

        total_pods = len(pods)
        running_pods = 0
        ready_pods = 0
        pending_pods = 0
        failed_pods = 0

        for pod in pods:
            pod_status = getattr(pod, "status", None)
            if not pod_status:
                continue
            phase = getattr(pod_status, "phase", None)
            if phase == "Running":
                running_pods += 1
                conditions = getattr(pod_status, "conditions", None) or []
                is_ready = False
                for cond in conditions:
                    if getattr(cond, "type", None) == "Ready" and getattr(cond, "status", None) == "True":
                        is_ready = True
                        break
                if is_ready:
                    ready_pods += 1
            elif phase == "Pending":
                pending_pods += 1
            elif phase in ("Failed", "Unknown"):
                failed_pods += 1
            elif phase == "Succeeded":
                ready_pods += 1
                running_pods += 1

        if pending_pods > 0 and running_pods == 0:
            return "pending"
        elif pending_pods > 0 or failed_pods > 0:
            if ready_pods > 0:
                return "degraded"
            return "progressing"
        elif ready_pods == total_pods and total_pods > 0:
            return "available"
        elif ready_pods > 0:
            return "degraded"
        elif running_pods > 0:
            return "progressing"
        
        return "inactive"

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
            
            if kind == "Pod":
                # Process pod event to dynamically update workload active status and last_active_at
                try:
                    owner_refs = metadata.owner_references or []
                    owner_kind = None
                    owner_name = None
                    
                    for ref in owner_refs:
                        if ref.kind == "ReplicaSet":
                            owner_kind = "Deployment"
                            owner_name = ref.name
                            parts = ref.name.rsplit('-', 1)
                            if len(parts) > 0:
                                owner_name = parts[0]
                        else:
                            owner_kind = ref.kind
                            owner_name = ref.name
                            
                    if owner_name and owner_kind in ("Deployment", "StatefulSet", "Job", "CronJob"):
                        is_pod_active = False
                        pod_status = getattr(obj, "status", None)
                        if pod_status and event_type != "DELETED":
                            phase = getattr(pod_status, "phase", None)
                            if phase == "Running":
                                conditions = getattr(pod_status, "conditions", None) or []
                                for cond in conditions:
                                    if getattr(cond, "type", None) == "Ready" and getattr(cond, "status", None) == "True":
                                        is_pod_active = True
                                        break

                        async with AsyncSessionLocal() as session:
                            asset_service = AssetService(session)
                            asset = await asset_service.asset_repo.get_by_name_kind_namespace(
                                self.cluster.id, owner_name, owner_kind, namespace
                            )
                            if asset:
                                from app.schemas.asset import AssetUpdate
                                from app.schemas.enums import AssetStatus
                                
                                matched_pods = []
                                if self.core_v1:
                                    try:
                                        pods = await asyncio.to_thread(
                                            self.core_v1.list_namespaced_pod,
                                            namespace=namespace
                                        )
                                        if pods and pods.items:
                                            for p in pods.items:
                                                # If it is the current pod from the event
                                                if p.metadata.name == metadata.name and event_type != "DELETED":
                                                    matched_pods.append(p)
                                                    continue
                                                if p.metadata.name == metadata.name:
                                                    continue
                                                for p_ref in (p.metadata.owner_references or []):
                                                    p_owner_name = p_ref.name
                                                    if p_ref.kind == "ReplicaSet":
                                                        p_parts = p_ref.name.rsplit('-', 1)
                                                        if len(p_parts) > 0:
                                                            p_owner_name = p_parts[0]
                                                    if p_owner_name == owner_name and p_ref.kind == owner_kind:
                                                        matched_pods.append(p)
                                                        break
                                    except Exception:
                                        pass
                                
                                detailed_status = self._determine_detailed_status(owner_kind, None, matched_pods)
                                is_currently_active = detailed_status in ("active", "available", "progressing", "degraded")
                                
                                update_schema = AssetUpdate(
                                    status=AssetStatus(detailed_status) if detailed_status in [s.value for s in AssetStatus] else AssetStatus.INACTIVE,
                                    last_active_at=datetime.now(timezone.utc) if is_currently_active else asset.last_active_at
                                )
                                await asset_service.asset_repo.update(asset, update_schema)
                except Exception as pod_err:
                    logger.debug(f"Failed to process Pod event on {self.cluster.name}: {pod_err}")
                return

            containers_info: List[ContainerInfo] = []

            image_references = []
            secret_references = []
            configmap_references = []
            service_account_name = None

            # 1. Fetch Namespace labels
            namespace_labels = {}
            if self.core_v1:
                try:
                    ns_obj = await asyncio.to_thread(self.core_v1.read_namespace, name=namespace)
                    if ns_obj and ns_obj.metadata:
                        namespace_labels = ns_obj.metadata.labels or {}
                except Exception as ns_err:
                    logger.debug(f"Failed to read namespace labels for {namespace} on {self.cluster.name}: {ns_err}")

            spec = getattr(obj, "spec", None)
            is_active = True
            
            if spec:
                template = getattr(spec, "template", None)
                job_spec = None
                
                if kind == "CronJob":
                    job_template = getattr(spec, "job_template", None)
                    if job_template:
                        job_spec = getattr(job_template, "spec", None)
                elif kind == "Job":
                    template = spec
                
                if job_spec:
                    template = getattr(job_spec, "template", None)

                status_str = "inactive"
                # 2. Fetch Pod readiness / running status for is_active
                if self.core_v1:
                    try:
                        selector_dict = None
                        selector_obj = getattr(spec, "selector", None)
                        if selector_obj:
                            selector_dict = getattr(selector_obj, "match_labels", None)
                        
                        if selector_dict:
                            selector_str = ",".join([f"{k}={v}" for k, v in selector_dict.items()])
                            pods = await asyncio.to_thread(
                                self.core_v1.list_namespaced_pod,
                                namespace=namespace,
                                label_selector=selector_str
                            )
                            if pods and pods.items:
                                status_str = self._determine_detailed_status(kind, obj, pods.items)
                                any_running = False
                                for pod in pods.items:
                                    pod_status = getattr(pod, "status", None)
                                    if pod_status:
                                        phase = getattr(pod_status, "phase", None)
                                        if phase == "Running":
                                            any_running = True
                                            break
                                is_active = any_running
                            else:
                                is_active = False
                                status_str = "inactive"
                    except Exception as pod_err:
                        logger.debug(f"Failed to list pods to determine status: {pod_err}")
                
                # Special active check for CronJob if it lists active jobs
                if kind == "CronJob":
                    status = getattr(obj, "status", None)
                    active_jobs = getattr(status, "active", None)
                    is_active = bool(active_jobs and len(active_jobs) > 0)
                    status_str = "available" if is_active else "inactive"

                if template:
                    pod_spec = getattr(template, "spec", None)
                    if pod_spec:
                        service_account_name = getattr(pod_spec, "service_account_name", None)
                        
                        volumes = getattr(pod_spec, "volumes", None) or []
                        for vol in volumes:
                            if getattr(vol, "secret", None):
                                secret_references.append(vol.secret.secret_name)
                            if getattr(vol, "config_map", None):
                                configmap_references.append(vol.config_map.name)

                        # Extract from both regular containers and initContainers
                        all_containers = []
                        all_containers.extend(getattr(pod_spec, "containers", None) or [])
                        all_containers.extend(getattr(pod_spec, "init_containers", None) or [])

                        for container in all_containers:
                            env_dict = {}
                            
                            # Extract env variables
                            env = getattr(container, "env", None) or []
                            for e in env:
                                name_env = getattr(e, "name", None)
                                if name_env:
                                    env_dict[name_env] = "[PRESENT]"
                                    
                                    # env[].valueFrom.secretKeyRef.name
                                    # env[].valueFrom.configMapKeyRef.name
                                    val_from = getattr(e, "value_from", None)
                                    if val_from:
                                        s_key = getattr(val_from, "secret_key_ref", None)
                                        if s_key and getattr(s_key, "name", None):
                                            secret_references.append(s_key.name)
                                        cm_key = getattr(val_from, "config_map_key_ref", None)
                                        if cm_key and getattr(cm_key, "name", None):
                                            configmap_references.append(cm_key.name)
                                            
                            # Extract envFrom references
                            env_from = getattr(container, "env_from", None) or []
                            for ef in env_from:
                                # envFrom[].secretRef.name
                                s_ref = getattr(ef, "secret_ref", None)
                                if s_ref and getattr(s_ref, "name", None):
                                    secret_references.append(s_ref.name)
                                # envFrom[].configMapRef.name
                                cm_ref = getattr(ef, "config_map_ref", None)
                                if cm_ref and getattr(cm_ref, "name", None):
                                    configmap_references.append(cm_ref.name)

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

            # Deduplicate secret/configmap references
            secret_references = list(set(secret_references))
            configmap_references = list(set(configmap_references))

            msg = DiscoveryMessage(
                cluster_id=self.cluster.id,
                cluster_name=self.cluster.name,
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
                configmap_references=configmap_references,
                namespace_labels=namespace_labels,
                is_active=is_active,
                status=status_str
            )

            async with AsyncSessionLocal() as session:
                asset_service = AssetService(session)
                if event_type == "DELETED":
                    await asset_service.deactivate_asset(msg.cluster_id, msg.workload_uid)
                else:
                    await asset_service.process_discovery_message(msg)

        except Exception as e:
            logger.error(f"Error processing K8s resource in {self.cluster.name}: {e}\n{traceback.format_exc()}")
import os
