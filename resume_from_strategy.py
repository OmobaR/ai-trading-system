"""
Resume pipeline from strategy output (already generated Parquet files).
Run this script from the project root.
"""
import sys
from pathlib import Path

# Add project root and quant_research_org to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "quant_research_org"))

import logging
from dotenv import load_dotenv

from core.state_store import StateStore, PipelineArtifact, ArtifactMetadata
from core.message_bus import MessageBus
from agents.risk_agent import RiskAgent
from agents.backtest_agent import BacktestAgent
from agents.validation_agent import ValidationAgent
from agents.optimization_agent import OptimizationAgent
from agents.deployment_agent import DeploymentAgent
from agents.feedback_agent import FeedbackAgent

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # 1. Initialize store and message bus
    store = StateStore(base_path="./data/processed")
    message_bus = MessageBus()
    
    # 2. Find all strategy Parquet files
    strategy_dir = Path("data/processed/strategy")
    signal_files = [str(p) for p in strategy_dir.glob("*_signals.parquet")]
    if not signal_files:
        logger.error("No strategy Parquet files found. Run strategy agent first.")
        return
    
    logger.info(f"Found {len(signal_files)} signal files.")
    
    # 3. Create a temporary artifact for strategy output
    mock_id = "mock_strategy_artifact"
    meta = ArtifactMetadata(agent="strategy_agent", phase="strategy")
    temp_artifact = PipelineArtifact(
        artifact_id=mock_id,
        name="strategy_signals",
        data={"file_paths": signal_files},
        metadata=meta
    )
    store.save(temp_artifact)
    
    # 4. Initialize agents
    risk_agent = RiskAgent(store, message_bus)
    bt_agent = BacktestAgent(store, message_bus)
    val_agent = ValidationAgent(store, message_bus)
    opt_agent = OptimizationAgent(store, message_bus)
    dep_agent = DeploymentAgent(store, message_bus)
    fb_agent = FeedbackAgent(store, message_bus)
    
    # 5. Run risk
    logger.info("Running risk agent...")
    risk_result = risk_agent.execute(input_artifact_id=mock_id)
    if not risk_result.success:
        logger.error(f"Risk failed: {risk_result.message}")
        return
    risk_artifact_id = risk_result.artifact_id
    logger.info(f"Risk artifact: {risk_artifact_id}")
    
    # 6. Backtest
    logger.info("Running backtest agent...")
    bt_result = bt_agent.execute(input_artifact_id=risk_artifact_id)
    if not bt_result.success:
        logger.error(f"Backtest failed: {bt_result.message}")
        return
    bt_artifact_id = bt_result.artifact_id
    logger.info(f"Backtest artifact: {bt_artifact_id}")
    
    # 7. Validation
    logger.info("Running validation agent...")
    val_result = val_agent.execute(input_artifact_id=bt_artifact_id)
    if not val_result.success:
        logger.error(f"Validation failed: {val_result.message}")
        return
    val_artifact_id = val_result.artifact_id
    logger.info(f"Validation artifact: {val_artifact_id}")
    
    # 8. Optimization
    logger.info("Running optimization agent...")
    opt_result = opt_agent.execute(input_artifact_id=val_artifact_id)
    if not opt_result.success:
        logger.error(f"Optimization failed: {opt_result.message}")
        return
    opt_artifact_id = opt_result.artifact_id
    logger.info(f"Optimization artifact: {opt_artifact_id}")
    
    # 9. Deployment
    logger.info("Running deployment agent...")
    dep_result = dep_agent.execute(input_artifact_id=opt_artifact_id)
    if not dep_result.success:
        logger.error(f"Deployment failed: {dep_result.message}")
        return
    dep_artifact_id = dep_result.artifact_id
    logger.info(f"Deployment artifact: {dep_artifact_id}")
    
    # 10. Feedback
    logger.info("Running feedback agent...")
    fb_result = fb_agent.execute(input_artifact_id=dep_artifact_id, backtest_artifact_id=bt_artifact_id)
    if not fb_result.success:
        logger.error(f"Feedback failed: {fb_result.message}")
        return
    fb_artifact_id = fb_result.artifact_id
    logger.info(f"Feedback artifact: {fb_artifact_id}")
    
    logger.info("✅ Pipeline resumed successfully from strategy output.")
    logger.info(f"Final backtest report artifact: {bt_artifact_id}")
    logger.info("Deployment EA written to: src/execution/mql5/AutoGen_RegimeEA_v1.mq5")

if __name__ == "__main__":
    main()