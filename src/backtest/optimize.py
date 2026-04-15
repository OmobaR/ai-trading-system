#!/usr/bin/env python3
"""
Walk‑forward optimization for NNFX strategy parameters.
"""

import argparse
import logging
import itertools
from datetime import datetime, timedelta
from copy import deepcopy
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
        
        for combination in itertools.product(*values):
            params = dict(zip(keys, combination))
            # Apply parameters to the strategy
            result = self._run_with_params(params)
            results.append({
                'params': params,
                'metrics': result
            })
            logger.info(f"Params: {params} -> PnL: {result.get('total_pnl', 0):.2f}, Trades: {result.get('total_trades', 0)}")
        
        return results
    
    def _run_with_params(self, params: dict) -> dict:
        """Run backtest with modified NNFX parameters"""
        # Modify global config or strategy thresholds (simplified: we'll pass via engine)
        # For now, we store original values, change, run, restore
        original_adx = getattr(config, 'ADX_THRESHOLD', 25)
        original_atr = getattr(config, 'ATR_PERIOD', 14)
        original_rsi_ob = getattr(config, 'RSI_OVERBOUGHT', 70)
        original_rsi_os = getattr(config, 'RSI_OVERSOLD', 30)
        original_conf = getattr(config, 'MIN_SIGNAL_CONFIDENCE', 0.6)
        
        try:
            # Override config values (if your strategy reads from config)
            config.ADX_THRESHOLD = params.get('adx_threshold', original_adx)
            config.ATR_PERIOD = params.get('atr_period', original_atr)
            config.RSI_OVERBOUGHT = params.get('rsi_overbought', original_rsi_ob)
            config.RSI_OVERSOLD = params.get('rsi_oversold', original_rsi_os)
            config.MIN_SIGNAL_CONFIDENCE = params.get('min_confidence', original_conf)
            
            # Re-initialize strategy with new parameters? The strategy reads from config on init.
            # Simplest: create a new engine (which creates new strategy)
            engine = BacktestEngine()
            metrics = engine.run(self.symbol, self.start_date, self.end_date)
            return {
                'total_trades': metrics.total_trades,
                'total_pnl': metrics.total_pnl,
                'win_rate': metrics.win_rate,
                'sharpe_ratio': metrics.sharpe_ratio,
                'max_drawdown': metrics.max_drawdown,
                'profit_factor': metrics.profit_factor
            }
        finally:
            # Restore original config values
            config.ADX_THRESHOLD = original_adx
            config.ATR_PERIOD = original_atr
            config.RSI_OVERBOUGHT = original_rsi_ob
            config.RSI_OVERSOLD = original_rsi_os
            config.MIN_SIGNAL_CONFIDENCE = original_conf
    
    def walk_forward(self, param_grid: dict, train_days: int = 60, test_days: int = 30):
        """
        Walk‑forward: train on first N days, test on next M days, slide.
        """
        current_start = self.start_date
        results = []
        
        while current_start + timedelta(days=train_days + test_days) <= self.end_date:
            train_end = current_start + timedelta(days=train_days)
            test_end = train_end + timedelta(days=test_days)
            
            logger.info(f"Training from {current_start.date()} to {train_end.date()}")
            # Train: find best params on training period
            train_opt = ParameterOptimizer(self.symbol, current_start, train_end)
            train_results = train_opt.run_grid_search(param_grid)
            if not train_results:
                logger.warning("No training results, skipping")
                break
            
            best_train = max(train_results, key=lambda x: x['metrics']['total_pnl'])
            best_params = best_train['params']
            logger.info(f"Best params: {best_params} with PnL {best_train['metrics']['total_pnl']:.2f}")
            
            # Test: run with best params on test period
            test_engine = BacktestEngine()
            test_metrics = test_engine.run(self.symbol, train_end, test_end)
            results.append({
                'train_period': (current_start, train_end),
                'test_period': (train_end, test_end),
                'best_params': best_params,
                'test_metrics': {
                    'total_trades': test_metrics.total_trades,
                    'total_pnl': test_metrics.total_pnl,
                    'win_rate': test_metrics.win_rate,
                    'sharpe_ratio': test_metrics.sharpe_ratio
                }
            })
            
            # Slide window
            current_start += timedelta(days=test_days)
        
        return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='GainX 400')
    parser.add_argument('--days', type=int, default=90, help='Total days for optimization')
    parser.add_argument('--train', type=int, default=60, help='Training days')
    parser.add_argument('--test', type=int, default=30, help='Test days')
    args = parser.parse_args()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    param_grid = {
        'adx_threshold': [20, 25, 30],
        'atr_period': [10, 14, 20],
        'min_confidence': [0.5, 0.6, 0.7],
        'rsi_overbought': [65, 70, 75],
        'rsi_oversold': [25, 30, 35]
    }
    
    opt = ParameterOptimizer(args.symbol, start_date, end_date)
    # First, grid search on whole period
    logger.info("=== Grid Search on Full Period ===")
    grid_results = opt.run_grid_search(param_grid)
    best = max(grid_results, key=lambda x: x['metrics']['total_pnl'])
    logger.info(f"Best params overall: {best['params']}")
    logger.info(f"Metrics: {best['metrics']}")
    
    # Walk‑forward
    logger.info("\n=== Walk‑Forward Optimization ===")
    wf_results = opt.walk_forward(param_grid, train_days=args.train, test_days=args.test)
    logger.info(f"Walk‑forward completed with {len(wf_results)} windows")
    for i, res in enumerate(wf_results):
        logger.info(f"Window {i+1}: Params {res['best_params']} -> Test PnL: {res['test_metrics']['total_pnl']:.2f}")

if __name__ == "__main__":
    main()