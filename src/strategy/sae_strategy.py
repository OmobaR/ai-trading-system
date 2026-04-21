# src/strategy/sae_strategy.py
"""
Deterministic SAE Strategy - No randomness, real signal logic
"""

from typing import Dict, Optional
from datetime import datetime
import logging
import numpy as np

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class SAEStrategy(BaseStrategy):
    def __init__(self, symbol: str = None, window: int = 30, threshold: float = 1.0,
                 initial_capital: float = 10000.0, risk_per_trade: float = 0.02, **kwargs):
        
        self.symbol = symbol
        self.window = window
        self.threshold = threshold
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade

        self.min_net_score = kwargs.get('min_net_score', 35)
        self.min_velocity = kwargs.get('min_velocity', 0.3)

        self.signal_count = 0

        # Store recent candles for structure logic
        self.recent_closes = []

        logger.info(f"SAE Strategy (Deterministic) initialized for {symbol}")

    def generate_signal(self, symbol: str, data: Dict, timestamp: datetime) -> Optional[Dict]:
        try:
            close = float(data.get('close', 0))
            open_p = float(data.get('open', close))
            high = float(data.get('high', close))
            low = float(data.get('low', close))

            if close <= 0 or open_p <= 0:
                return None

            # =========================
            # 1. MARKET BIAS
            # =========================
            if "GainX" in symbol:
                bias = 1
            elif "PainX" in symbol:
                bias = -1
            else:
                bias = 1

            # =========================
            # 2. PRICE FEATURES
            # =========================
            price_change = (close - open_p) / open_p
            momentum = price_change * 4000

            candle_range = max(high - low, 1e-6)
            candle_body = abs(close - open_p)

            body_strength = candle_body / candle_range  # 0–1

            # Velocity (scaled realistically)
            velocity = abs(price_change) * 100

            if velocity < self.min_velocity:
                return None

            # =========================
            # 3. TREND STRUCTURE (NEW)
            # =========================
            self.recent_closes.append(close)

            if len(self.recent_closes) > 5:
                self.recent_closes.pop(0)

            trend_score = 0

            if len(self.recent_closes) >= 3:
                if self.recent_closes[-1] > self.recent_closes[-2] > self.recent_closes[-3]:
                    trend_score = 5
                elif self.recent_closes[-1] < self.recent_closes[-2] < self.recent_closes[-3]:
                    trend_score = -5

            # =========================
            # 4. NET SCORE (DETERMINISTIC)
            # =========================
            base_score = 40

            net_score = (
                base_score
                + momentum
                + (body_strength * 15)
                + trend_score
            )

            # Apply threshold scaling
            net_score *= self.threshold

            # =========================
            # 5. FINAL FILTER
            # =========================
            if net_score < self.min_net_score:
                return None

            # =========================
            # 6. SIGNAL
            # =========================
            action = "BUY" if bias > 0 else "SELL"

            confidence = min(0.5 + (net_score / 180.0), 0.95)

            self.signal_count += 1

            if self.signal_count % 50 == 0:
                logger.info(
                    f"SIGNAL #{self.signal_count} | {action} | "
                    f"net={net_score:.2f} | vel={velocity:.2f}"
                )

            return {
                'action': action,
                'symbol': symbol,
                'confidence': round(confidence, 2),
                'strategy': 'sae_deterministic',
                'meta': {
                    'net_score': round(net_score, 2),
                    'velocity': round(velocity, 2),
                    'momentum': round(momentum, 2),
                    'body_strength': round(body_strength, 2),
                    'trend_score': trend_score
                }
            }

        except Exception as e:
            logger.debug(f"Signal error: {e}")
            return None

    def get_parameters(self) -> dict:
        return {
            'window': self.window,
            'threshold': self.threshold,
            'min_net_score': self.min_net_score,
            'min_velocity': self.min_velocity,
            'total_signals': self.signal_count
        }