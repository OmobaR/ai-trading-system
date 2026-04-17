#!/usr/bin/env python3
"""
Enhanced Backtesting Engine with realistic slippage, commission, and metrics.
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
    commission: float = 0.0
    slippage: float = 0.0

@dataclass
class BacktestMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration_days: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    total_commission: float = 0.0
    total_slippage: float = 0.0
    trades: List[BacktestTrade] = field(default_factory=list)

class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0,
                 commission_rate: float = 0.0005,   # 0.05% commission
                 slippage_model: str = 'percent',   # 'percent' or 'points'
                 slippage_value: float = 0.0001,    # 0.01% or 1 point
                 atr_slippage_multiplier: float = 0.5):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_model = slippage_model
        self.slippage_value = slippage_value
        self.atr_slippage_multiplier = atr_slippage_multiplier
        
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
        self.daily_returns = []
    
    def _get_historical_data(self, symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
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
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=['time', 'symbol', 'open', 'high', 'low', 'close', 'volume'])
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        df['volume'] = df['volume'].astype(int)
        df.set_index('time', inplace=True)
        return df
    
    def _get_or_compute_regime(self, symbol: str, row: pd.Series, historical_context: pd.DataFrame) -> Tuple[str, float, Dict]:
        ohlcv_dict = {
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'volume': int(row.get('volume', 1000))
        }
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
    
    def _apply_slippage(self, price: float, side: str, atr: float = None) -> float:
        """Apply slippage based on model."""
        if self.slippage_model == 'points':
            slip = self.slippage_value
        elif self.slippage_model == 'percent':
            slip = price * self.slippage_value
        elif self.slippage_model == 'atr' and atr is not None:
            slip = atr * self.atr_slippage_multiplier
        else:
            slip = 0.0
        if side == 'BUY':
            return price + slip
        else:
            return price - slip
    
    def _apply_commission(self, price: float, quantity: float) -> float:
        return price * quantity * self.commission_rate
    
    def _execute_trade(self, symbol: str, side: str, price: float, timestamp: datetime,
                       confidence: float, regime: str, atr: float = None) -> Optional[Dict]:
        atr_for_sizing = atr if atr is not None else 0.01
        approved_size, details = self.risk_manager.approve_trade(symbol, atr_for_sizing, confidence, price)
        if approved_size <= 0:
            return None
        quantity = approved_size
        cost = quantity * price
        if cost > self.capital:
            quantity = self.capital / price
        if quantity <= 0:
            return None
        commission = self._apply_commission(price, quantity)
        self.capital -= commission
        return {
            'side': side,
            'entry_price': price,
            'quantity': quantity,
            'entry_time': timestamp,
            'cost': cost,
            'confidence': confidence,
            'regime': regime,
            'commission': commission,
            'slippage': 0.0
        }
    
    def _close_position(self, exit_price: float, exit_time: datetime, reason: str, atr: float = None):
        if self.current_position is None:
            return
        pos = self.current_position
        if pos['side'] == 'BUY':
            pnl = (exit_price - pos['entry_price']) * pos['quantity']
        else:
            pnl = (pos['entry_price'] - exit_price) * pos['quantity']
        commission_exit = self._apply_commission(exit_price, pos['quantity'])
        pnl -= commission_exit
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
            exit_reason=reason,
            commission=pos['commission'] + commission_exit,
            slippage=pos.get('slippage', 0.0)
        )
        self.trades.append(trade)
        self.current_position = None
        self.equity_curve.append((exit_time, self.capital))
        # Update risk manager with trade PnL
        self.risk_manager.update_risk_metrics(pnl, pos['symbol'])
    
    def run(self, symbol: str, start_date: datetime, end_date: datetime,
            initial_capital: float = None) -> BacktestMetrics:
        if initial_capital:
            self.capital = initial_capital
            self.initial_capital = initial_capital
        logger.info(f"Backtest {symbol} from {start_date} to {end_date}")
        df = self._get_historical_data(symbol, start_date, end_date)
        if df.empty:
            logger.error(f"No data for {symbol}")
            return BacktestMetrics()
        
        self.current_position = None
        self.trades = []
        self.equity_curve = [(df.index[0], self.capital)]
        bars_in_position = 0
        max_hold_bars = 48  # 2 days (hourly)
        
        for idx, (timestamp, row) in enumerate(df.iterrows()):
            historical_context = df.iloc[max(0, idx-50):idx]
            regime, confidence, signals = self._get_or_compute_regime(symbol, row, historical_context)
            signal = signals['signal']
            signal_conf = signals['confidence']
            # Compute ATR for slippage (use recent bars)
            atr = 0.01
            if len(historical_context) >= 14:
                highs = historical_context['high'].values[-14:]
                lows = historical_context['low'].values[-14:]
                closes = historical_context['close'].values[-14:]
                import talib
                atr_val = talib.ATR(highs, lows, closes, timeperiod=14)[-1] if len(closes)>=14 else 0.01
                atr = atr_val if not np.isnan(atr_val) else 0.01
            
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
                    exit_price = self._apply_slippage(row['close'], self.current_position['side'], atr)
                    self._close_position(exit_price, timestamp, exit_reason, atr)
                    bars_in_position = 0
            
            if self.current_position is None and signal in ['BUY', 'SELL'] and signal_conf >= config.MIN_SIGNAL_CONFIDENCE:
                entry_price = self._apply_slippage(row['close'], signal, atr)
                new_pos = self._execute_trade(symbol, signal, entry_price, timestamp, signal_conf, regime, atr)
                if new_pos:
                    new_pos['symbol'] = symbol
                    new_pos['slippage'] = abs(entry_price - row['close'])
                    self.current_position = new_pos
                    bars_in_position = 0
        
        if self.current_position:
            last_price = df.iloc[-1]['close']
            exit_price = self._apply_slippage(last_price, self.current_position['side'], atr)
            self._close_position(exit_price, df.index[-1], 'end_of_period', atr)
        
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
        metrics.gross_profit = sum(t.pnl for t in winning)
        metrics.gross_loss = abs(sum(t.pnl for t in losing))
        metrics.total_commission = sum(t.commission for t in self.trades)
        metrics.total_slippage = sum(t.slippage for t in self.trades)
        metrics.win_rate = metrics.winning_trades / metrics.total_trades if metrics.total_trades else 0
        
        if winning:
            metrics.avg_win = sum(t.pnl for t in winning) / len(winning)
        if losing:
            metrics.avg_loss = sum(t.pnl for t in losing) / len(losing)
        
        metrics.profit_factor = metrics.gross_profit / metrics.gross_loss if metrics.gross_loss != 0 else float('inf')
        metrics.expectancy = metrics.total_pnl / metrics.total_trades if metrics.total_trades else 0
        
        # Drawdown from equity curve
        if self.equity_curve:
            equity_values = [e[1] for e in self.equity_curve]
            peak = equity_values[0]
            drawdown = 0.0
            max_dd_duration = 0
            current_duration = 0
            for val in equity_values:
                if val > peak:
                    peak = val
                    current_duration = 0
                else:
                    current_duration += 1
                    dd = (peak - val) / peak if peak != 0 else 0
                    if dd > drawdown:
                        drawdown = dd
                    if current_duration > max_dd_duration:
                        max_dd_duration = current_duration
            metrics.max_drawdown = drawdown
            # Convert bar count to days (assuming hourly bars)
            metrics.max_drawdown_duration_days = max_dd_duration / 24.0
        
        # Returns for Sharpe/Sortino
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                ret = (self.equity_curve[i][1] - self.equity_curve[i-1][1]) / self.equity_curve[i-1][1] if self.equity_curve[i-1][1] != 0 else 0
                returns.append(ret)
            if returns:
                ret_series = np.array(returns)
                mean_ret = np.mean(ret_series)
                std_ret = np.std(ret_series)
                metrics.sharpe_ratio = (mean_ret / (std_ret + 1e-6)) * np.sqrt(252)  # annualized
                # Sortino (only negative returns)
                neg_returns = ret_series[ret_series < 0]
                downside_std = np.std(neg_returns) if len(neg_returns) > 0 else std_ret
                metrics.sortino_ratio = (mean_ret / (downside_std + 1e-6)) * np.sqrt(252)
                # Calmar = annualized return / max drawdown
                annualized_return = (self.capital / self.initial_capital) ** (252 / len(returns)) - 1 if len(returns) > 0 else 0
                metrics.calmar_ratio = annualized_return / (metrics.max_drawdown + 1e-6)
        
        return metrics