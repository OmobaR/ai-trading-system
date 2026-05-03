"""
Quant Research Organization — Multi-Agent Trading Pipeline
Entry point. Builds the orchestrator, registers agents, and runs the pipeline.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from core.state_store import StateStore
from core.message_bus import MessageBus
from core.orchestrator import Orchestrator

from agents.data_agent import DataAgent
from agents.feature_agent import FeatureAgent
from agents.governance_agent import GovernanceAgent
from agents.regime_agent import RegimeAgent
from agents.filter_agent import FilterAgent
from agents.strategy_agent import StrategyAgent
from agents.risk_agent import RiskAgent
from agents.backtest_agent import BacktestAgent
from agents.validation_agent import ValidationAgent
from agents.optimization_agent import OptimizationAgent
from agents.deployment_agent import DeploymentAgent
from agents.feedback_agent import FeedbackAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")

def build_pipeline(config: dict | None = None) -> Orchestrator:
    store = StateStore(base_path="./data/processed")
    bus = MessageBus(log_path="./data/processed/message_bus.log")
    orch = Orchestrator(store, bus, config_path=config)

    # Register all agents to their phases
    orch.register_agent(DataAgent(store, bus), "data")
    orch.register_agent(FeatureAgent(store, bus), "features")
    orch.register_agent(GovernanceAgent(store, bus), "governance")
    orch.register_agent(RegimeAgent(store, bus), "regime")
    orch.register_agent(FilterAgent(store, bus), "filter")
    orch.register_agent(StrategyAgent(store, bus), "strategy")
    orch.register_agent(RiskAgent(store, bus), "risk")
    orch.register_agent(BacktestAgent(store, bus), "backtest")
    orch.register_agent(ValidationAgent(store, bus), "validation")
    orch.register_agent(OptimizationAgent(store, bus), "optimization")
    orch.register_agent(DeploymentAgent(store, bus), "deployment")
    orch.register_agent(FeedbackAgent(store, bus), "feedback")

    return orch

def run_step_1(orchestrator: Orchestrator) -> dict:
    """
    STEP 1: Data → Features → Governance
    """
    logger.info("\n" + "=" * 70)
    logger.info("STEP 1: Data → Feature → Governance")
    logger.info("=" * 70)

    plan = orchestrator.build_execution_plan(skip_phases=[
        "sae", "regime", "filter", "strategy", "risk",
        "backtest", "validation", "optimization", "deployment", "feedback"
    ])
    return orchestrator.run_pipeline()

def run_step_2(orchestrator: Orchestrator, governance_artifact_id: str | None = None) -> dict:
    """
    STEP 2: Regime
    """
    logger.info("\n" + "=" * 70)
    logger.info("STEP 2: Regime Classification")
    logger.info("=" * 70)

    plan = orchestrator.build_execution_plan(skip_phases=[
        "data", "features", "governance", "sae",
        "filter", "strategy", "risk",
        "backtest", "validation", "optimization", "deployment", "feedback"
    ])
    return orchestrator.run_pipeline(input_artifact_id=governance_artifact_id)

def run_full_pipeline(orchestrator: Orchestrator) -> dict:
    """
    Full sequential pipeline.
    """
    logger.info("\n" + "=" * 70)
    logger.info("FULL PIPELINE RUN")
    logger.info("=" * 70)

    plan = orchestrator.build_execution_plan()
    return orchestrator.run_pipeline()

def main():
    logger.info("QuantResearchOrg Multi-Agent Trading Pipeline starting...")

    orch = build_pipeline()

    # --- STEP 1: Data → Feature → Governance ---
    result_1 = run_step_1(orch)
    logger.info(f"STEP 1 result: {result_1['status']}")
    if result_1["status"] != "COMPLETE":
        logger.error("STEP 1 failed. Halting.")
        sys.exit(1)

    gov_artifact = None
    for phase, info in result_1["report"].items():
        if phase == "governance" and info.get("artifact_id"):
            gov_artifact = info["artifact_id"]
            break

    if not gov_artifact:
        logger.error("No governance artifact found. Cannot proceed to STEP 2.")
        sys.exit(1)

    # --- STOP → VALIDATE checkpoint ---
    logger.info("\n" + "=" * 70)
    logger.info("STOP → VALIDATE: Inspecting STEP 1 outputs before proceeding")
    logger.info("=" * 70)
    store = orch.store
    data_art = store.get_latest("data")
    feature_art = store.get_latest("features")
    gov_art = store.get_latest("governance")

    logger.info(f"  Data artifact:      {data_art.artifact_id if data_art else 'None'} ({data_art.metadata.notes if data_art else ''})")
    logger.info(f"  Feature artifact:   {feature_art.artifact_id if feature_art else 'None'} ({feature_art.metadata.notes if feature_art else ''})")
    logger.info(f"  Governance artifact:{gov_art.artifact_id if gov_art else 'None'} ({gov_art.metadata.notes if gov_art else ''})")

    # Check governance approval by inspecting feature artifact status
    feature_approved = False
    if feature_art and feature_art.metadata.status.value == "approved":
        feature_approved = True
    elif gov_art and gov_art.data and isinstance(gov_art.data, dict):
        approved_features = gov_art.data.get("approved_features", [])
        feature_approved = len(approved_features) > 0

    if not feature_approved:
        logger.error("Governance did not approve features. Pipeline halted at STOP → VALIDATE.")
        sys.exit(1)

    logger.info("STOP → VALIDATE: PASSED. Proceeding to STEP 2.")

    # --- STEP 2: Regime ---
    result_2 = run_step_2(orch, governance_artifact_id=gov_artifact)
    logger.info(f"STEP 2 result: {result_2['status']}")
    if result_2["status"] != "COMPLETE":
        logger.error("STEP 2 failed. Halting.")
        sys.exit(1)

    regime_artifact = result_2.get("final_artifact_id")
    if not regime_artifact:
        logger.error("No regime artifact produced.")
        sys.exit(1)

    logger.info(f"\nRegime artifact: {regime_artifact}")
    regime_art = store.load(regime_artifact)
    logger.info(f"  Notes: {regime_art.metadata.notes}")

    # --- OPTIONAL: Full pipeline from here ---
    logger.info("\n" + "=" * 70)
    logger.info("STEP 1 + STEP 2 COMPLETE. Ready for full downstream pipeline.")
    logger.info("To run full pipeline, call: run_full_pipeline(orchestrator)")
    logger.info("=" * 70)

    # Demonstrate full pipeline continuation from regime artifact
    logger.info("\nRunning full downstream pipeline from regime artifact...")
    orch_full = build_pipeline()
    plan = orch_full.build_execution_plan(skip_phases=["data", "features", "governance", "sae", "regime"])
    result_full = orch_full.run_pipeline(input_artifact_id=regime_artifact)
    logger.info(f"Full downstream result: {result_full['status']}")
    logger.info(f"Final artifact: {result_full.get('final_artifact_id')}")

    logger.info("\n" + "=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 70)

if __name__ == "__main__":
    main()
