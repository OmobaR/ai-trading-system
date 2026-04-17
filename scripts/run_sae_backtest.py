# scripts/run_sae_backtest.py
"""
Run SAE strategy backtest on all symbols using data from TimescaleDB.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
import logging
from src.events.event_store import EventStore
from src.config.settings import config
from src.strategies.sae_strategy import SAEStrategy

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SYMBOLS = [
    "GainX 400", "GainX 600", "GainX 800", "GainX 999", "GainX 1200",
    "PainX 400", "PainX 600", "PainX 800", "PainX 999", "PainX 1200",
    "FlipX 1", "FlipX 2", "FlipX 3", "FlipX 4", "FlipX 5",
    "FX Vol 20", "FX Vol 40", "FX Vol 60", "FX Vol 80", "FX Vol 99",
    "SFX Vol 20", "SFX Vol 40", "SFX Vol 60", "SFX Vol 80", "SFX Vol 99",
    "TrendX 600", "TrendX 1200", "TrendX 1800",
    "SwitchX 600", "SwitchX 1200", "SwitchX 1800",
    "BreakX 600", "BreakX 1200", "BreakX 1800",
]

TIMEFRAME = "M2"   # primary, fallback to M5 then M15 if M2 missing

def load_data(symbol: str, timeframe: str = TIMEFRAME, limit: int = 50000) -> pd.DataFrame:
    store = EventStore({
        'host': config.DB_HOST,
        'port': config.DB_PORT,
        'database': config.DB_NAME,
        'user': config.DB_USER,
        'password': config.DB_PASSWORD
    })
    query = """
        SELECT time, open, high, low, close, volume
        FROM ohlcv_data
        WHERE symbol = %s
        ORDER BY time ASC
        LIMIT %s
    """
    df = pd.read_sql(query, store.conn, params=(symbol, limit), index_col='time', parse_dates=['time'])
    return df

def run_backtest(symbol: str):
    df = load_data(symbol)
    if df is None or len(df) < 100:
        logger.warning(f"Insufficient data for {symbol}")
        return None

    strategy = SAEStrategy(symbol, initial_capital=10000, risk_per_trade=0.02)
    result = strategy.backtest(df)

    total_return = (result['equity'].iloc[-1] - strategy.initial_capital) / strategy.initial_capital
    sharpe = result['returns'].mean() / result['returns'].std() * np.sqrt(252 * 24 * 12) if result['returns'].std() != 0 else 0
    max_dd = (result['equity'].cummax() - result['equity']).max() / result['equity'].cummax().max()
    num_trades = len(strategy.trades) // 2

    metrics = {
        'symbol': symbol,
        'total_return': total_return,
        'sharpe_ratio': sharpe,
        'max_drawdown': max_dd,
        'num_trades': num_trades,
        'final_equity': result['equity'].iloc[-1]
    }
    return metrics

if __name__ == "__main__":
    results = []
    for sym in SYMBOLS:
        logger.info(f"Backtesting {sym}...")
        metrics = run_backtest(sym)
        if metrics:
            results.append(metrics)
            logger.info(f"  Return: {metrics['total_return']:.2%}, Sharpe: {metrics['sharpe_ratio']:.2f}")

    if results:
        df_results = pd.DataFrame(results)
        print("\n" + "="*60)
        print("SAE Strategy Backtest Summary (M2 timeframe)")
        print("="*60)
        print(df_results.to_string(index=False))
        print("\nAverages:")
        print(f"  Mean Return: {df_results['total_return'].mean():.2%}")
        print(f"  Mean Sharpe: {df_results['sharpe_ratio'].mean():.2f}")
        print(f"  Mean Max DD: {df_results['max_drawdown'].mean():.2%}")
    else:
        print("No backtest results.")