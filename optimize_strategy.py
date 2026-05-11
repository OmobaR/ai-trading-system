"""
Sequential parameter optimization for the strategy.
Tests on a subset: 10 symbols, last 100 days of M5 data (~20k bars per symbol).
Optimizes 4 parameters using Sharpe as metric.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import logging
from itertools import product

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "quant_research_org"))

from core.state_store import StateStore, PipelineArtifact, ArtifactMetadata
from core.message_bus import MessageBus
from agents.risk_agent import RiskAgent
from agents.backtest_agent import BacktestAgent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ----- Configuration -----
SYMBOLS = [
    "GainX 600", "PainX 600", "FlipX 3", "FX Vol 40", "SFX Vol 40",
    "TrendX 1200", "SwitchX 1200", "BreakX 1200", "PlusX 1", "QuadX"
]
DAYS = 100   # last N days of data
BARS = DAYS * 288   # M5: ~288 bars per day = 28,800 bars for 100 days

# Parameter ranges
TREND_THRESHOLDS = [0.002, 0.005, 0.01, 0.02, 0.03]
VOLATILITY_MULTS  = [1.2, 1.5, 2.0, 2.5, 3.0]
MIN_CONFIDENCES   = [0.3, 0.4, 0.5, 0.6, 0.7]
RSI_UPPER_VALS =    [70, 75, 80, 85, 90]   # oversold = 100 - upper (symmetrical)

# ----- Strategy function (parameterised) -----
def generate_signals(df, trend_thresh=0.005, vol_mult=1.5, min_conf=0.4, rsi_upper=70):
    df = df.copy()
    # Trend strength from ema_7_21_ratio
    ratio = df["ema_7_21_ratio"]
    trend = (ratio - 1.0) / trend_thresh
    trend = trend.clip(-1, 1)
    base_conf = trend.abs() * 0.8 + 0.2

    # Volatility filter
    atr = df["atr_14"]
    median_atr = atr.rolling(100, min_periods=10).median()
    vol_ok = atr < (median_atr * vol_mult)
    vol_ok = vol_ok.fillna(True)

    direction = np.sign(trend)
    confidence = base_conf * trend.abs()
    confidence = confidence.clip(min_conf, 0.95)

    # Mean‑reversion (only when trend weak)
    rsi_lower = 100 - rsi_upper
    weak_mask = (trend.abs() < 0.2) & (df["position_in_yearly_range"] < 0.3) & (df["rsi_14"] < rsi_lower)
    direction[weak_mask] = 1
    confidence[weak_mask] = 0.5
    weak_mask_sell = (trend.abs() < 0.2) & (df["position_in_yearly_range"] > 0.7) & (df["rsi_14"] > rsi_upper)
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

def evaluate(params, regime_files):
    trend_thresh, vol_mult, min_conf, rsi_upper = params
    all_signals = []
    for f in regime_files:
        df = pd.read_parquet(f)
        # Take last BARS rows
        df_subset = df.tail(BARS).copy()
        if df_subset.empty:
            continue
        signals = generate_signals(df_subset, trend_thresh, vol_mult, min_conf, rsi_upper)
        all_signals.append(signals)
    if not all_signals:
        return -999
    signals_df = pd.concat(all_signals, ignore_index=True)

    # Run risk and backtest
    store = StateStore(base_path="./data/processed")
    message_bus = MessageBus()
    mock_id = f"opt_{trend_thresh}_{vol_mult}_{min_conf}_{rsi_upper}"
    meta = ArtifactMetadata(agent="strategy_agent", phase="strategy")
    temp_artifact = PipelineArtifact(artifact_id=mock_id, name="opt_signals", data={}, metadata=meta)
    # We need to save signals to files first
    test_dir = Path("data/processed/opt_temp")
    test_dir.mkdir(exist_ok=True)
    signal_files = []
    for symbol, grp in signals_df.groupby("symbol"):
        out_path = test_dir / f"{symbol}_signals.parquet"
        grp.to_parquet(out_path, index=False)
        signal_files.append(str(out_path))
    temp_artifact.data = {"file_paths": signal_files}
    store.save(temp_artifact, overwrite=True)

    risk_agent = RiskAgent(store, message_bus, capital=10000.0, max_risk_per_trade=0.02)
    risk_result = risk_agent.execute(input_artifact_id=mock_id)
    if not risk_result.success:
        return -999
    bt_agent = BacktestAgent(store, message_bus)
    bt_result = bt_agent.execute(input_artifact_id=risk_result.artifact_id)
    if not bt_result.success:
        return -999
    art = store.load(bt_result.artifact_id)
    return art.data['report']['sharpe']

def main():
    # Load regime files for selected symbols
    regime_dir = Path("data/processed/regime")
    all_files = list(regime_dir.glob("*_regime.parquet"))
    sym_stems = [f.stem.replace("_regime", "") for f in all_files]
    regime_files = []
    for sym in SYMBOLS:
        # Find file matching symbol
        for f in all_files:
            if f.stem.startswith(sym):
                regime_files.append(f)
                break
    if not regime_files:
        logger.error("No regime files found for selected symbols")
        return
    logger.info(f"Using {len(regime_files)} symbols: {[f.stem for f in regime_files]}")

    # Sequential optimization (fix one param, vary another)
    best_sharpe = -999
    best_params = None

    # 1. Optimize trend_threshold
    logger.info("Optimizing trend_threshold...")
    for trend in TREND_THRESHOLDS:
        params = (trend, 1.5, 0.4, 70)
        sharpe = evaluate(params, regime_files)
        logger.info(f"trend={trend} -> Sharpe={sharpe:.3f}")
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_params = params

    # 2. Optimize volatility_mult
    logger.info("Optimizing volatility_mult...")
    for vol in VOLATILITY_MULTS:
        params = (best_params[0], vol, best_params[2], best_params[3])
        sharpe = evaluate(params, regime_files)
        logger.info(f"vol_mult={vol} -> Sharpe={sharpe:.3f}")
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_params = params

    # 3. Optimize min_confidence
    logger.info("Optimizing min_confidence...")
    for conf in MIN_CONFIDENCES:
        params = (best_params[0], best_params[1], conf, best_params[3])
        sharpe = evaluate(params, regime_files)
        logger.info(f"min_conf={conf} -> Sharpe={sharpe:.3f}")
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_params = params

    # 4. Optimize rsi_upper
    logger.info("Optimizing rsi_upper...")
    for rsi in RSI_UPPER_VALS:
        params = (best_params[0], best_params[1], best_params[2], rsi)
        sharpe = evaluate(params, regime_files)
        logger.info(f"rsi_upper={rsi} -> Sharpe={sharpe:.3f}")
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_params = params

    logger.info(f"\n✅ Best parameters: trend_threshold={best_params[0]}, volatility_mult={best_params[1]}, min_confidence={best_params[2]}, rsi_upper={best_params[3]}, Sharpe={best_sharpe:.3f}")

    # Save to file for later use
    with open("best_params.txt", "w") as f:
        f.write(f"trend_threshold={best_params[0]}\n")
        f.write(f"volatility_mult={best_params[1]}\n")
        f.write(f"min_confidence={best_params[2]}\n")
        f.write(f"rsi_upper={best_params[3]}\n")
    print("Saved to best_params.txt")

if __name__ == "__main__":
    main()