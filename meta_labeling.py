"""
Meta‑labeling using XGBoost.
Filters strategy signals based on predicted probability of profit.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "quant_research_org"))

import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb
from sklearn.metrics import accuracy_score, precision_score, recall_score
import logging


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
SIGNAL_DIR = Path("data/processed/strategy_continuous")
REGIME_DIR = Path("data/processed/regime_continuous")   # fallback to regular regime if absent
OUTPUT_MODEL_PATH = Path("models/xgb_meta_label.json")
OUTPUT_METRICS_PATH = Path("data/processed/meta_label_results.csv")

def load_signals_and_regime(symbol):
    """Load strategy signals and corresponding regime data for a symbol."""
    signal_file = SIGNAL_DIR / f"{symbol}_signals.parquet"
    if not signal_file.exists():
        return None, None
    signals = pd.read_parquet(signal_file)
    # Try to load continuous regime, else fallback to discrete regime
    regime_file = REGIME_DIR / f"{symbol}_regime.parquet"
    if not regime_file.exists():
        regime_file = Path("data/processed/regime") / f"{symbol}_regime.parquet"
    if not regime_file.exists():
        logger.warning(f"No regime file for {symbol}")
        return signals, None
    regime = pd.read_parquet(regime_file)
    return signals, regime

def compute_forward_return(signals, close_col='close'):
    """Compute forward return (next bar) for each signal."""
    signals = signals.sort_values('time')
    signals['next_close'] = signals[close_col].shift(-1)
    signals['forward_return'] = (signals['next_close'] - signals[close_col]) / signals[close_col]
    return signals.dropna(subset=['forward_return'])

def create_dataset(signals, regime):
    """Merge signals with regime features and create label (1 if forward_return > 0)."""
    # Keep only necessary columns from regime
    regime_cols = ['time', 'trend_strength', 'regime_confidence', 'atr_14',
                   'position_in_yearly_range', 'rsi_14']
    regime = regime[regime_cols].copy()
    # Merge on time (assume same time index)
    df = signals.merge(regime, on='time', how='left')
    # Features: direction, confidence, and regime features
    feature_cols = ['direction', 'confidence', 'trend_strength', 'regime_confidence', 'atr_14']
    # Ensure no NaNs
    df = df.dropna(subset=feature_cols + ['forward_return'])
    # Label: 1 if forward_return > 0 else 0
    df['label'] = (df['forward_return'] > 0).astype(int)
    return df, feature_cols

def backtest_metrics(df, trade_col='direction', return_col='forward_return'):
    """Compute basic backtest metrics from trades (long only here, but direction used)."""
    # For simplicity, we assume each row is a trade with given direction
    # Realised return = direction * forward_return
    df = df.copy()
    df['realized_return'] = df['direction'] * df[return_col]
    # Transaction cost (0.01%)
    df['realized_return'] = df['realized_return'] - 0.0001
    returns = df['realized_return'].values
    total_trades = len(returns)
    if total_trades == 0:
        return {'total_trades':0, 'win_rate':0, 'sharpe':0, 'profit_factor':0, 'max_drawdown':0}
    wins = (returns > 0).sum()
    win_rate = wins / total_trades
    avg_ret = returns.mean()
    sharpe = avg_ret / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    cum = np.cumsum(returns)
    running_max = np.maximum.accumulate(cum)
    drawdowns = cum - running_max
    max_dd = abs(drawdowns.min()) if len(drawdowns) else 0
    gross_profit = returns[returns > 0].sum()
    gross_loss = abs(returns[returns < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999
    return {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'sharpe': sharpe,
        'profit_factor': profit_factor,
        'max_drawdown': max_dd,
    }

def main():
    # Get list of symbols from signal files
    signal_files = list(SIGNAL_DIR.glob("*_signals.parquet"))
    symbols = [f.stem.replace("_signals", "") for f in signal_files]
    logger.info(f"Found {len(symbols)} symbols")

    all_data = []
    for symbol in symbols:
        signals, regime = load_signals_and_regime(symbol)
        if signals is None or regime is None:
            continue
        signals = compute_forward_return(signals)
        df, _ = create_dataset(signals, regime)
        if df.empty:
            continue
        all_data.append(df)

    if not all_data:
        logger.error("No valid data")
        return
    data = pd.concat(all_data, ignore_index=True)
    # Sort by time globally (important for time split)
    data = data.sort_values('time').reset_index(drop=True)

    # Features and label
    feature_cols = ['direction', 'confidence', 'trend_strength', 'regime_confidence', 'atr_14']
    X = data[feature_cols]
    y = data['label']

    # Time-based split (first 80% train, last 20% test)
    split_idx = int(len(data) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    data_train = data.iloc[:split_idx]
    data_test = data.iloc[split_idx:]

    logger.info(f"Train size: {len(X_train)}, Test size: {len(X_test)}")

    # Train XGBoost
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric='logloss'
    )
    model.fit(X_train, y_train)

    # Predict probabilities on test set
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    # Choose a threshold (e.g., 0.6) – can be tuned
    threshold = 0.6
    y_pred = (y_pred_proba >= threshold).astype(int)

    # Evaluate classifier on test set
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    logger.info(f"XGBoost on test: Accuracy={acc:.3f}, Precision={prec:.3f}, Recall={rec:.3f}")

    # Backtest on original test signals
    orig_metrics = backtest_metrics(data_test)
    logger.info(f"Original signals (test): trades={orig_metrics['total_trades']}, Sharpe={orig_metrics['sharpe']:.3f}, WR={orig_metrics['win_rate']:.3f}")

    # Filter test signals using model predictions (keep only where pred_proba >= threshold)
    filtered_test = data_test.iloc[y_pred_proba >= threshold].copy()
    filtered_metrics = backtest_metrics(filtered_test)
    logger.info(f"Filtered signals (test): trades={filtered_metrics['total_trades']}, Sharpe={filtered_metrics['sharpe']:.3f}, WR={filtered_metrics['win_rate']:.3f}")

    # Save model
    model.save_model(OUTPUT_MODEL_PATH)
    logger.info(f"Model saved to {OUTPUT_MODEL_PATH}")

    # Save metrics
    results = pd.DataFrame({
        'metric': ['original_total_trades', 'original_win_rate', 'original_sharpe', 'original_profit_factor', 'original_max_drawdown',
                   'filtered_total_trades', 'filtered_win_rate', 'filtered_sharpe', 'filtered_profit_factor', 'filtered_max_drawdown'],
        'value': [orig_metrics['total_trades'], orig_metrics['win_rate'], orig_metrics['sharpe'], orig_metrics['profit_factor'], orig_metrics['max_drawdown'],
                  filtered_metrics['total_trades'], filtered_metrics['win_rate'], filtered_metrics['sharpe'], filtered_metrics['profit_factor'], filtered_metrics['max_drawdown']]
    })
    results.to_csv(OUTPUT_METRICS_PATH, index=False)
    logger.info(f"Metrics saved to {OUTPUT_METRICS_PATH}")

if __name__ == "__main__":
    main()
