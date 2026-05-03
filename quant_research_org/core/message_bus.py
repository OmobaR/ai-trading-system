"""
Core: Message Bus for inter-agent communication.
Lightweight, file-backed event log for pipeline traceability.
"""
from __future__ import annotations

import json
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class MessageType(str, Enum):
    TASK_ASSIGNMENT = "task_assignment"
    ARTIFACT_PRODUCED = "artifact_produced"
    VALIDATION_REQUEST = "validation_request"
    VALIDATION_RESULT = "validation_result"
    GOVERNANCE_REQUEST = "governance_request"
    GOVERNANCE_RESULT = "governance_result"
    PIPELINE_HALT = "pipeline_halt"
    PIPELINE_RESUME = "pipeline_resume"
    FEEDBACK = "feedback"
    SYSTEM_HEALTH = "system_health"

@dataclass
class Message:
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    sender: str = "orchestrator"
    recipient: str = "all"
    message_type: MessageType = MessageType.TASK_ASSIGNMENT
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None  # ties related messages together

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["message_type"] = self.message_type.value
        return d

class MessageBus:
    """
    In-memory + file-backed message bus for agent coordination.
    - Subscribers register callbacks per message type
    - All messages appended to event log for audit
    """

    def __init__(self, log_path: str = "./data/processed/message_bus.log"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._subscribers: Dict[MessageType, List[Callable[[Message], None]]] = {mt: [] for mt in MessageType}
        self._history: List[Message] = []
        self._halted = False

    def subscribe(self, message_type: MessageType, callback: Callable[[Message], None]):
        self._subscribers[message_type].append(callback)

    def publish(self, message: Message):
        if self._halted and message.message_type not in {MessageType.PIPELINE_RESUME, MessageType.SYSTEM_HEALTH}:
            logger.warning(f"[MessageBus] Dropped message {message.message_id}: pipeline halted.")
            return

        self._history.append(message)
        self._append_to_log(message)

        for callback in self._subscribers.get(message.message_type, []):
            try:
                callback(message)
            except Exception as e:
                logger.error(f"[MessageBus] Subscriber error for {message.message_type}: {e}")

        logger.debug(f"[MessageBus] {message.sender} → {message.recipient} [{message.message_type.value}]")

    def _append_to_log(self, message: Message):
        with open(self.log_path, "a") as f:
            f.write(json.dumps(message.to_dict(), default=str) + "\n")

    def halt(self, reason: str = ""):
        self._halted = True
        logger.critical(f"[MessageBus] PIPELINE HALTED. Reason: {reason}")
        self.publish(Message(
            sender="orchestrator",
            recipient="all",
            message_type=MessageType.PIPELINE_HALT,
            payload={"reason": reason},
        ))

    def resume(self):
        self._halted = False
        logger.info("[MessageBus] Pipeline resumed.")
        self.publish(Message(
            sender="orchestrator",
            recipient="all",
            message_type=MessageType.PIPELINE_RESUME,
            payload={},
        ))

    def get_history(self, correlation_id: Optional[str] = None) -> List[Message]:
        if correlation_id:
            return [m for m in self._history if m.correlation_id == correlation_id]
        return list(self._history)

    def is_halted(self) -> bool:
        return self._halted
