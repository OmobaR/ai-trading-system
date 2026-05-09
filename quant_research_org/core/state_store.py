"""
Core: Shared Memory / State Store for inter-agent communication.
Implements artifact persistence with versioning, schema validation,
and lineage tracking for reproducible quant research.
Also pushes approved features to Redis for live consumption.
"""
from __future__ import annotations

import json
import hashlib
import pickle
import logging
import redis
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import pandas as pd

from src.config.settings import config

logger = logging.getLogger(__name__)

class ArtifactStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"
    APPROVED = "approved"
    DEPRECATED = "deprecated"

@dataclass
class ArtifactMetadata:
    agent: str
    phase: str
    version: int = 1
    parent_artifact: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: ArtifactStatus = ArtifactStatus.PENDING
    checksum: str = ""
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

@dataclass
class PipelineArtifact:
    """Immutable-ish research artifact produced by an agent."""
    artifact_id: str
    name: str
    data: Any
    metadata: ArtifactMetadata

    def __post_init__(self):
        if not self.metadata.checksum:
            self.metadata.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        try:
            payload = pickle.dumps(self.data, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            payload = str(self.data).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "metadata": self.metadata.to_dict(),
            "checksum": self.metadata.checksum,
        }

class StateStore:
    """
    Shared memory/state store for inter-agent communication.
    - File-based artifact registry for reproducibility
    - In-memory hot cache for pipeline speed
    - Strict schema validation gates
    - Redis integration for live system features
    """

    def __init__(self, base_path: str = "./data/processed"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._registry_path = self.base_path / "artifact_registry.json"
        self._registry: Dict[str, Dict[str, Any]] = {}
        self._hot_cache: Dict[str, PipelineArtifact] = {}
        self._load_registry()
        # Connect to Redis (assumes running on localhost:6379)
        self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

    def _load_registry(self):
        if self._registry_path.exists():
            with open(self._registry_path, "r") as f:
                self._registry = json.load(f)
        else:
            self._registry = {}

    def _save_registry(self):
        with open(self._registry_path, "w") as f:
            json.dump(self._registry, f, indent=2, default=str)

    def _artifact_path(self, artifact_id: str) -> Path:
        return self.base_path / f"{artifact_id}.pkl"

    def _meta_path(self, artifact_id: str) -> Path:
        return self.base_path / f"{artifact_id}.meta.json"

    def save(self, artifact: PipelineArtifact, overwrite: bool = False) -> str:
        """Persist artifact to disk and register it."""
        aid = artifact.artifact_id
        if aid in self._registry and not overwrite:
            raise ValueError(f"Artifact {aid} exists. Use overwrite=True to replace.")

        # Persist data
        artifact_path = self._artifact_path(aid)
        with open(artifact_path, "wb") as f:
            pickle.dump(artifact.data, f, protocol=pickle.HIGHEST_PROTOCOL)

        # Persist metadata
        meta_path = self._meta_path(aid)
        with open(meta_path, "w") as f:
            json.dump(artifact.metadata.to_dict(), f, indent=2)

        # Update registry
        self._registry[aid] = artifact.to_dict()
        self._save_registry()

        # Update hot cache
        self._hot_cache[aid] = artifact

        # If this is an approved artifact from the governance agent,
        # push its contents to Redis for the live trading system.
        if (artifact.metadata.agent == "governance_agent" and
            artifact.metadata.status == ArtifactStatus.APPROVED):
            approved_data = artifact.data  # expected dict: {symbol: {'features': {...}, 'regime': str}}
            if isinstance(approved_data, dict):
                for sym, feat_dict in approved_data.items():
                    self.push_approved_features(
                        sym,
                        feat_dict.get('features', {}),
                        feat_dict.get('regime', 'unknown')
                    )

        logger.info(f"[StateStore] Saved artifact {aid} ({artifact.metadata.agent} / {artifact.metadata.phase})")
        return aid

    def load(self, artifact_id: str) -> PipelineArtifact:
        """Load artifact from hot cache or disk."""
        if artifact_id in self._hot_cache:
            return self._hot_cache[artifact_id]

        if artifact_id not in self._registry:
            raise KeyError(f"Artifact {artifact_id} not found in registry.")

        artifact_path = self._artifact_path(artifact_id)
        meta_path = self._meta_path(artifact_id)

        with open(artifact_path, "rb") as f:
            data = pickle.load(f)

        with open(meta_path, "r") as f:
            meta_dict = json.load(f)

        metadata = ArtifactMetadata(
            agent=meta_dict["agent"],
            phase=meta_dict["phase"],
            version=meta_dict.get("version", 1),
            parent_artifact=meta_dict.get("parent_artifact"),
            created_at=meta_dict.get("created_at"),
            status=ArtifactStatus(meta_dict.get("status", "pending")),
            checksum=meta_dict.get("checksum", ""),
            tags=meta_dict.get("tags", []),
            notes=meta_dict.get("notes", ""),
        )

        artifact = PipelineArtifact(
            artifact_id=artifact_id,
            name=self._registry[artifact_id].get("name", artifact_id),
            data=data,
            metadata=metadata,
        )
        self._hot_cache[artifact_id] = artifact
        return artifact

    def update_status(self, artifact_id: str, status: ArtifactStatus, notes: str = ""):
        """Update artifact validation status."""
        if artifact_id not in self._registry:
            raise KeyError(f"Artifact {artifact_id} not found.")

        meta_path = self._meta_path(artifact_id)
        with open(meta_path, "r") as f:
            meta = json.load(f)

        meta["status"] = status.value
        if notes:
            meta["notes"] = notes

        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        self._registry[artifact_id]["metadata"]["status"] = status.value
        self._save_registry()

        if artifact_id in self._hot_cache:
            self._hot_cache[artifact_id].metadata.status = status

        # If setting status to APPROVED and artifact is from governance_agent,
        # push to Redis (redundant but safe if save didn't catch it)
        if (status == ArtifactStatus.APPROVED and
            self._registry[artifact_id]["metadata"].get("agent") == "governance_agent"):
            artifact = self.load(artifact_id)
            approved_data = artifact.data
            if isinstance(approved_data, dict):
                for sym, feat_dict in approved_data.items():
                    self.push_approved_features(
                        sym,
                        feat_dict.get('features', {}),
                        feat_dict.get('regime', 'unknown')
                    )

        logger.info(f"[StateStore] Artifact {artifact_id} status → {status.value}")

    def push_approved_features(self, symbol: str, features: Dict, regime: str):
        """Push latest approved features to Redis for live system."""
        key = f"approved_features:{symbol}"
        value = json.dumps({
            'features': features,
            'regime': regime,
            'timestamp': datetime.utcnow().isoformat()
        })
        self.redis_client.set(key, value, ex=3600)  # expire after 1 hour
        logger.info(f"[StateStore] Pushed approved features for {symbol} to Redis")

    def list_artifacts(self, phase: Optional[str] = None, agent: Optional[str] = None, status: Optional[ArtifactStatus] = None) -> List[str]:
        """List artifact IDs with optional filtering."""
        results = []
        for aid, info in self._registry.items():
            meta = info.get("metadata", {})
            if phase and meta.get("phase") != phase:
                continue
            if agent and meta.get("agent") != agent:
                continue
            if status and meta.get("status") != status.value:
                continue
            results.append(aid)
        return results

    def get_latest(self, phase: str) -> Optional[PipelineArtifact]:
        """Get the most recent artifact for a given phase."""
        candidates = self.list_artifacts(phase=phase)
        if not candidates:
            return None
        # Sort by created_at descending
        sorted_candidates = sorted(
            candidates,
            key=lambda a: self._registry[a]["metadata"].get("created_at", ""),
            reverse=True,
        )
        return self.load(sorted_candidates[0])

    def get_lineage(self, artifact_id: str) -> List[str]:
        """Trace parent lineage for an artifact."""
        lineage = []
        current = artifact_id
        while current:
            lineage.append(current)
            meta_path = self._meta_path(current)
            if not meta_path.exists():
                break
            with open(meta_path, "r") as f:
                meta = json.load(f)
            current = meta.get("parent_artifact")
        return lineage

    def clear_cache(self):
        self._hot_cache.clear()

    def __repr__(self) -> str:
        return f"StateStore(base={self.base_path}, artifacts={len(self._registry)})"