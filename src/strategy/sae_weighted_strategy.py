"""
SAE Weighted Strategy v2 - Stronger, category-aware, no fallback
Uses the improved SSS features for clearer entry conditions
"""

from typing import Dict, Optional
from datetime import datetime
import logging

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class SAEWeightedStrategy(BaseStrategy):
    def __init__(self, symbol: str = None, min_net_score: float = 28, decision_threshold: float = 0.53, **kwargs):
        self.symbol = symbol
        self.min_net_score = min_net_score
        self.decision_threshold = decision_threshold
        self.signal_count = 0
        self.category = self._detect_category(symbol)

        logger.info(f"SAEWeightedStrategy v2 initialized for {symbol} ({self.category}) | min_net_score={self.min_net_score}")

    def _detect_category(self, symbol: str) -> str:
        if any(x in symbol for x in ["GainX", "PainX"]):
            return "synthetics"
        elif "FlipX" in symbol:
            return "probabilistic"
        elif any(x in symbol for x in ["FX Vol", "SFX Vol"]):
            return "volatility"
        elif any(x in symbol for x in ["TrendX", "SwitchX"]):
            return "trend"
        elif "BreakX" in symbol:
            return "breakout"
        return "special"

    def generate_signal(self, symbol: str, data: Dict, timestamp: datetime) -> Optional[Dict]:
        try:
            net_score = float(data.get('net_score', 0))
            bias = int(data.get('bias', 0))
            velocity = float(data.get('velocity', 0))
            state = data.get('state', 'normal')
            pin_bar = float(data.get('pin_bar_score', 0))
            breakout = float(data.get('breakout_score', 0))
            persistence = float(data.get('trend_persistence', 0))

            # Light Gate
            if net_score < self.min_net_score:
                return None

            # Category-aware weights (stronger differentiation)
            if self.category in ["volatility", "probabilistic"]:
                w_net, w_bias, w_vel, w_structure = 0.40, 0.18, 0.26, 0.16
                adj_th = self.decision_threshold - 0.05
            elif self.category == "breakout":
                w_net, w_bias, w_vel, w_structure = 0.34, 0.25, 0.20, 0.21   # favour breakout_score
                adj_th = self.decision_threshold - 0.04
            elif self.category == "trend":
                w_net, w_bias, w_vel, w_structure = 0.36, 0.26, 0.22, 0.16
                adj_th = self.decision_threshold
            else:
                w_net, w_bias, w_vel, w_structure = 0.37, 0.23, 0.24, 0.16
                adj_th = self.decision_threshold + 0.02

            # Weighted decision score
            score = (
                w_net * (net_score / 100.0) +
                w_bias * (1.0 if bias > 0 else 0.0) +
                w_vel * min(abs(velocity) / 30.0, 1.0) +
                w_structure * (pin_bar * 0.4 + breakout * 0.4 + persistence / 100.0)
            )

            if score < adj_th:
                return None

            action = "BUY" if bias >= 0 else "SELL"
            confidence = min(0.62 + score * 0.38, 0.95)

            self.signal_count += 1
            if self.signal_count % 60 == 0:
                logger.info(f"SAEWeighted SIGNAL #{self.signal_count} | {action} | {symbol} | score={score:.3f} | conf={confidence:.2f} | net={net_score:.1f} | cat={self.category}")

            return {
                'action': action,
                'symbol': symbol,
                'confidence': round(confidence, 2),
                'strategy': 'sae_weighted',
                'meta': {
                    'net_score': round(net_score, 1),
                    'score': round(score, 3),
                    'velocity': round(velocity, 3),
                    'bias': bias,
                    'state': state,
                    'pin_bar': round(pin_bar, 2),
                    'breakout': round(breakout, 2),
                    'category': self.category
                }
            }

        except Exception as e:
            logger.debug(f"Signal error for {symbol}: {e}")
            return None

    def get_parameters(self) -> dict:
        return {
            'min_net_score': self.min_net_score,
            'decision_threshold': self.decision_threshold,
            'total_signals': self.signal_count,
            'category': self.category
        }