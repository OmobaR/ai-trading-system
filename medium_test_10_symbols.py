"""
Medium scale test on 10 representative symbols (last 10000 bars) with volatility filter.
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

# Representative symbols (one per category)
SYMBOLS = [
    "GainX 600",
    "PainX 600",
    "FlipX 3",
    "FX Vol 40",
    "SFX Vol 40",
    "TrendX 1200",
    "SwitchX 1200",
    "BreakX 1200",
    "PlusX 1",
    "QuadX",
]

def generate_signals_with_volatility_filter(df: pd.DataFrame, atr_window: int = 100, atr_mult: float = 1.5) -> pd.DataFrame:
    """
    Generate signals with a volatility filter:
    - Only trade if current ATR is less than atr_mult * median ATR over last atr_window bars.
    - Signal logic:
        - ema_7_21_ratio > 1.005 → long
        - ema_7_21_ratio < 0.995 → short
        - else, range mean‑reversion (position > 0.7 and RSI > 60 → short; position < 0.3 and RSI < 40 → long)
    """
    df = df.copy()
    # Compute rolling median ATR (use last atr_window bars, min_periods=10)
    median_atr = df['atr_14'].rolling(window=atr_window, min_periods=10).median()
    volatility_filter = df['atr_14'] < (median_atr * atr_mult)
    volatility_filter = volatility_filter.fillna(True)  # allow early bars

    direction = np.zeros(len(df))
    confidence = np.zeros(len(df))

    for i in range(len(df)):
        row = df.iloc[i]
        # Skip if volatility filter fails
        if not volatility_filter.iloc[i]:
            direction[i] = 0
            confidence[i] = 0.0
            continue

        ratio = row.get('ema_7_21_ratio', 1.0)
        pos = row.get('position_in_yearly_range', 0.5)
        rsi = row.get('rsi_14', 50.0)
        base_conf = row.get('regime_confidence', 0.5)

        if ratio > 1.005:
            direction[i] = 1
            sig_conf = base_conf * 0.8
        elif ratio < 0.995:
            direction[i] = -1
            sig_conf = base_conf * 0.8
        else:
            # Range mean-reversion
            if pos > 0.7 and rsi > 60:
                direction[i] = -1
                sig_conf = base_conf * 0.6
            elif pos < 0.3 and rsi < 40:
                direction[i] = 1
                sig_conf = base_conf * 0.6
            else:
                direction[i] = 0
                sig_conf = base_conf * 0.3

        confidence[i] = round(sig_conf, 3)

    df['direction'] = direction
    df['confidence'] = confidence
    df['volatility_filter'] = volatility_filter.astype(int)
    return df

def main():
    regime_dir = Path("data/processed/regime_continuous")
    # Map symbol names to regime file names (files end with "_regime.parquet")
    all_files = list(regime_dir.glob("*_regime.parquet"))
    selected_files = []
    for sym in SYMBOLS:
        # Find file that starts with the symbol name
        for f in all_files:
            if f.stem.startswith(sym):
                selected_files.append(f)
                break
        else:
            logger.warning(f"Regime file for {sym} not found")
    if not selected_files:
        logger.error("No regime files found for selected symbols")
        return

    logger.info(f"Testing on {len(selected_files)} symbols: {[f.stem for f in selected_files]}")

    all_signals = []
    for f in selected_files:
        df = pd.read_parquet(f)
        # Take last 10000 rows (most recent data)
        df_subset = df.tail(10000).copy()
        if df_subset.empty:
            continue
        signals = generate_signals_with_volatility_filter(df_subset)
        all_signals.append(signals)

    if not all_signals:
        logger.error("No signals generated")
        return
    signals_df = pd.concat(all_signals, ignore_index=True)

    # Keep necessary columns
    keep_cols = ['time', 'symbol', 'open', 'high', 'low', 'close', 'volume',
                 'direction', 'confidence', 'regime', 'regime_confidence', 'atr_14']
    available = [c for c in keep_cols if c in signals_df.columns]
    signals_df = signals_df[available]

    # Save signals to Parquet (one per symbol for risk agent)
    test_dir = Path("data/processed/medium_test")
    test_dir.mkdir(parents=True, exist_ok=True)
    signal_files = []
    for symbol, grp in signals_df.groupby("symbol"):
        out_path = test_dir / f"{symbol}_signals.parquet"
        grp.to_parquet(out_path, index=False)
        signal_files.append(str(out_path))

    # Create mock strategy artifact
    store = StateStore(base_path="./data/processed")
    message_bus = MessageBus()
    mock_id = "medium_test_strategy"
    meta = ArtifactMetadata(agent="strategy_agent", phase="strategy")
    temp_artifact = PipelineArtifact(
        artifact_id=mock_id,
        name="medium_test_signals",
        data={"file_paths": signal_files},
        metadata=meta
    )
    store.save(temp_artifact, overwrite=True)

    # Run risk agent
    risk_agent = RiskAgent(store, message_bus, capital=10000.0, max_risk_per_trade=0.02)
    risk_result = risk_agent.execute(input_artifact_id=mock_id)
    if not risk_result.success:
        logger.error(f"Risk failed: {risk_result.message}")
        return
    risk_id = risk_result.artifact_id

    # Run backtest
    bt_agent = BacktestAgent(store, message_bus)
    bt_result = bt_agent.execute(input_artifact_id=risk_id)
    if not bt_result.success:
        logger.error(f"Backtest failed: {bt_result.message}")
        return
    bt_id = bt_result.artifact_id

    # Load and print backtest report
    art = store.load(bt_id)
    report = art.data['report']
    print("\n=== BACKTEST REPORT (10 symbols, 10000 bars, volatility filter) ===")
    for k, v in report.items():
        print(f"{k}: {v}")

    # Also print per-symbol trade counts
    risk_dir = Path("data/processed/risk")
    print("\n=== Per‑symbol approved trades ===")
    for f in risk_dir.glob("*_risk.parquet"):
        symbol = f.stem.replace("_risk", "")
        if symbol in [Path(f).stem.split('_')[0] for f in selected_files]:  # rough match
            df = pd.read_parquet(f)
            approved = df['approved'].sum()
            total = len(df)
            print(f"{symbol}: {approved}/{total} trades approved")

if __name__ == "__main__":
    main()
