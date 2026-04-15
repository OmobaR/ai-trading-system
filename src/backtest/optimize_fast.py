#!/usr/bin/env python3
"""
Fast grid search for key NNFX parameters.
"""

import argparse
import logging
from datetime import datetime, timedelta
import sys
import os
import itertools

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import BacktestEngine
from config.settings import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_parameter_sweep(symbol: str, start_date: datetime, end_date: datetime,
                        adx_thresholds=[20, 25, 30],
                        min_confidences=[0.5, 0.6, 0.7]):
    """Simple grid over ADX and min_confidence only (fastest)."""
    results = []
    total_combos = len(adx_thresholds) * len(min_confidences)
    logger.info(f"Running {total_combos} combinations for {symbol}")
    
    for adx, conf in itertools.product(adx_thresholds, min_confidences):
        # Override config temporarily
        original_adx = config.ADX_THRESHOLD
        original_conf = config.MIN_SIGNAL_CONFIDENCE
        try:
            config.ADX_THRESHOLD = adx
            config.MIN_SIGNAL_CONFIDENCE = conf
            # Recreate engine (it will pick up new config values)
            engine = BacktestEngine()
            metrics = engine.run(symbol, start_date, end_date)
            results.append({
                'adx_threshold': adx,
                'min_confidence': conf,
                'total_pnl': metrics.total_pnl,
                'trades': metrics.total_trades,
                'win_rate': metrics.win_rate
            })
            logger.info(f"ADX={adx}, Conf={conf} -> PnL={metrics.total_pnl:.2f}, Trades={metrics.total_trades}")
        finally:
            config.ADX_THRESHOLD = original_adx
            config.MIN_SIGNAL_CONFIDENCE = original_conf
    
    # Find best
    best = max(results, key=lambda x: x['total_pnl'])
    logger.info(f"\n=== Best Parameters ===")
    logger.info(f"ADX Threshold: {best['adx_threshold']}")
    logger.info(f"Min Confidence: {best['min_confidence']}")
    logger.info(f"PnL: {best['total_pnl']:.2f}, Win Rate: {best['win_rate']:.1%}")
    return best

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='GainX 400')
    parser.add_argument('--days', type=int, default=90)
    args = parser.parse_args()
    
    end = datetime.now()
    start = end - timedelta(days=args.days)
    best = run_parameter_sweep(args.symbol, start, end)
    
    # Optionally update config permanently
    print(f"\nUpdate config.settings.py with:")
    print(f"ADX_THRESHOLD = {best['adx_threshold']}")
    print(f"MIN_SIGNAL_CONFIDENCE = {best['min_confidence']}")

if __name__ == "__main__":
    main()