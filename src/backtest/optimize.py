#!/usr/bin/env python3
"""
Walk‑forward optimization for NNFX strategy parameters.
Includes grid search over ADX, ATR, confidence, RSI thresholds, and risk per trade.
"""

import argparse
import logging
import itertools
from datetime import datetime, timedelta
import json
import csv
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import BacktestEngine
from config.settings import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ParameterOptimizer:
    def __init__(self, symbol: str, start_date: datetime, end_date: datetime):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.base_engine = BacktestEngine()
    
    def run_grid_search(self, param_grid: dict) -> list:
        """Grid search over all parameter combinations"""
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        results = []
        total_combos = 1
        for v in values:
            total_combos *= len(v)
        logger.info(f"Grid search over {total_combos} combinations")
        
        for idx, combination in enumerate(itertools.product(*values)):
            params = dict(zip(keys, combination))
            result = self._run_with_params(params)
            results.append({
                'params': params,
                'metrics': result
            })
            logger.info(f"[{idx+1}/{total_combos}] Params: {params} -> PnL: {result.get('total_pnl', 0):.2f}, Trades: {result.get('total_trades', 0)}")
        
        return results
    
    def _run_with_params(self, params: dict) -> dict:
        """Run backtest with modified NNFX parameters"""
        # Store original config values
        original_adx = getattr(config, 'ADX_THRESHOLD', 25)
        original_atr = getattr(config, 'ATR_PERIOD', 14)
        original_rsi_ob = getattr(config, 'RSI_OVERBOUGHT', 70)
        original_rsi_os = getattr(config, 'RSI_OVERSOLD', 30)
        original_conf = getattr(config, 'MIN_SIGNAL_CONFIDENCE', 0.6)
        original_risk_per_trade = getattr(config, 'RISK_PER_TRADE', 0.02)
        
        try:
            # Override config values
            config.ADX_THRESHOLD = params.get('adx_threshold', original_adx)
            config.ATR_PERIOD = params.get('atr_period', original_atr)
            config.RSI_OVERBOUGHT = params.get('rsi_overbought', original_rsi_ob)
            config.RSI_OVERSOLD = params.get('rsi_oversold', original_rsi_os)
            config.MIN_SIGNAL_CONFIDENCE = params.get('min_confidence', original_conf)
            if 'risk_per_trade' in params:
                config.RISK_PER_TRADE = params['risk_per_trade']
            
            engine = BacktestEngine()
            metrics = engine.run(self.symbol, self.start_date, self.end_date)
            return {
                'total_trades': metrics.total_trades,
                'total_pnl': metrics.total_pnl,
                'win_rate': metrics.win_rate,
                'sharpe_ratio': metrics.sharpe_ratio,
                'max_drawdown': metrics.max_drawdown,
                'profit_factor': metrics.profit_factor,
                'sortino_ratio': getattr(metrics, 'sortino_ratio', 0.0),
                'calmar_ratio': getattr(metrics, 'calmar_ratio', 0.0)
            }
        finally:
            # Restore original config values
            config.ADX_THRESHOLD = original_adx
            config.ATR_PERIOD = original_atr
            config.RSI_OVERBOUGHT = original_rsi_ob
            config.RSI_OVERSOLD = original_rsi_os
            config.MIN_SIGNAL_CONFIDENCE = original_conf
            if 'risk_per_trade' in params:
                config.RISK_PER_TRADE = original_risk_per_trade
    
    def walk_forward(self, param_grid: dict, train_days: int = 60, test_days: int = 30) -> list:
        """
        Walk‑forward: train on first N days, test on next M days, slide.
        """
        current_start = self.start_date
        results = []
        window = 1
        
        while current_start + timedelta(days=train_days + test_days) <= self.end_date:
            train_end = current_start + timedelta(days=train_days)
            test_end = train_end + timedelta(days=test_days)
            
            logger.info(f"Window {window}: Training from {current_start.date()} to {train_end.date()}")
            train_opt = ParameterOptimizer(self.symbol, current_start, train_end)
            train_results = train_opt.run_grid_search(param_grid)
            if not train_results:
                logger.warning("No training results, skipping")
                break
            
            best_train = max(train_results, key=lambda x: x['metrics']['total_pnl'])
            best_params = best_train['params']
            logger.info(f"Best params: {best_params} with PnL {best_train['metrics']['total_pnl']:.2f}")
            
            test_engine = BacktestEngine()
            test_metrics = test_engine.run(self.symbol, train_end, test_end)
            results.append({
                'window': window,
                'train_period': (current_start.isoformat(), train_end.isoformat()),
                'test_period': (train_end.isoformat(), test_end.isoformat()),
                'best_params': best_params,
                'test_metrics': {
                    'total_trades': test_metrics.total_trades,
                    'total_pnl': test_metrics.total_pnl,
                    'win_rate': test_metrics.win_rate,
                    'sharpe_ratio': test_metrics.sharpe_ratio,
                    'max_drawdown': test_metrics.max_drawdown,
                    'profit_factor': test_metrics.profit_factor
                }
            })
            
            current_start += timedelta(days=test_days)
            window += 1
        
        return results

def save_results(results, filename_base):
    """Save grid or walk‑forward results to JSON and CSV."""
    if not results:
        return
    # JSON
    with open(f"{filename_base}.json", 'w') as f:
        json.dump(results, f, indent=2, default=str)
    # CSV (flattened) – only for grid results where each entry has 'params' and 'metrics'
    if 'params' in results[0]:
        with open(f"{filename_base}.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            header = list(results[0]['params'].keys()) + list(results[0]['metrics'].keys())
            writer.writerow(header)
            for r in results:
                row = list(r['params'].values()) + list(r['metrics'].values())
                writer.writerow(row)
    logger.info(f"Saved results to {filename_base}.json and .csv")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='GainX 400')
    parser.add_argument('--days', type=int, default=90, help='Total days for optimization')
    parser.add_argument('--train', type=int, default=60, help='Training days')
    parser.add_argument('--test', type=int, default=30, help='Test days')
    parser.add_argument('--output', default='backtest_results', help='Base filename for saving results')
    args = parser.parse_args()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    param_grid = {
        'adx_threshold': [20, 25, 30],
        'atr_period': [10, 14, 20],
        'min_confidence': [0.5, 0.6, 0.7],
        'rsi_overbought': [65, 70, 75],
        'rsi_oversold': [25, 30, 35],
        'risk_per_trade': [0.015, 0.02, 0.025]   # optional – comment out if not needed
    }
    
    opt = ParameterOptimizer(args.symbol, start_date, end_date)
    
    # Grid search on full period
    logger.info("=== Grid Search on Full Period ===")
    grid_results = opt.run_grid_search(param_grid)
    best = max(grid_results, key=lambda x: x['metrics']['total_pnl'])
    logger.info(f"Best params overall: {best['params']}")
    logger.info(f"Metrics: {best['metrics']}")
    save_results(grid_results, f"{args.output}_grid")
    
    # Walk‑forward
    logger.info("\n=== Walk‑Forward Optimization ===")
    wf_results = opt.walk_forward(param_grid, train_days=args.train, test_days=args.test)
    logger.info(f"Walk‑forward completed with {len(wf_results)} windows")
    for res in wf_results:
        logger.info(f"Window {res['window']}: Params {res['best_params']} -> Test PnL: {res['test_metrics']['total_pnl']:.2f}")
    save_results(wf_results, f"{args.output}_walkforward")

if __name__ == "__main__":
    main()