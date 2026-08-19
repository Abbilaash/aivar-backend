import re
from typing import Dict, List, Optional, Tuple, Any
from app.schemas.enums import AssetType, RiskTier
from app.schemas.discovery import DiscoveryMessage


class AIDetector:
    # Key-value keywords and patterns for AI workloads detection
    PROVIDER_SDK_KEYWORDS = [
        "openai", "anthropic", "langchain", "langgraph", "ollama",
        "huggingface", "bedrock", "vertexai", "azure-openai", "azure openai"
    ]
    MODEL_KEYWORDS = [
        "gpt", "claude", "llama", "mistral", "gemini"
    ]
    AI_ENV_VARS = [
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "COHERE_API_KEY",
        "MISTRAL_API_KEY", "LLAMA_API_KEY", "HF_TOKEN", "HUGGINGFACE_CO_TOKEN",
        "OLLAMA_HOST", "LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY"
    ]
    IMAGE_COMMAND_KEYWORDS = [
        "ollama", "vllm", "tgi", "text-generation-inference", "localai",
        "triton-inference-server", "langshare", "flowise"
    ]

    @classmethod
    def detect(cls, msg: DiscoveryMessage) -> Tuple[bool, Optional[AssetType], float, List[str]]:
        """
        Inspects workload metadata and returns:
        - is_ai: bool
        - asset_type: Optional[AssetType] (model, agent, or tool)
        - confidence: float (0.0 to 1.0)
        - evidence: List[str]
        """
        evidence = []
        confidence = 0.0

        # 1. Explicit Label override
        explicit_type = msg.labels.get("aivar.io/asset-type")
        if explicit_type:
            evidence.append(f"Explicit detection label aivar.io/asset-type={explicit_type}")
            try:
                asset_type = AssetType(explicit_type.lower())
                return True, asset_type, 1.0, evidence
            except ValueError:
                # Fallback to model if the label is invalid but present
                return True, AssetType.MODEL, 1.0, evidence

        # Gather check fields (names, namespace, images, annotations, labels, command/args)
        all_text_sources = [
            ("workload_name", msg.workload_name),
            ("namespace", msg.namespace),
        ]
        
        # Check label keys and values
        for k, v in msg.labels.items():
            all_text_sources.append((f"label key '{k}'", k))
            all_text_sources.append((f"label value '{v}'", v))

        # Check annotation keys and values
        for k, v in msg.annotations.items():
            if k.startswith("kubernetes.io/") or k.startswith("kubectl.kubernetes.io/") or k == "deployment.kubernetes.io/revision":
                continue
            all_text_sources.append((f"annotation key '{k}'", k))
            all_text_sources.append((f"annotation value '{v}'", v))

        # Check image references
        for img in msg.image_references:
            all_text_sources.append(("image reference", img))

        # Check env variable names (never values)
        for container in msg.containers:
            for env_name in container.env.keys():
                all_text_sources.append(("env name", env_name))
            for cmd in container.command:
                all_text_sources.append(("command", cmd))
            for arg in container.args:
                all_text_sources.append(("arg", arg))

        # Run keyword check on text sources
        detected_keywords = set()
        for field, text in all_text_sources:
            if not text:
                continue
            text_lower = text.lower()
            
            # Check SDKs
            for kw in cls.PROVIDER_SDK_KEYWORDS:
                if kw in text_lower:
                    detected_keywords.add(kw)
                    evidence.append(f"Found keyword '{kw}' in {field}")

            # Check Models
            for model in cls.MODEL_KEYWORDS:
                if model in text_lower:
                    detected_keywords.add(model)
                    evidence.append(f"Found model reference '{model}' in {field}")

            # Check image/command markers
            for marker in cls.IMAGE_COMMAND_KEYWORDS:
                if marker in text_lower:
                    detected_keywords.add(marker)
                    evidence.append(f"Found image/command marker '{marker}' in {field}")

        # Check explicit env variables
        for container in msg.containers:
            for env_name in container.env.keys():
                if env_name in cls.AI_ENV_VARS:
                    evidence.append(f"AI environment variable '{env_name}' is set")
                    detected_keywords.add(env_name)

        if not evidence:
            return False, None, 0.0, []

        # Determine Confidence
        # More hits / specific markers raise confidence
        hits = len(detected_keywords)
        if any(env in detected_keywords for env in cls.AI_ENV_VARS):
            confidence = min(0.9, 0.7 + (hits * 0.05))
        elif any(marker in detected_keywords for marker in cls.IMAGE_COMMAND_KEYWORDS):
            confidence = min(0.95, 0.8 + (hits * 0.05))
        else:
            confidence = min(0.8, 0.4 + (hits * 0.1))

        # Infer Asset Type:
        # Default to model unless there are indicators of agent (orchestration, framework) or tool (databases, tools, function callers)
        asset_type = AssetType.MODEL
        text_summary = " ".join([t[1] for t in all_text_sources if t[1]]).lower()
        
        agent_indicators = ["agent", "langchain", "langgraph", "flowise", "autogen", "crewai"]
        tool_indicators = ["tool", "calculator", "search", "web-search", "database", "retriever"]
        
        if any(ind in text_summary for ind in agent_indicators):
            asset_type = AssetType.AGENT
        elif any(ind in text_summary for ind in tool_indicators):
            asset_type = AssetType.TOOL

        return True, asset_type, round(confidence, 2), list(set(evidence))

    @classmethod
    def infer_owner(cls, msg: DiscoveryMessage) -> Tuple[str, str]:
        """
        Returns (owner_name, source) based on precedence:
        1. aivar.io/owner annotation on workload
        2. owner or team label on workload
        3. aivar.io/owner or team label on namespace
        4. service-account owner label or service account name
        5. "unassigned"
        """
        # Precedence 1: aivar.io/owner annotation on workload
        if "aivar.io/owner" in msg.annotations:
            return msg.annotations["aivar.io/owner"], "annotation:aivar.io/owner"

        # Precedence 2: owner or team label on workload
        for label_key in ["owner", "team"]:
            if label_key in msg.labels:
                return msg.labels[label_key], f"label:{label_key}"

        # Precedence 3: aivar.io/owner or team label on namespace
        ns_labels = getattr(msg, "namespace_labels", {}) or {}
        if "aivar.io/owner" in ns_labels:
            return ns_labels["aivar.io/owner"], "namespace_annotation:aivar.io/owner"
        if "team" in ns_labels:
            return ns_labels["team"], "namespace_label:team"

        # Precedence 4: service-account owner label or service account name
        for sa_label in ["service-account-owner", "service-account", "serviceaccount"]:
            if sa_label in msg.labels:
                return msg.labels[sa_label], f"label:{sa_label}"
        if msg.service_account_name and msg.service_account_name != "default":
            return msg.service_account_name, "service_account"

        # Precedence 5: default
        return "unassigned", "not_declared"


    @classmethod
    def calculate_risk(cls, msg: DiscoveryMessage) -> Tuple[RiskTier, List[str]]:
        """
        Returns (RiskTier, reasons) based on indicators.
        - low: no sensitive access indicators.
        - medium: internal ConfigMaps/secrets or internal service accounts.
        - high: sensitive/customer/PII/financial secret-name indicators, privileged settings,
                broad service account/RBAC indicators, or multiple sensitive signals.
        """
        reasons = []
        sensitive_signals = 0

        # Check for Secret / ConfigMap name indicators
        sensitive_key_patterns = [
            "customer", "pii", "finance", "billing", "payment", "db", "database",
            "prod", "credential", "auth", "token", "password"
        ]

        # ConfigMaps/Secrets usage triggers medium automatically
        if msg.secret_references:
            reasons.append(f"Workload references Secrets: {', '.join(msg.secret_references[:3])}")
            # Check for high risk secret names
            for sec in msg.secret_references:
                sec_lower = sec.lower()
                matched = [p for p in sensitive_key_patterns if p in sec_lower]
                if matched:
                    reasons.append(f"Workload references sensitive Secret: '{sec}' (matched: {', '.join(matched)})")
                    sensitive_signals += 2

        if msg.configmap_references:
            reasons.append(f"Workload references ConfigMaps: {', '.join(msg.configmap_references[:3])}")

        # Check env variables for sensitive keywords
        for container in msg.containers:
            for env_name in container.env.keys():
                env_lower = env_name.lower()
                # Check for sensitive indicators
                matched_env = [p for p in ["key", "secret", "token", "password", "credential"] if p in env_lower]
                if matched_env:
                    reasons.append(f"Workload contains sensitive environment variable name: '{env_name}'")
                    sensitive_signals += 1

        # Service Account indicators
        if msg.service_account_name and msg.service_account_name != "default":
            reasons.append(f"Workload runs under specific Service Account: '{msg.service_account_name}'")
            # If the service account looks privileged/admin
            sa_lower = msg.service_account_name.lower()
            if any(admin_pat in sa_lower for admin_pat in ["admin", "cluster", "writer", "privileged"]):
                reasons.append(f"Privileged service account indicator in name: '{msg.service_account_name}'")
                sensitive_signals += 2

        # Check labels / annotations for privileged metadata
        for k, v in {**msg.labels, **msg.annotations}.items():
            if "privileged" in k.lower() or "privileged" in v.lower():
                reasons.append(f"Privileged annotation/label key/value found: {k}={v}")
                sensitive_signals += 2

        # Final tier logic
        if sensitive_signals >= 3:
            reasons.append(f"Multiple sensitive signals detected (count: {sensitive_signals})")
            return RiskTier.HIGH, reasons
        elif sensitive_signals > 0 or msg.secret_references or msg.configmap_references:
            return RiskTier.MEDIUM, reasons
        else:
            reasons.append("No sensitive access indicators observed")
            return RiskTier.LOW, reasons
