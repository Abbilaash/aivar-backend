import os
import logging
from typing import Optional
from kubernetes import client, config
from app.models.cluster import Cluster
from app.core.config import settings

logger = logging.getLogger(__name__)


class ClusterConnectionFactory:
    @staticmethod
    def create_api_client(cluster: Cluster) -> client.ApiClient:
        """
        Dynamically constructs a dedicated Kubernetes ApiClient for the given cluster.
        Supports:
        - connection_type="kubeconfig": loads path/context from settings/database
        - connection_type="eks_iam": leverages local EKS contexts and AWS IAM auth exec flows
        """
        # 1. Native OIDC token authentication (Service Account token + OIDC Provider)
        if cluster.connection_type == "oidc":
            logger.info(f"Configuring OIDC API client for cluster '{cluster.name}' (endpoint={cluster.api_server})")
            token = cluster.credential_reference
            if not token:
                raise ConnectionError("OIDC connection type requires a valid token in credential_reference")
            conf = client.Configuration()
            conf.host = cluster.api_server
            conf.verify_ssl = False
            conf.api_key['authorization'] = f"Bearer {token}"
            return client.ApiClient(conf)

        # 2. Native EKS IAM token generation (avoids dependency on aws CLI executable)
        if cluster.connection_type == "eks_iam":
            logger.info(f"Generating EKS token natively for EKS cluster '{cluster.eks_cluster_name}' in region '{cluster.aws_region}'...")
            try:
                import base64
                import boto3
                from botocore.signers import RequestSigner

                # EKS clusters verify tokens against STS. By default, EKS only trusts STS tokens signed for us-east-1.
                reg = "us-east-1"
                cname = cluster.eks_cluster_name or cluster.name

                # Priority 1: Use explicit AWS credentials stored on the cluster record.
                # This avoids dependence on a local SSO session which can expire mid-run.
                if cluster.aws_access_key_id and cluster.aws_secret_access_key:
                    logger.info(f"Using explicit AWS IAM credentials stored for cluster '{cname}'.")
                    session = boto3.Session(
                        aws_access_key_id=cluster.aws_access_key_id,
                        aws_secret_access_key=cluster.aws_secret_access_key,
                        region_name=reg
                    )
                elif cluster.credential_reference and cluster.credential_reference.startswith("arn:aws:iam::"):
                    # Priority 2: Assume an IAM role (requires the underlying default credential to be valid)
                    logger.info(f"Assuming IAM Role '{cluster.credential_reference}' for EKS token signing...")
                    temp_sts = boto3.client('sts', region_name=reg)
                    assumed = temp_sts.assume_role(
                        RoleArn=cluster.credential_reference,
                        RoleSessionName="AIVAREKSSession"
                    )
                    creds = assumed['Credentials']
                    session = boto3.Session(
                        aws_access_key_id=creds['AccessKeyId'],
                        aws_secret_access_key=creds['SecretAccessKey'],
                        aws_session_token=creds['SessionToken'],
                        region_name=reg
                    )
                else:
                    # Priority 3: Default boto3 chain (env vars → ~/.aws/credentials → SSO)
                    session = boto3.Session(region_name=reg)

                sts_client = session.client('sts', region_name=reg)

                # Get the actual service_id object (it has the hyphenize attribute)
                service_id = sts_client.meta.service_model.service_id

                signer = RequestSigner(
                    service_id,
                    reg,
                    'sts',
                    'v4',
                    session.get_credentials(),
                    session.events
                )

                params = {
                    'method': 'GET',
                    'url': 'https://sts.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
                    'body': {},
                    'headers': {
                        'x-k8s-aws-id': cname
                    },
                    'context': {}
                }

                signed_url = signer.generate_presigned_url(
                    params,
                    region_name='us-east-1',
                    expires_in=60,
                    operation_name=''
                )

                base64_url = base64.urlsafe_b64encode(signed_url.encode('utf-8')).decode('utf-8')
                token = 'k8s-aws-v1.' + base64_url.rstrip('=')

                conf = client.Configuration()
                conf.host = cluster.api_server
                conf.verify_ssl = False
                conf.api_key['authorization'] = f"Bearer {token}"

                logger.info(f"Successfully generated native EKS token for {cname}.")
                return client.ApiClient(conf)
            except Exception as e:
                logger.warning(f"Native EKS token generation failed, falling back to config: {e}")

        # Resolve config file path
        kubeconfig_path = os.environ.get("DEFAULT_KUBECONFIG_PATH") or settings.KUBECONFIG_PATH or os.path.expanduser("~/.kube/config")
        
        context = cluster.kube_context
        
        logger.info(
            f"Configuring API client for cluster '{cluster.name}' (type={cluster.connection_type}, "
            f"context={context or 'default'}, path={kubeconfig_path})"
        )

        try:
            # Load in-cluster config if running inside a pod and no specific context/kubeconfig is forced
            if not context and not os.path.exists(kubeconfig_path):
                try:
                    config.load_incluster_config()
                    logger.info(f"Loaded in-cluster config for cluster {cluster.name}")
                    return client.ApiClient()
                except Exception:
                    pass

            # Construct new client from specific configuration and context
            api_client = config.new_client_from_config(
                config_file=kubeconfig_path,
                context=context
            )
            return api_client
            
        except Exception as e:
            logger.error(f"Failed to create Kubernetes client for cluster {cluster.name}: {e}")
            raise ConnectionError(f"Kubernetes client initialization failed: {str(e)}")
