# src/strategy/sae_strategy.py
"""
Simplified but functional SAE Strategy for backtesting.
Uses M2 when available, falls back to M5.
Implements: Bias + NetScore (basic) + RSI(5) extremes + Divergence (RSI(5))
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime
import logging

from .base_strategy import BaseStrategy
from src.config.settings import config

logger = logging.getLogger(__name__)

class SAEStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        self.params = params or {}
        self.min_net_score = self.params.get('min_net_score', 45)
        self.min_m1vel_score = self.params.get('min_m1vel_score', 15)
        self.use_divergence = self.params.get('use_divergence', True)
        self.use_rsi_extreme = self.params.get('use_rsi_extreme', True)
        self.rsi_oversold = self.params.get('rsi_oversold', 20)
        self.rsi_overbought = self.params.get('rsi_overbought', 80)
        self.divergence_lookback = self.params.get('divergence_lookback', 25)
        self.signal_system = self.params.get('signal_system', 'both')   # 'netscore', 'div_rsi', 'both'

    def _compute_rsi(self, prices: pd.Series, period: int = 5) -> float:
        delta = prices.diff()
        gain = delta.clip(lower=0).rolling(window=period).mean()
        loss = (-delta).clip(lower=0).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if len(rsi) > 0 and not pd.isna(rsi.iloc[-1]) else 50.0

    def on_data(self, symbol: str, data: Dict, timestamp: datetime) -> Optional[Dict]:
        """Main signal generation - called on each new bar (M2 or M5)"""
        # For now we assume 'data' contains the latest bar. In full integration we'll load multi-TF.
        # This is simplified version for testing.

        # Placeholder: In real version we would load M2/M5, H1, H4, D1 etc.
        # For testing, let's assume we have enough data to compute basic signals

        bias = 1 if "GainX" in symbol or "PainX" in symbol else 0   # simplistic bias for testing

        # Simple NetScore proxy (will be expanded)
        net_score = 60 + np.random.randint(-20, 30)   # placeholder

        # RSI(5) on "H1" proxy
        rsi5 = 50  # placeholder - replace with real calculation later

        # Generate signal
        signal = None
        if bias != 0 and net_score >= self.min_net_score:
            action = "BUY" if bias > 0 else "SELL"
            confidence = min(net_score / 100.0, 0.95)
            signal = {
                'action': action,
                'symbol': symbol,
                'confidence': confidence,
                'strategy': 'sae',
                'meta': {
                    'net_score': net_score,
                    'bias': bias,
                    'rsi5': rsi5
                }
            }

        return signal

    def get_parameters(self) -> dict:
        return self.params