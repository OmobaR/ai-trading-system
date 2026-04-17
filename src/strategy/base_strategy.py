# src/strategy/base_strategy.py
from abc import ABC, abstractmethod
from typing import Dict, Optional
from datetime import datetime

class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    @abstractmethod
    def on_data(self, symbol: str, data: Dict, timestamp: datetime) -> Optional[Dict]:
        """
        Called whenever new market data arrives.
        data: dictionary containing at least 'open','high','low','close','volume'
        Returns a signal dict with keys: 'action' (BUY/SELL/HOLD), 'confidence', 'position_size', etc.
        """
        pass

    def get_parameters(self) -> dict:
        """Return current strategy parameters for logging/optimisation."""
        return {}