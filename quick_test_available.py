"""
Quick test using only symbols that have existing regime files.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "quant_research_org"))

import pandas as pd
import numpy as np
import logging
from core.state_store import StateStore, PipelineArtifact, ArtifactMetadata
from core.message_bus import MessageBus
from agents.risk_agent import RiskAgent
from agents.backtest_agent import BacktestAgent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Use ema_7_21_ratio to compute trend strength
    ratio = df.get("ema_7_21_ratio", 1.0)
    trend = (ratio - 1.0) / 0.05
    trend = trend.clip(-1, 1)
    base_conf = trend.abs() * 0.8 + 0.2

    # Volatility filter
    atr = df.get("atr_14", 0.01)
    median_atr = atr.rolling(100, min_periods=10).median()
    vol_ok = atr < (median_atr * 1.5)
    vol_ok = vol_ok.fillna(True)

    direction = np.sign(trend).astype(int)
    confidence = base_conf * trend.abs()
    confidence = confidence.clip(0.05, 0.95)

    # Mean-reversion in weak trend
    weak_mask = (trend.abs() < 0.2) & (df["position_in_yearly_range"] < 0.3) & (df["rsi_14"] < 40)
    direction[weak_mask] = 1
    confidence[weak_mask] = 0.5
    weak_mask_sell = (trend.abs() < 0.2) & (df["position_in_yearly_range"] > 0.7) & (df["rsi_14"] > 60)
    direction[weak_mask_sell] = -1
    confidence[weak_mask_sell] = 0.5

    direction[~vol_ok] = 0
    confidence[~vol_ok] = 0.0

    df["direction"] = direction.astype(int)
    df["confidence"] = confidence.round(3)
    keep = ["time", "symbol", "open", "high", "low", "close", "volume",
            "direction", "confidence", "atr_14", "regime", "regime_confidence"]
    keep = [c for c in keep if c in df.columns]
    return df[keep]

def main():
    regime_dir = Path("data/processed/regime")
    all_files = list(regime_dir.glob("*_regime.parquet"))
    if not all_files:
        logger.error("No regime files found")
        return
    logger.info(f"Found {len(all_files)} regime files")

    # Use all available symbols
    all_signals = []
    for f in all_files:
        symbol = f.stem.replace("_regime", "")
        logger.info(f"Processing {symbol}...")
        df = pd.read_parquet(f)
        # Use last 10000 rows for test
        df_subset = df.tail(10000).copy()
        if df_subset.empty:
            continue
        signals = generate_signals(df_subset)
        all_signals.append(signals)

    if not all_signals:
        logger.error("No signals generated")
        return
    signals_df = pd.concat(all_signals, ignore_index=True)

    # Save signals to Parquet
    test_dir = Path("data/processed/quick_test")
    test_dir.mkdir(parents=True, exist_ok=True)
    signal_files = []
    for symbol, grp in signals_df.groupby("symbol"):
        out_path = test_dir / f"{symbol}_signals.parquet"
        grp.to_parquet(out_path, index=False)
        signal_files.append(str(out_path))

    # Run risk and backtest
    store = StateStore(base_path="./data/processed")
    message_bus = MessageBus()
    mock_id = "quick_test_strategy"
    meta = ArtifactMetadata(agent="strategy_agent", phase="strategy")
    temp_artifact = PipelineArtifact(artifact_id=mock_id, name="quick_test_signals", data={"file_paths": signal_files}, metadata=meta)
    store.save(temp_artifact, overwrite=True)

    risk_agent = RiskAgent(store, message_bus, capital=10000.0, max_risk_per_trade=0.02)
    risk_result = risk_agent.execute(input_artifact_id=mock_id)
    if not risk_result.success:
        logger.error(f"Risk failed: {risk_result.message}")
        return
    risk_id = risk_result.artifact_id

    bt_agent = BacktestAgent(store, message_bus)
    bt_result = bt_agent.execute(input_artifact_id=risk_id)
    if not bt_result.success:
        logger.error(f"Backtest failed: {bt_result.message}")
        return
    bt_id = bt_result.artifact_id

    art = store.load(bt_id)
    report = art.data['report']
    print("\n=== BACKTEST REPORT (available symbols, last 10000 bars) ===")
    for k, v in report.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()
