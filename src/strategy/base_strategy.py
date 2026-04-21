# src/strategy/base_strategy.py
from abc import ABC, abstractmethod
from typing import Dict, Optional
from datetime import datetime

class BaseStrategy(ABC):
    """Abstract base class for all trading strategies in the system."""

    @abstractmethod
    def generate_signal(self, symbol: str, data: Dict, timestamp: datetime) -> Optional[Dict]:
        """
        Generate a trading signal based on the latest market data.
        
        Returns:
            Dict with 'action', 'confidence', 'strategy', 'meta' or None if no signal.
        """
        pass

    def get_parameters(self) -> dict:
        """Return current strategy parameters for logging/optimization."""
        return {}