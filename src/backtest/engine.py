#!/usr/bin/env python3
"""
Backtesting Engine for AI Trading System
Replays historical data from TimescaleDB and simulates trades.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from events.event_store import EventStore
from database.redis_feature_store import UnifiedRegimeFeatureStore
from strategy.nnfx_strategy import NNFXStrategy
from risk.risk_manager import RiskManagerAgent
from config.settings import config

logger = logging.getLogger(__name__)

@dataclass
class BacktestTrade:
    entry_time: datetime
    exit_time: datetime
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_percent: float
    exit_reason: str

@dataclass
class BacktestMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    trades: List[BacktestTrade] = field(default_factory=list)

class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0, 
                 commission: float = 0.0,
                 slippage: float = 0.0001):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        
        self.db_config = {
            'host': config.DB_HOST,
            'port': config.DB_PORT,
            'database': config.DB_NAME,
            'user': config.DB_USER,
            'password': config.DB_PASSWORD
        }
        self.redis_config = {
            'host': config.REDIS_HOST,
            'port': config.REDIS_PORT,
            'db': config.REDIS_DB
        }
        
        self.event_store = EventStore(self.db_config)
        self.feature_store = UnifiedRegimeFeatureStore(self.redis_config, regime_model='comprehensive')
        self.strategy = NNFXStrategy()
        self.risk_manager = RiskManagerAgent(self.redis_config)
        
        self.current_position = None
        self.trades = []
        self.equity_curve = []
    
    def _get_historical_data(self, symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Fetch OHLCV data from TimescaleDB and convert Decimal to float"""
        query = """
        SELECT time, symbol, open, high, low, close, volume
        FROM ohlcv_data
        WHERE symbol = %s AND time BETWEEN %s AND %s
        ORDER BY time ASC
        """
        with self.event_store.conn.cursor() as cur:
            cur.execute(query, (symbol, start_date, end_date))
            rows = cur.fetchall()
        
        if not rows:
            logger.warning(f"No data for {symbol}")
            return pd.DataFrame()
        
        df = pd.DataFrame(rows, columns=['time', 'symbol', 'open', 'high', 'low', 'close', 'volume'])
        # Convert Decimal to float
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        df['volume'] = df['volume'].astype(int)
        df.set_index('time', inplace=True)
        return df
    
    def _get_or_compute_regime(self, symbol: str, row: pd.Series, historical_context: pd.DataFrame) -> Tuple[str, float, Dict]:
        """Compute regime for a bar, ensuring float conversion"""
        ohlcv_dict = {
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'volume': int(row.get('volume', 1000))
        }
        # Convert context to float
        if not historical_context.empty:
            context = historical_context.tail(50).copy()
            for col in ['open', 'high', 'low', 'close']:
                context[col] = context[col].astype(float)
            if 'volume' in context:
                context['volume'] = context['volume'].astype(int)
        else:
            context = pd.DataFrame()
        
        features, signals = self.feature_store.compute_unified_regime_features(symbol, ohlcv_dict, context)
        return features.regime_type, features.regime_confidence, {
            'signal': signals.nnfx_signal,
            'confidence': signals.signal_confidence
        }
    
    def _apply_slippage(self, price: float, side: str) -> float:
        if side == 'BUY':
            return price * (1 + self.slippage)
        else:
            return price * (1 - self.slippage)
    
    def _execute_trade(self, symbol: str, side: str, price: float, timestamp: datetime,
                       confidence: float, regime: str) -> Optional[Dict]:
        atr = 0.01  # Placeholder – would compute from recent bars
        approved_size, details = self.risk_manager.approve_trade(symbol, atr, confidence, price)
        if approved_size <= 0:
            return None
        
        quantity = approved_size
        cost = quantity * price
        if cost > self.capital:
            quantity = self.capital / price
        
        if quantity <= 0:
            return None
        
        commission_cost = cost * self.commission
        self.capital -= commission_cost
        
        return {
            'side': side,
            'entry_price': price,
            'quantity': quantity,
            'entry_time': timestamp,
            'cost': cost,
            'confidence': confidence,
            'regime': regime
        }
    
    def _close_position(self, exit_price: float, exit_time: datetime, reason: str):
        if self.current_position is None:
            return
        
        pos = self.current_position
        if pos['side'] == 'BUY':
            pnl = (exit_price - pos['entry_price']) * pos['quantity']
        else:
            pnl = (pos['entry_price'] - exit_price) * pos['quantity']
        
        exit_cost = exit_price * pos['quantity'] * self.commission
        pnl -= exit_cost
        self.capital += pnl
        
        trade = BacktestTrade(
            entry_time=pos['entry_time'],
            exit_time=exit_time,
            symbol=pos['symbol'],
            side=pos['side'],
            entry_price=pos['entry_price'],
            exit_price=exit_price,
            quantity=pos['quantity'],
            pnl=pnl,
            pnl_percent=(pnl / (pos['entry_price'] * pos['quantity'])) * 100,
            exit_reason=reason
        )
        self.trades.append(trade)
        self.current_position = None
        self.equity_curve.append((exit_time, self.capital))
    
    def run(self, symbol: str, start_date: datetime, end_date: datetime,
            initial_capital: float = None) -> BacktestMetrics:
        if initial_capital:
            self.capital = initial_capital
            self.initial_capital = initial_capital
        
        logger.info(f"Starting backtest for {symbol} from {start_date} to {end_date}")
        df = self._get_historical_data(symbol, start_date, end_date)
        if df.empty:
            logger.error(f"No data for {symbol}")
            return BacktestMetrics()
        
        self.current_position = None
        self.trades = []
        self.equity_curve = [(df.index[0], self.capital)]
        bars_in_position = 0
        max_hold_bars = 48
        
        for idx, (timestamp, row) in enumerate(df.iterrows()):
            historical_context = df.iloc[max(0, idx-50):idx]
            regime, confidence, signals = self._get_or_compute_regime(symbol, row, historical_context)
            signal = signals['signal']
            signal_conf = signals['confidence']
            
            if self.current_position:
                bars_in_position += 1
                exit_signal = False
                exit_reason = None
                if signal in ['BUY', 'SELL'] and signal != self.current_position['side']:
                    exit_signal = True
                    exit_reason = 'opposite_signal'
                elif bars_in_position >= max_hold_bars:
                    exit_signal = True
                    exit_reason = 'timeout'
                
                if exit_signal:
                    exit_price = self._apply_slippage(row['close'], self.current_position['side'])
                    self._close_position(exit_price, timestamp, exit_reason)
                    bars_in_position = 0
            
            if self.current_position is None and signal in ['BUY', 'SELL'] and signal_conf >= 0.6:
                entry_price = self._apply_slippage(row['close'], signal)
                new_pos = self._execute_trade(symbol, signal, entry_price, timestamp, signal_conf, regime)
                if new_pos:
                    new_pos['symbol'] = symbol
                    self.current_position = new_pos
                    bars_in_position = 0
        
        if self.current_position:
            last_price = df.iloc[-1]['close']
            exit_price = self._apply_slippage(last_price, self.current_position['side'])
            self._close_position(exit_price, df.index[-1], 'end_of_period')
        
        return self._calculate_metrics()
    
    def _calculate_metrics(self) -> BacktestMetrics:
        metrics = BacktestMetrics()
        metrics.trades = self.trades
        metrics.total_trades = len(self.trades)
        if metrics.total_trades == 0:
            return metrics
        
        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl <= 0]
        metrics.winning_trades = len(winning)
        metrics.losing_trades = len(losing)
        metrics.total_pnl = sum(t.pnl for t in self.trades)
        metrics.win_rate = metrics.winning_trades / metrics.total_trades if metrics.total_trades else 0
        
        if winning:
            metrics.avg_win = sum(t.pnl for t in winning) / len(winning)
        if losing:
            metrics.avg_loss = sum(t.pnl for t in losing) / len(losing)
        
        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        metrics.profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')
        
        if self.equity_curve:
            equity_values = [e[1] for e in self.equity_curve]
            peak = equity_values[0]
            drawdown = 0
            for val in equity_values:
                if val > peak:
                    peak = val
                dd = (peak - val) / peak if peak != 0 else 0
                if dd > drawdown:
                    drawdown = dd
            metrics.max_drawdown = drawdown
        
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                ret = (self.equity_curve[i][1] - self.equity_curve[i-1][1]) / self.equity_curve[i-1][1] if self.equity_curve[i-1][1] != 0 else 0
                returns.append(ret)
            if returns:
                metrics.sharpe_ratio = np.mean(returns) / (np.std(returns) + 1e-6) * np.sqrt(252)
        
        return metrics

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = BacktestEngine()
    end = datetime.now()
    start = end - timedelta(days=30)
    metrics = engine.run("GainX 400", start, end)
    print(metrics)