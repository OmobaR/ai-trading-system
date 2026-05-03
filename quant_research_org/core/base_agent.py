"""
Core: Base Agent class enforcing the constraint-ownership model.
Each agent owns a constraint, not the system.
"""
from __future__ import annotations

import uuid
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from dataclasses import dataclass

from core.state_store import StateStore, ArtifactMetadata, ArtifactStatus, PipelineArtifact
from core.message_bus import MessageBus, Message, MessageType

logger = logging.getLogger(__name__)

@dataclass
class AgentResult:
    success: bool
    artifact_id: Optional[str] = None
    message: str = ""
    diagnostics: Dict[str, Any] = None
    halt_pipeline: bool = False

    def __post_init__(self):
        if self.diagnostics is None:
            self.diagnostics = {}

class BaseAgent(ABC):
    """
    Abstract base for all quant research agents.
    - Receives tasks via MessageBus
    - Produces artifacts to StateStore
    - Reports results back to Orchestrator
    """

    def __init__(self, name: str, state_store: StateStore, message_bus: MessageBus):
        self.name = name
        self.store = state_store
        self.bus = message_bus
        self._running = False

    def _produce_artifact(self, name: str, data: Any, phase: str, parent_artifact: Optional[str] = None, tags: Optional[List[str]] = None, notes: str = "") -> str:
        """Helper to package output as a versioned artifact."""
        artifact_id = f"{phase}_{self.name}_{uuid.uuid4().hex[:8]}"
        metadata = ArtifactMetadata(
            agent=self.name,
            phase=phase,
            parent_artifact=parent_artifact,
            tags=tags or [],
            notes=notes,
        )
        artifact = PipelineArtifact(
            artifact_id=artifact_id,
            name=name,
            data=data,
            metadata=metadata,
        )
        self.store.save(artifact)
        self.bus.publish(Message(
            sender=self.name,
            recipient="orchestrator",
            message_type=MessageType.ARTIFACT_PRODUCED,
            payload={
                "artifact_id": artifact_id,
                "phase": phase,
                "parent_artifact": parent_artifact,
            },
            correlation_id=artifact_id,
        ))
        return artifact_id

    def _request_validation(self, artifact_id: str, validator_name: str = "validation_agent"):
        self.bus.publish(Message(
            sender=self.name,
            recipient=validator_name,
            message_type=MessageType.VALIDATION_REQUEST,
            payload={"artifact_id": artifact_id, "phase": self.name},
            correlation_id=artifact_id,
        ))

    def _request_governance(self, artifact_id: str):
        self.bus.publish(Message(
            sender=self.name,
            recipient="governance_agent",
            message_type=MessageType.GOVERNANCE_REQUEST,
            payload={"artifact_id": artifact_id, "phase": self.name},
            correlation_id=artifact_id,
        ))

    @abstractmethod
    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        """Main execution entry point. Override in subclasses."""
        pass

    def on_task(self, message: Message):
        """Default task handler wired to MessageBus."""
        if message.recipient not in (self.name, "all"):
            return
        payload = message.payload
        input_id = payload.get("input_artifact_id")
        logger.info(f"[{self.name}] Received task (correlation={message.correlation_id})")
        result = self.execute(input_id, **payload.get("params", {}))
        if result.halt_pipeline and not result.success:
            self.bus.halt(f"{self.name} failed: {result.message}")

    def start(self):
        """Register with message bus."""
        self.bus.subscribe(MessageType.TASK_ASSIGNMENT, self.on_task)
        self._running = True
        logger.info(f"[{self.name}] Agent started and listening.")

    def stop(self):
        self._running = False
        logger.info(f"[{self.name}] Agent stopped.")
