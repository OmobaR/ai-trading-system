#!/usr/bin/env python3
"""
Command-line interface for backtesting.
"""

import argparse
import logging
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import BacktestEngine
from config.settings import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Run backtest on historical data')
    parser.add_argument('--symbol', type=str, default='GainX 400', help='Symbol to backtest')
    parser.add_argument('--days', type=int, default=30, help='Number of days to backtest')
    parser.add_argument('--capital', type=float, default=10000.0, help='Initial capital')
    parser.add_argument('--multi', action='store_true', help='Run on all symbols')
    args = parser.parse_args()
    
    engine = BacktestEngine(initial_capital=args.capital)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    if args.multi:
        symbols = config.SYMBOLS
        results = engine.run_multi_symbol(symbols, start_date, end_date, args.capital)
        for sym, metrics in results.items():
            print(f"{sym}: {metrics.total_trades} trades, PnL: {metrics.total_pnl:.2f}, Win Rate: {metrics.win_rate:.1%}")
    else:
        metrics = engine.run(args.symbol, start_date, end_date, args.capital)
        print(f"\n=== Backtest Results for {args.symbol} ===")
        print(f"Total Trades: {metrics.total_trades}")
        print(f"Winning Trades: {metrics.winning_trades}")
        print(f"Losing Trades: {metrics.losing_trades}")
        print(f"Total PnL: {metrics.total_pnl:.2f}")
        print(f"Win Rate: {metrics.win_rate:.1%}")
        print(f"Max Drawdown: {metrics.max_drawdown:.1%}")
        print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
        print(f"Profit Factor: {metrics.profit_factor:.2f}")

if __name__ == "__main__":
    main()