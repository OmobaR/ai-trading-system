"""
Resume pipeline from saved regime Parquet files.
Preserves all feature columns needed for strategy signals.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "quant_research_org"))

import logging
import pandas as pd
import numpy as np
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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def apply_filter(df: pd.DataFrame, min_confidence=0.4, filter_transitions=False, filter_range=False):
    mask = pd.Series(True, index=df.index)
    if "regime_confidence" in df.columns:
        mask &= df["regime_confidence"] >= min_confidence
    if filter_transitions and "transition_flag" in df.columns:
        mask &= ~df["transition_flag"]
    if filter_range and "regime" in df.columns:
        mask &= df["regime"] != "range"
    return df[mask].copy()

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Generate signals using ALL available feature columns."""
    out = df.copy()
    directions = []
    confidences = []
    rationales = []

    for i in range(len(df)):
        row = df.iloc[i]
        regime = row.get("regime", "unknown")
        base_conf = row.get("regime_confidence", 0.0)
        rsi = row.get("rsi_14", 50.0)
        pos = row.get("position_in_yearly_range", 0.5)
        close = row.get("close", np.nan)
        ema_7 = row.get("ema_7", np.nan)
        ema_21 = row.get("ema_21", np.nan)

        direction = 0
        rationale = ""

        if regime == "trend_continuation":
            if not np.isnan(ema_7) and not np.isnan(ema_21):
                if ema_7 > ema_21 and rsi < 70:
                    direction = 1
                    rationale = "Trend up, EMA7>EMA21, RSI not overbought"
                elif ema_7 < ema_21 and rsi > 30:
                    direction = -1
                    rationale = "Trend down, EMA7<EMA21, RSI not oversold"
            else:
                rationale = "Missing EMA data"

        elif regime == "breakout":
            if not np.isnan(ema_7) and not np.isnan(close):
                if close > ema_7 * 1.01:
                    direction = 1
                    rationale = "Breakout continuation, price above EMA7"
                elif close < ema_7 * 0.99:
                    direction = -1
                    rationale = "Breakout, price below EMA7"

        elif regime == "range":
            if pos > 0.7 and rsi > 60:
                direction = -1
                rationale = "Range, near top, RSI elevated"
            elif pos < 0.3 and rsi < 40:
                direction = 1
                rationale = "Range, near bottom, RSI depressed"
            else:
                rationale = "Range, mid-zone, no edge"

        elif regime == "weak_trend":
            if not np.isnan(ema_7) and not np.isnan(ema_21):
                if ema_7 > ema_21:
                    direction = 1
                    rationale = "Weak trend up, following with reduced confidence"
                elif ema_7 < ema_21:
                    direction = -1
                    rationale = "Weak trend down, following with reduced confidence"
            else:
                rationale = "Weak trend, no EMA direction"

        elif regime == "transition":
            # Optionally follow EMA direction with very low confidence
            if not np.isnan(ema_7) and not np.isnan(ema_21):
                if ema_7 > ema_21:
                    direction = 1
                    rationale = "Transition but EMA7>EMA21, lean long"
                elif ema_7 < ema_21:
                    direction = -1
                    rationale = "Transition but EMA7<EMA21, lean short"
            else:
                rationale = "Transition, hold"

        else:
            rationale = f"Unknown regime '{regime}'"

        # Adjust signal confidence based on regime
        if direction != 0:
            if regime in ("weak_trend", "transition"):
                sig_conf = base_conf * 0.5
            else:
                sig_conf = base_conf * 0.8
        else:
            sig_conf = base_conf * 0.3

        directions.append(direction)
        confidences.append(round(sig_conf, 3))
        rationales.append(rationale)

    out["direction"] = directions
    out["confidence"] = confidences
    out["rationale"] = rationales
    return out

