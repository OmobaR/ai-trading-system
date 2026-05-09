# src/strategy/sae_strategy.py
"""
SAEStrategy - Real adapter to MQL5 SAE Suite
Reads SAE_* global variables via MT5GlobalReader.
Supports your preferences: RSI(5) divergence + tunable NetScore threshold.
Exits remain in MQL5 ExitManager.
"""

from typing import Dict, Optional
from datetime import datetime
import logging
import pandas as pd

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class SAEStrategy(BaseStrategy):
    def __init__(self,
                 min_net_score: float = 55,
                 use_divergence: bool = True,
                 use_rsi_extreme: bool = True,
                 signal_system: str = "BOTH",
                 **kwargs):
        
        self.min_net_score = min_net_score
        self.use_divergence = use_divergence
        self.use_rsi_extreme = use_rsi_extreme
        self.signal_system = signal_system.upper()
        self.signal_count = 0
        self.reader = None

        logger.info(f"SAEStrategy (REAL MQL5) initialized | min_net_score={min_net_score}, system={signal_system}")

    def set_reader(self, reader):
        """Inject the global variable reader (MT5GlobalReader)."""
        self.reader = reader
        logger.info("✅ MT5 Global Reader connected to SAEStrategy")

    def generate_signal(self, symbol: str, df: pd.DataFrame, timestamp: datetime) -> Optional[Dict]:
        """
        Required by BaseStrategy. For SAE, we use on_tick with price only.
        This method extracts the latest close price and calls on_tick.
        """
        if df is None or df.empty:
            return None
        price = df['close'].iloc[-1]
        return self.on_tick(symbol, price, timestamp)

    def on_tick(self, symbol: str, price: float, timestamp: datetime) -> Optional[Dict]:
        """Main signal handler – called by orchestrator."""
        if not self.reader:
            logger.warning(f"No reader set for {symbol}")
            return None

        try:
            # Read SAE globals
            bias = self.reader.get_global(f"SAE_{symbol}_Bias") or 0
            net_score = self.reader.get_global(f"SAE_{symbol}_NetScore") or 0
            m1vel_score = self.reader.get_global(f"SAE_{symbol}_M1VelScore") or 0
            bull_div = bool(self.reader.get_global(f"SAE_{symbol}_BullDiv_M15") or 
                           self.reader.get_global(f"SAE_{symbol}_BullDiv_H1"))
            bear_div = bool(self.reader.get_global(f"SAE_{symbol}_BearDiv_M15") or 
                           self.reader.get_global(f"SAE_{symbol}_BearDiv_H1"))
            rsi5_h1 = self.reader.get_global(f"SAE_{symbol}_RSI5_H1") or 50.0

            if bias == 0:
                return None

            signal = None

            # NetScore path
            if self.signal_system in ["NETSCORE", "BOTH"]:
                if net_score >= self.min_net_score and m1vel_score >= 20:
                    action = "BUY" if bias > 0 else "SELL"
                    signal = self._make_signal(symbol, action, net_score, "NETSCORE")

            # Divergence / RSI(5) path
            if not signal and self.signal_system in ["DIVERGENCE_RSI", "BOTH"]:
                if (bias > 0 and (bull_div or (self.use_rsi_extreme and rsi5_h1 <= 20))) or \
                   (bias < 0 and (bear_div or (self.use_rsi_extreme and rsi5_h1 >= 80))):
                    action = "BUY" if bias > 0 else "SELL"
                    signal = self._make_signal(symbol, action, net_score or 50, "DIVERGENCE_RSI")

            if signal:
                self.signal_count += 1
                if self.signal_count % 40 == 0:
                    logger.info(f"SAE SIGNAL #{self.signal_count} | {signal['action']} | {symbol} | "
                                f"NetScore={net_score:.1f} | conf={signal['confidence']:.2f} | source={signal['source']}")

            return signal

        except Exception as e:
            logger.debug(f"SAE on_tick error for {symbol}: {e}")
            return None

    def _make_signal(self, symbol: str, action: str, net_score: float, source: str) -> Dict:
        confidence = min(0.65 + (net_score / 100.0) * 0.35, 0.96)
        return {
            'action': action,
            'symbol': symbol,
            'confidence': round(confidence, 2),
            'strategy': 'sae',
            'source': source,
            'meta': {
                'net_score': round(net_score, 1),
                'timestamp': datetime.utcnow().isoformat()
            }
        }

    def get_parameters(self) -> dict:
        return {
            'min_net_score': self.min_net_score,
            'use_divergence': self.use_divergence,
            'use_rsi_extreme': self.use_rsi_extreme,
            'signal_system': self.signal_system,
            'total_signals': self.signal_count
        }