# src/execution/signal_agent.py
import logging
import sys
import os
from typing import Dict, Any, Optional
from datetime import datetime

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from src.strategy.nnfx_strategy import NNFXStrategy, NNFXSignal
    from src.risk.risk_manager import RiskManagerAgent
    from src.database.redis_feature_store import UnifiedRegimeFeatureStore
    from src.events.event_store import EventStore
except ImportError as e:
    print(f"Import error: {e}")
    # Fallback for when running in DLL context
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SignalAgent:
    """
    Signal Agent that integrates strategy, risk management, and feature store
    Called by DLL bridge for real-time trading signals
    """
    
    def __init__(self, redis_config: Dict, db_config: Dict, risk_capital: float = 10000):
        self.redis_config = redis_config
        self.db_config = db_config
        self.risk_capital = risk_capital
        
        # Initialize components
        try:
            self.feature_store = UnifiedRegimeFeatureStore(redis_config, regime_model='nnfx')
            self.strategy = NNFXStrategy()
            self.risk_manager = RiskManagerAgent(redis_config, risk_capital)
            self.event_store = EventStore(db_config)
            logger.info("✅ Signal Agent initialized successfully")
        except Exception as e:
            logger.error(f"❌ Signal Agent initialization failed: {e}")
            raise
    
    def get_trade_signal(self, symbol: str) -> Dict[str, Any]:
        """
        Generate comprehensive trade signal with risk management
        Called by DLL bridge
        """
        try:
            logger.info(f"🔍 Generating trade signal for {symbol}")
            
            # Get current market features from Redis
            ml_features = self.feature_store.get_ml_features(symbol)
            if not ml_features:
                logger.warning(f"No features found for {symbol}")
                return self._create_error_signal("NO_FEATURES")
            
            # Get regime history for context
            regime_history = self.feature_store.get_regime_history(symbol, limit=10)
            if not regime_history:
                logger.warning(f"No regime history for {symbol}")
                return self._create_error_signal("NO_REGIME_HISTORY")
            
            # Convert features to DataFrame format for strategy
            # Note: In production, you'd get actual OHLCV data from TimescaleDB
            strategy_data = self._prepare_strategy_data(ml_features, regime_history)
            
            # Get current regime
            current_regime = ml_features.get('regime', 'unknown')
            
            # Generate strategy signal
            signal = self.strategy.generate_signal(symbol, strategy_data, current_regime)
            
            # Skip if no valid signal
            if signal.signal == 0 or signal.confidence < 0.6:
                return {
                    'type': 0,  # No trade
                    'volume': 0.0,
                    'sl': 0.0,
                    'tp': 0.0,
                    'confidence': signal.confidence,
                    'regime': current_regime,
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            # Get risk-managed position size
            position_size, risk_metrics = self.strategy.calculate_position_size(
                signal, self.risk_capital
            )
            
            # Calculate stop loss and take profit based on ATR
            atr = signal.indicators.get('atr', 1.0)
            sl_points = atr * 1.5  # 1.5x ATR for stop loss
            tp_points = atr * 3.0  # 3.0x ATR for take profit
            
            # Create final signal
            trade_signal = {
                'type': signal.signal,  # 1 for Buy, -1 for Sell
                'volume': position_size,
                'sl': sl_points,
                'tp': tp_points,
                'confidence': signal.confidence,
                'regime': current_regime,
                'symbol': symbol,
                'timestamp': datetime.utcnow().isoformat(),
                'risk_metrics': risk_metrics
            }
            
            # Log the signal
            self._log_signal(symbol, trade_signal, signal)
            
            logger.info(f"🎯 Generated signal for {symbol}: {trade_signal}")
            return trade_signal
            
        except Exception as e:
            logger.error(f"❌ Error generating signal for {symbol}: {e}")
            return self._create_error_signal(f"ERROR: {str(e)}")
    
    def _prepare_strategy_data(self, ml_features: Dict, regime_history: list):
        """Prepare data for strategy consumption"""
        # This is a simplified version - in production, you'd get actual OHLCV data
        import pandas as pd
        import numpy as np
        
        # Create mock data based on features (replace with real data in production)
        dates = pd.date_range(end=datetime.now(), periods=50, freq='H')
        data = pd.DataFrame({
            'open': np.random.randn(50).cumsum() + 100,
            'high': np.random.randn(50).cumsum() + 102,
            'low': np.random.randn(50).cumsum() + 98,
            'close': np.random.randn(50).cumsum() + 101,
            'volume': np.random.randint(800, 2000, 50)
        }, index=dates)
        
        # Update last row with current features if available
        if ml_features:
            current_price = ml_features.get('close', 100)
            data.iloc[-1] = {
                'open': current_price - 0.5,
                'high': current_price + 1.0,
                'low': current_price - 1.0,
                'close': current_price,
                'volume': 1500
            }
        
        return data
    
    def _create_error_signal(self, error_msg: str) -> Dict[str, Any]:
        """Create error signal response"""
        return {
            'type': -1,  # Error code
            'volume': 0.0,
            'sl': 0.0,
            'tp': 0.0,
            'error': error_msg,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def _log_signal(self, symbol: str, trade_signal: Dict, original_signal: NNFXSignal):
        """Log signal to event store"""
        try:
            self.event_store.append_event(
                event_type='trade_signal_generated',
                aggregate_id=f"signal_{symbol}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                data=trade_signal,
                metadata={
                    'symbol': symbol,
                    'strategy': 'nnfx',
                    'original_confidence': original_signal.confidence,
                    'indicators': original_signal.indicators
                }
            )
        except Exception as e:
            logger.warning(f"Could not log signal to event store: {e}")

# Global instance for DLL access
_signal_agent_instance = None

def get_trade_signal(symbol: str) -> Dict[str, Any]:
    """
    Main function called by DLL bridge
    This maintains compatibility with the existing C++ bridge code
    """
    global _signal_agent_instance
    
    try:
        # Lazy initialization
        if _signal_agent_instance is None:
            redis_config = {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'decode_responses': False
            }
            db_config = {
                'dbname': 'ai_trading_db',
                'user': 'postgres',
                'password': 'password',
                'host': 'localhost',
                'port': 5432
            }
            _signal_agent_instance = SignalAgent(redis_config, db_config)
        
        return _signal_agent_instance.get_trade_signal(symbol)
        
    except Exception as e:
        logger.error(f"❌ Error in get_trade_signal: {e}")
        return {
            'type': -1,
            'volume': 0.0,
            'sl': 0.0,
            'tp': 0.0,
            'error': f"Initialization error: {str(e)}"
        }

# Test function
if __name__ == "__main__":
    # Test the signal agent
    redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
    db_config = {
        'dbname': 'ai_trading_db',
        'user': 'postgres', 
        'password': 'password',
        'host': 'localhost',
        'port': 5432
    }
    
    agent = SignalAgent(redis_config, db_config)
    test_signal = agent.get_trade_signal("GainX 600")
    print(f"Test Signal: {test_signal}")