def main():
    # 1. Load all regime Parquet files (they contain all original feature columns)
    regime_dir = Path("data/processed/regime")
    regime_files = list(regime_dir.glob("*_regime.parquet"))
    if not regime_files:
        logger.error("No regime files found. Run regime_agent first.")
        return
    logger.info(f"Found {len(regime_files)} regime files.")

    all_filtered = []
    for f in regime_files:
        df = pd.read_parquet(f)
        filtered = apply_filter(df, min_confidence=0.4, filter_transitions=False, filter_range=False)
        if not filtered.empty:
            all_filtered.append(filtered)
    if not all_filtered:
        logger.error("No rows after filtering.")
        return
    filtered_df = pd.concat(all_filtered, ignore_index=True)
    logger.info(f"After filter: {len(filtered_df)} rows.")

    # 2. Generate signals (keeps all columns, adds direction, confidence)
    signals_df = generate_signals(filtered_df)

    # 3. Save signals to Parquet (one per symbol) for risk agent
    strategy_dir = Path("data/processed/strategy_resumed_corrected")
    strategy_dir.mkdir(parents=True, exist_ok=True)
    signal_files = []
    for symbol, grp in signals_df.groupby("symbol"):
        out_path = strategy_dir / f"{symbol}_signals.parquet"
        grp.to_parquet(out_path, index=False)
        signal_files.append(str(out_path))
    logger.info(f"Saved {len(signal_files)} signal files.")

    # 4. Create a mock strategy artifact
    store = StateStore(base_path="./data/processed")
    message_bus = MessageBus()
    mock_id = "mock_strategy_corrected"
    meta = ArtifactMetadata(agent="strategy_agent", phase="strategy")
    temp_artifact = PipelineArtifact(
        artifact_id=mock_id,
        name="strategy_signals",
        data={"file_paths": signal_files},
        metadata=meta
    )
    store.save(temp_artifact)

    # 5. Run downstream agents (risk → backtest → validation → optimization → deployment → feedback)
    risk_agent = RiskAgent(store, message_bus)
    bt_agent = BacktestAgent(store, message_bus)
    val_agent = ValidationAgent(store, message_bus)
    opt_agent = OptimizationAgent(store, message_bus)
    dep_agent = DeploymentAgent(store, message_bus)
    fb_agent = FeedbackAgent(store, message_bus)

    logger.info("Running risk agent...")
    risk_result = risk_agent.execute(input_artifact_id=mock_id)
    if not risk_result.success:
        logger.error(f"Risk failed: {risk_result.message}")
        return
    risk_id = risk_result.artifact_id

    logger.info("Running backtest...")
    bt_result = bt_agent.execute(input_artifact_id=risk_id)
    if not bt_result.success:
        logger.error(f"Backtest failed: {bt_result.message}")
        return
    bt_id = bt_result.artifact_id

    logger.info("Running validation...")
    val_result = val_agent.execute(input_artifact_id=bt_id)
    if not val_result.success:
        logger.error(f"Validation failed: {val_result.message}")
        return
    val_id = val_result.artifact_id

    logger.info("Running optimization...")
    opt_result = opt_agent.execute(input_artifact_id=val_id)
    if not opt_result.success:
        logger.error(f"Optimization failed: {opt_result.message}")
        return
    opt_id = opt_result.artifact_id

    logger.info("Running deployment...")
    dep_result = dep_agent.execute(input_artifact_id=opt_id)
    if not dep_result.success:
        logger.error(f"Deployment failed: {dep_result.message}")
        return

    logger.info("Running feedback...")
    fb_result = fb_agent.execute(input_artifact_id=dep_result.artifact_id, backtest_artifact_id=bt_id)
    if not fb_result.success:
        logger.error(f"Feedback failed: {fb_result.message}")

    logger.info("\n✅ Pipeline completed with trade signals.")
    logger.info(f"Backtest artifact: {bt_id}")
    logger.info("Deployment EA: src/execution/mql5/AutoGen_RegimeEA_v1.mq5")

if __name__ == "__main__":
    main()