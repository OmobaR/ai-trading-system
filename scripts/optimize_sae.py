#!/usr/bin/env python3
"""
Grid search for SAE parameters with data caching.
"""

import sys
import os
import itertools
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.events.event_store import EventStore
from src.config.settings import config
from src.strategies.sae_strategy import SAEStrategy

# Cache data per symbol
DATA_CACHE = {}

def load_data(symbol: str, limit: int = 50000) -> pd.DataFrame:
    if symbol in DATA_CACHE:
        return DATA_CACHE[symbol]
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
    DATA_CACHE[symbol] = df
    return df

def run_backtest_for_params(symbol: str, window: int, threshold: float, initial_capital: float = 10000) -> dict:
    df = load_data(symbol)
    if df.empty or len(df) < 100:
        return {'total_return': 0.0, 'sharpe_ratio': 0.0, 'num_trades': 0}
    
    strategy = SAEStrategy(symbol, window=window, threshold=threshold, initial_capital=initial_capital, risk_per_trade=0.02)
    result = strategy.backtest(df)
    
    total_return = (result['equity'].iloc[-1] - initial_capital) / initial_capital
    returns = result['returns'].dropna()
    if returns.std() != 0 and len(returns) > 0:
        sharpe = returns.mean() / returns.std() * np.sqrt(252 * 24 * 12)
    else:
        sharpe = 0.0
    num_trades = len(strategy.trades) // 2
    
    return {
        'total_return': total_return,
        'sharpe_ratio': sharpe,
        'num_trades': num_trades
    }

def main():
    symbol = 'GainX 400'
    param_grid = {
        'window': [30, 60, 90, 120],
        'threshold': [0.5, 1.0, 1.5, 2.0, 2.5]
    }
    
    results = []
    best_return = -float('inf')
    best_params = None
    
    for window, threshold in itertools.product(param_grid['window'], param_grid['threshold']):
        print(f"Testing window={window}, threshold={threshold}...")
        metrics = run_backtest_for_params(symbol, window, threshold)
        results.append({
            'window': window,
            'threshold': threshold,
            'return': metrics['total_return'],
            'sharpe': metrics['sharpe_ratio'],
            'trades': metrics['num_trades']
        })
        print(f"  Return: {metrics['total_return']:.4f}, Sharpe: {metrics['sharpe_ratio']:.2f}, Trades: {metrics['num_trades']}")
        if metrics['total_return'] > best_return:
            best_return = metrics['total_return']
            best_params = (window, threshold)
    
    print("\n" + "="*50)
    print(f"Best parameters for {symbol}: window={best_params[0]}, threshold={best_params[1]}")
    print(f"Best return: {best_return:.4f}")
    
    df_results = pd.DataFrame(results)
    df_results.to_csv('sae_optimization_results.csv', index=False)
    print("Results saved to sae_optimization_results.csv")

if __name__ == "__main__":
    main()