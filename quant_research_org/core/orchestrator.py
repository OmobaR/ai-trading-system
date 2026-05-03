"""
Orchestrator Agent: The Brain.
Controls execution order and enforces rules:
- Do not proceed if validation fails
- Reject feature expansion without governance approval
- Stop pipeline if any agent fails
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from core.state_store import StateStore, ArtifactStatus
from core.message_bus import MessageBus, Message, MessageType
from core.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

PHASE_ORDER = [
    "data",
    "features",
    "governance",
    "sae",           # conditional
    "regime",
    "filter",
    "strategy",
    "risk",
    "backtest",
    "validation",
    "optimization",
    "deployment",
    "feedback",
]

class Orchestrator:
    """
    Master controller for the multi-agent pipeline.
    Owns the constraint: SEQUENTIAL EXECUTION with VALIDATION GATES.
    """

    def __init__(self, state_store: StateStore, message_bus: MessageBus, config_path: Optional[str] = None):
        self.store = state_store
        self.bus = message_bus
        self.agents: Dict[str, BaseAgent] = {}
        self._current_phase_index = 0
        self._execution_plan: List[str] = []
        self._status_report: Dict[str, Any] = {}
        self._halt_on_failure = True
        self._require_governance = True
        self._config = self._load_config(config_path)

        # Subscribe to key bus events
        self.bus.subscribe(MessageType.ARTIFACT_PRODUCED, self._on_artifact)
        self.bus.subscribe(MessageType.VALIDATION_RESULT, self._on_validation)
        self.bus.subscribe(MessageType.GOVERNANCE_RESULT, self._on_governance)
        self.bus.subscribe(MessageType.PIPELINE_HALT, self._on_halt)

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        if config_path and Path(config_path).exists():
            with open(config_path, "r") as f:
                return json.load(f)
        return {
            "phases": PHASE_ORDER,
            "halt_on_failure": True,
            "require_governance": True,
            "sae_threshold": 20,  # trigger SAE if features > this count
        }

    def register_agent(self, agent: BaseAgent, phase: str):
        """Register an agent to a pipeline phase."""
        self.agents[phase] = agent
        logger.info(f"[Orchestrator] Registered {agent.name} → phase '{phase}'")

    def build_execution_plan(self, skip_phases: Optional[List[str]] = None) -> List[str]:
        """Build a linear execution plan with optional skips."""
        skip = set(skip_phases or [])
        plan = [p for p in self._config["phases"] if p not in skip]
        self._execution_plan = plan
        logger.info(f"[Orchestrator] Execution plan: {' → '.join(plan)}")
        return plan

    def run_phase(self, phase: str, input_artifact_id: Optional[str] = None) -> AgentResult:
        """Execute a single phase by dispatching to its agent."""
        if phase not in self.agents:
            logger.warning(f"[Orchestrator] No agent registered for phase '{phase}'. Skipping.")
            return AgentResult(success=True, message=f"No agent for {phase}; skipped.")

        agent = self.agents[phase]
        logger.info(f"[Orchestrator] Running phase: {phase} (agent={agent.name})")

        # Dispatch task via message bus (synchronous wrapper for now)
        result = agent.execute(input_artifact_id)

        self._status_report[phase] = {
            "agent": agent.name,
            "success": result.success,
            "artifact_id": result.artifact_id,
            "message": result.message,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if not result.success and self._halt_on_failure:
            self.bus.halt(f"Phase '{phase}' failed: {result.message}")
            return result

        # Governance gate after feature production
        if phase == "features" and self._require_governance and "governance" not in self._execution_plan:
            if result.artifact_id:
                self._pending_governance = result.artifact_id
                logger.info(f"[Orchestrator] Governance gate: awaiting approval for {result.artifact_id}")
                gov_agent = self.agents.get("governance")
                if gov_agent:
                    gov_result = gov_agent.execute(result.artifact_id)
                    if not gov_result.success:
                        self.bus.halt(f"Governance rejected features: {gov_result.message}")
                        return gov_result

        # Conditional SAE gate
        if phase == "governance" and result.artifact_id:
            # Check if SAE is recommended
            artifact = self.store.load(result.artifact_id)
            diagnostics = result.diagnostics
            if diagnostics.get("sae_recommended", False):
                logger.info("[Orchestrator] SAE compression recommended by governance.")
                sae_agent = self.agents.get("sae")
                if sae_agent:
                    sae_result = sae_agent.execute(result.artifact_id)
                    if not sae_result.success:
                        self.bus.halt(f"SAE phase failed: {sae_result.message}")
                        return sae_result

        return result

    def run_pipeline(self, input_artifact_id: Optional[str] = None) -> Dict[str, Any]:
        """Run the full execution plan sequentially."""
        logger.info("=" * 60)
        logger.info("[Orchestrator] PIPELINE START")
        logger.info("=" * 60)

        current_input = input_artifact_id
        for phase in self._execution_plan:
            if self.bus.is_halted():
                logger.error("[Orchestrator] Pipeline halted. Aborting.")
                break

            result = self.run_phase(phase, current_input)
            if result.success and result.artifact_id:
                current_input = result.artifact_id
            else:
                logger.error(f"[Orchestrator] Phase {phase} did not produce output.")
                if self._halt_on_failure:
                    break

        final_status = "HALTED" if self.bus.is_halted() else "COMPLETE"
        logger.info("=" * 60)
        logger.info(f"[Orchestrator] PIPELINE {final_status}")
        logger.info("=" * 60)

        return {
            "status": final_status,
            "plan": self._execution_plan,
            "report": self._status_report,
            "final_artifact_id": current_input,
        }

    def _on_artifact(self, message: Message):
        payload = message.payload
        logger.info(f"[Orchestrator] Artifact produced: {payload.get('artifact_id')} by {message.sender}")

    def _on_validation(self, message: Message):
        payload = message.payload
        approved = payload.get("approved", False)
        artifact_id = payload.get("artifact_id")
        if not approved:
            self.bus.halt(f"Validation failed for {artifact_id}")
        else:
            self.store.update_status(artifact_id, ArtifactStatus.VALIDATED)

    def _on_governance(self, message: Message):
        payload = message.payload
        approved = payload.get("approved", False)
        artifact_id = payload.get("artifact_id")
        if not approved:
            self.bus.halt(f"Governance rejected {artifact_id}")
        else:
            self.store.update_status(artifact_id, ArtifactStatus.APPROVED)

    def _on_halt(self, message: Message):
        reason = message.payload.get("reason", "unknown")
        logger.critical(f"[Orchestrator] HALT received: {reason}")

    def get_status_report(self) -> Dict[str, Any]:
        return self._status_report
