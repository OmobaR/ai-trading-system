"""
Meta‑labeling using XGBoost – works directly with regime files.
Computes signals on the fly using improved strategy.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "quant_research_org"))

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score, precision_score, recall_score
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

REGIME_DIR = Path("data/processed/regime")
OUTPUT_MODEL_PATH = Path("models/xgb_meta_label.json")
OUTPUT_METRICS_PATH = Path("data/processed/meta_label_results.csv")

def generate_signals(df: pd.DataFrame, trend_thresh=0.005, vol_mult=1.5, min_conf=0.4, rsi_upper=70):
    """Generate signals from regime data using the improved strategy."""
    df = df.copy()
    # Trend strength from ema_7_21_ratio
    if 'ema_7_21_ratio' not in df.columns:
        raise ValueError("Missing ema_7_21_ratio in regime file")
    ratio = df['ema_7_21_ratio']
    trend = (ratio - 1.0) / trend_thresh
    trend = trend.clip(-1, 1)
    base_conf = trend.abs() * 0.8 + 0.2

    # Volatility filter
    if 'atr_14' not in df.columns:
        atr = df.get('true_range', 0.01)  # fallback
    else:
        atr = df['atr_14']
    median_atr = atr.rolling(100, min_periods=10).median()
    vol_ok = atr < (median_atr * vol_mult)
    vol_ok = vol_ok.fillna(True)

    direction = np.sign(trend)
    confidence = base_conf * trend.abs()
    confidence = confidence.clip(min_conf, 0.95)

    # Mean‑reversion when trend weak
    rsi_lower = 100 - rsi_upper
    weak_mask = (trend.abs() < 0.2) & (df['position_in_yearly_range'] < 0.3) & (df['rsi_14'] < rsi_lower)
    direction[weak_mask] = 1
    confidence[weak_mask] = 0.5
    weak_mask_sell = (trend.abs() < 0.2) & (df['position_in_yearly_range'] > 0.7) & (df['rsi_14'] > rsi_upper)
    direction[weak_mask_sell] = -1
    confidence[weak_mask_sell] = 0.5

    direction[~vol_ok] = 0
    confidence[~vol_ok] = 0.0

    df['direction'] = direction.astype(int)
    df['confidence'] = confidence.round(3)
    # Keep only rows with non‑zero direction
    return df[df['direction'] != 0].copy()

def compute_forward_return(df, close_col='close'):
    """Compute forward return for each row."""
    df = df.sort_values('time')
    df['next_close'] = df[close_col].shift(-1)
    df['forward_return'] = (df['next_close'] - df[close_col]) / df[close_col]
    return df.dropna(subset=['forward_return'])

def backtest_metrics(df):
    """Compute basic metrics from trades (each row is a trade)."""
    if df.empty:
        return {'total_trades':0, 'win_rate':0, 'sharpe':0, 'profit_factor':0, 'max_drawdown':0}
    df = df.copy()
    df['realized_return'] = df['direction'] * df['forward_return'] - 0.0001  # cost
    returns = df['realized_return'].values
    total = len(returns)
    wins = (returns > 0).sum()
    win_rate = wins / total
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
        'total_trades': total,
        'win_rate': win_rate,
        'sharpe': sharpe,
        'profit_factor': profit_factor,
        'max_drawdown': max_dd,
    }

def main():
    # Get all regime file paths
    regime_files = list(REGIME_DIR.glob("*_regime.parquet"))
    if not regime_files:
        logger.error("No regime files found in data/processed/regime")
        return
    logger.info(f"Found {len(regime_files)} regime files")

    all_trades = []
    # Process each symbol independently to build dataset
    for f in regime_files:
        symbol = f.stem.replace("_regime", "")
        logger.info(f"Processing {symbol}...")
        df = pd.read_parquet(f)
        # Use last 20000 bars to keep manageable (adjust as needed)
        df = df.tail(20000).copy()
        signals = generate_signals(df)
        if signals.empty:
            continue
        trades = compute_forward_return(signals)
        if trades.empty:
            continue
        # Add relevant features for meta‑labeling
        feat_cols = ['direction', 'confidence', 'trend_strength', 'regime_confidence', 'atr_14', 'position_in_yearly_range', 'rsi_14']
        # Ensure all features exist; fill missing with 0
        for col in feat_cols:
            if col not in trades.columns:
                trades[col] = 0
        trades = trades[feat_cols + ['forward_return', 'time']]
        all_trades.append(trades)

    if not all_trades:
        logger.error("No trades generated from any symbol")
        return
    data = pd.concat(all_trades, ignore_index=True)
    data = data.sort_values('time').reset_index(drop=True)
    logger.info(f"Total trades in dataset: {len(data)}")

    # Create label: 1 if forward_return > 0 else 0
    data['label'] = (data['forward_return'] > 0).astype(int)

    # Features for XGBoost
    feature_cols = ['direction', 'confidence', 'trend_strength', 'regime_confidence', 'atr_14', 'position_in_yearly_range', 'rsi_14']
    X = data[feature_cols]
    y = data['label']

    # Time‑based split (first 80% train, last 20% test)
    split_idx = int(len(data) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    data_train = data.iloc[:split_idx]
    data_test = data.iloc[split_idx:]

    logger.info(f"Train samples: {len(X_train)}, Test samples: {len(X_test)}")

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
    threshold = 0.6
    y_pred = (y_pred_proba >= threshold).astype(int)

    # Classifier metrics
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    logger.info(f"XGBoost – Acc={acc:.3f}, Prec={prec:.3f}, Rec={rec:.3f}")

    # Backtest original test signals
    orig_metrics = backtest_metrics(data_test)
    logger.info(f"Original (test): trades={orig_metrics['total_trades']}, Sharpe={orig_metrics['sharpe']:.3f}, WR={orig_metrics['win_rate']:.3f}")

    # Filter test signals using predictions
    filtered_test = data_test.iloc[y_pred_proba >= threshold].copy()
    filt_metrics = backtest_metrics(filtered_test)
    logger.info(f"Filtered (test): trades={filt_metrics['total_trades']}, Sharpe={filt_metrics['sharpe']:.3f}, WR={filt_metrics['win_rate']:.3f}")

    # Save model and metrics
    OUTPUT_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(OUTPUT_MODEL_PATH))
    logger.info(f"Model saved to {OUTPUT_MODEL_PATH}")

    results = pd.DataFrame({
        'metric': ['original_total_trades', 'original_win_rate', 'original_sharpe', 'original_profit_factor', 'original_max_drawdown',
                   'filtered_total_trades', 'filtered_win_rate', 'filtered_sharpe', 'filtered_profit_factor', 'filtered_max_drawdown'],
        'value': [orig_metrics['total_trades'], orig_metrics['win_rate'], orig_metrics['sharpe'], orig_metrics['profit_factor'], orig_metrics['max_drawdown'],
                  filt_metrics['total_trades'], filt_metrics['win_rate'], filt_metrics['sharpe'], filt_metrics['profit_factor'], filt_metrics['max_drawdown']]
    })
    results.to_csv(OUTPUT_METRICS_PATH, index=False)
    logger.info(f"Metrics saved to {OUTPUT_METRICS_PATH}")

if __name__ == "__main__":
    main()