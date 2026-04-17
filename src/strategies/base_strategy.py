"""
Abstract base class for all trading strategies.
"""

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional

class BaseStrategy(ABC):
    def __init__(self, symbol: str, initial_capital: float = 10000.0, risk_per_trade: float = 0.02):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.position = 0
        self.capital = initial_capital
        self.trades = []

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        pass

    def calculate_position_size(self, price: float, atr: float = None) -> int:
        if atr is None:
            risk_amount = self.capital * self.risk_per_trade
            position_size = int(risk_amount / price)
        else:
            risk_amount = self.capital * self.risk_per_trade
            position_size = int(risk_amount / atr)
        return max(position_size, 0)

    def execute_trade(self, timestamp, signal, price):
        if signal == 1 and self.position == 0:
            size = self.calculate_position_size(price)
            cost = size * price
            if cost <= self.capital:
                self.position = size
                self.capital -= cost
                self.trades.append({
                    'time': timestamp, 'type': 'BUY', 'price': price,
                    'size': size, 'capital': self.capital
                })
        elif signal == -1 and self.position > 0:
            proceeds = self.position * price
            self.capital += proceeds
            self.trades.append({
                'time': timestamp, 'type': 'SELL', 'price': price,
                'size': self.position, 'capital': self.capital
            })
            self.position = 0

    def backtest(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.generate_signals(df.copy())
        df['position'] = 0
        df['capital'] = self.initial_capital
        for i, row in df.iterrows():
            self.execute_trade(row.name, row.get('signal', 0), row['close'])
            df.at[i, 'position'] = self.position
            df.at[i, 'capital'] = self.capital
        df['equity'] = df['capital'] + df['position'] * df['close']
        df['returns'] = df['equity'].pct_change()
        df['cumulative_returns'] = (1 + df['returns']).cumprod()
        return df
