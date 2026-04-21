import numpy as np
import pandas as pd
import logging
from typing import Dict, Optional, Tuple
import talib
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class NNFXSignal:
    signal: int  # 1 for Buy, -1 for Sell, 0 for Hold
    confidence: float
    regime: str
    indicators: Dict[str, float]
    timestamp: pd.Timestamp

class NNFXStrategy:
    """
    Enhanced NNFX Strategy with regime adaptation and proper technical indicators
    Based on Patrick Victor's No Nonsense Forex methodology
    """
    
    def __init__(self, regime_periods: Dict[str, int] = None):
        self.regime_periods = regime_periods or {
            'trending_high_vol': 50,
            'trending_low_vol': 34,
            'ranging_high_vol': 20,
            'ranging_low_vol': 14
        }
        self.current_regime = 'trending_high_vol'
        
        # NNFX-specific parameters
        self.adx_threshold = 25.0
        self.atr_multiplier = 1.5
        self.rsi_overbought = 70
        self.rsi_oversold = 30
        
    def hull_moving_average(self, data: pd.Series, period: int) -> pd.Series:
        """Calculate Hull Moving Average with proper implementation"""
        if len(data) < period:
            return pd.Series([np.nan] * len(data), index=data.index)
        
        # WMA for half period
        half_period = max(1, period // 2)
        wma_half = data.rolling(window=half_period).apply(
            lambda x: np.average(x, weights=np.arange(1, len(x)+1)), 
            raw=False
        )
        
        # WMA for full period
        wma_full = data.rolling(window=period).apply(
            lambda x: np.average(x, weights=np.arange(1, len(x)+1)), 
            raw=False
        )
        
        # Calculate raw HMA
        raw_hma = 2 * wma_half - wma_full
        
        # WMA of raw HMA with sqrt(period)
        sqrt_period = max(1, int(np.sqrt(period)))
        hma = raw_hma.rolling(window=sqrt_period).apply(
            lambda x: np.average(x, weights=np.arange(1, len(x)+1)), 
            raw=False
        )
        
        return hma

    def adaptive_period(self, data: pd.DataFrame, base_period: int = 20) -> int:
        """
        Calculate adaptive period based on market volatility using ATR
        Higher volatility = longer period, lower volatility = shorter period
        """
        if len(data) < base_period * 2:
            return base_period
            
        atr = talib.ATR(data['high'], data['low'], data['close'], timeperiod=base_period)
        current_atr = atr.iloc[-1] if not atr.empty else 0.0
        
        # Normalize ATR relative to price
        if data['close'].iloc[-1] > 0:
            atr_ratio = current_atr / data['close'].iloc[-1]
        else:
            atr_ratio = 0.0
            
        # Adjust period based on volatility (inverse relationship for responsiveness)
        volatility_factor = 1.0 / (atr_ratio + 0.001)  # Avoid division by zero
        adaptive_period = int(base_period * np.clip(volatility_factor, 0.5, 2.0))
        
        return max(10, min(100, adaptive_period))  # Reasonable bounds

    def calculate_nnfx_indicators(self, data: pd.DataFrame) -> Dict[str, float]:
        """Calculate all NNFX required indicators"""
        if len(data) < 50:  # Need sufficient data
            return {}
            
        close = data['close']
        high = data['high']
        low = data['low']
        
        indicators = {}
        
        try:
            # 1. Baseline - Hull Moving Average
            hma_period = self.adaptive_period(data)
            indicators['hma'] = self.hull_moving_average(close, hma_period).iloc[-1]
            
            # 2. Trend Strength - ADX
            indicators['adx'] = talib.ADX(high, low, close, timeperiod=14).iloc[-1]
            
            # 3. Volatility - ATR
            indicators['atr'] = talib.ATR(high, low, close, timeperiod=14).iloc[-1]
            indicators['atr_pct'] = indicators['atr'] / close.iloc[-1] if close.iloc[-1] > 0 else 0
            
            # 4. Momentum - RSI
            indicators['rsi'] = talib.RSI(close, timeperiod=14).iloc[-1]
            
            # 5. Additional Confirmations
            stoch_k, stoch_d = talib.STOCH(high, low, close)
            indicators['stoch_k'] = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
            indicators['stoch_d'] = stoch_d.iloc[-1] if len(stoch_d) > 0 else 50
            
            macd, macd_signal, _ = talib.MACD(close)
            indicators['macd'] = macd.iloc[-1] if len(macd) > 0 else 0
            indicators['macd_signal'] = macd_signal.iloc[-1] if len(macd_signal) > 0 else 0
            
        except Exception as e:
            logger.error(f"Error calculating NNFX indicators: {e}")
            return {}
            
        return indicators

    def generate_signal(self, symbol: str, df: pd.DataFrame, timestamp: pd.Timestamp) -> Optional[Dict]:
        """
        Generate NNFX trading signal based on current regime and indicators.
        df: DataFrame with columns open, high, low, close, volume (at least 50 rows)
        Returns a dict compatible with the strategy engine.
        """
        if df is None or len(df) < 50:
            return None
        
        # Use current regime (in production you could get it from feature store)
        regime = self.current_regime
        
        # Calculate indicators
        indicators = self.calculate_nnfx_indicators(df)
        if not indicators:
            return None
            
        current_price = df['close'].iloc[-1]
        hma = indicators['hma']
        adx = indicators['adx']
        rsi = indicators['rsi']
        
        # Determine signal based on regime
        signal = 0
        confidence = 0.0
        
        if "trending" in regime:
            # Trending markets: Use trend-following logic
            if adx > self.adx_threshold:  # Strong trend
                if current_price > hma and rsi < self.rsi_overbought:
                    signal = 1  # Buy in uptrend
                    confidence = min(0.9, adx / 50.0)
                elif current_price < hma and rsi > self.rsi_oversold:
                    signal = -1  # Sell in downtrend
                    confidence = min(0.9, adx / 50.0)
                    
        else:  # Ranging markets
            # Use mean-reversion logic
            price_distance = abs(current_price - hma) / hma if hma > 0 else 0
            
            if price_distance > 0.02:  # Significant deviation from HMA
                if current_price > hma and rsi > self.rsi_overbought:
                    signal = -1  # Sell overbought
                    confidence = 0.7
                elif current_price < hma and rsi < self.rsi_oversold:
                    signal = 1  # Buy oversold
                    confidence = 0.7
        
        # Adjust confidence based on multiple confirmations
        if signal != 0:
            # Add confirmation from MACD
            macd_confirm = 1.0 if (signal == 1 and indicators['macd'] > indicators['macd_signal']) or \
                                 (signal == -1 and indicators['macd'] < indicators['macd_signal']) else 0.5
            
            # Add confirmation from Stochastic
            stoch_confirm = 1.0 if (signal == 1 and indicators['stoch_k'] < 20) or \
                                  (signal == -1 and indicators['stoch_k'] > 80) else 0.5
            
            confidence = confidence * 0.6 + macd_confirm * 0.2 + stoch_confirm * 0.2
        
        if signal == 0:
            return None
        
        action = "BUY" if signal == 1 else "SELL"
        return {
            'action': action,
            'symbol': symbol,
            'confidence': round(confidence, 2),
            'strategy': 'nnfx',
            'meta': {
                'adx': round(indicators.get('adx', 0), 1),
                'rsi': round(indicators.get('rsi', 0), 1),
                'regime': regime
            }
        }

    def calculate_position_size(self, signal: NNFXSignal, account_balance: float, 
                              risk_per_trade: float = 0.02) -> Tuple[float, Dict[str, float]]:
        """
        Calculate position size based on ATR volatility and risk management
        """
        if signal.signal == 0 or signal.confidence < 0.6:
            return 0.0, {}
            
        atr = signal.indicators.get('atr', 0)
        if atr <= 0:
            return 0.0, {}
            
        # Risk calculation
        risk_amount = account_balance * risk_per_trade
        stop_loss_distance = atr * self.atr_multiplier
        
        if stop_loss_distance > 0:
            position_size = risk_amount / stop_loss_distance
        else:
            position_size = 0.0
            
        # Adjust position size based on signal confidence
        position_size *= signal.confidence
        
        risk_metrics = {
            'risk_amount': risk_amount,
            'stop_loss_pips': stop_loss_distance,
            'position_size': position_size,
            'risk_reward_ratio': 2.0,  # Fixed 1:2 risk-reward
            'max_position_value': position_size * signal.indicators.get('atr', 1) * 100  # Approximate
        }
        
        return position_size, risk_metrics

    def walk_forward_optimization(self, data: pd.DataFrame, window_size: int = 252, 
                                step_size: int = 63) -> Dict[str, float]:
        """
        Perform walk-forward optimization for strategy parameters
        """
        results = []
        
        for start in range(0, len(data) - window_size, step_size):
            in_sample = data.iloc[start:start + window_size]
            out_sample = data.iloc[start + window_size:start + window_size + step_size]
            
            if len(in_sample) < 50 or len(out_sample) < 20:
                continue
                
            # Optimize parameters on in-sample data (simplified)
            optimal_adx = 25.0  # Would be optimized in real implementation
            optimal_atr_multiplier = 1.5
            
            # Test on out-sample data
            test_strategy = NNFXStrategy()
            test_strategy.adx_threshold = optimal_adx
            test_strategy.atr_multiplier = optimal_atr_multiplier
            
            # Generate signals and calculate performance (simplified)
            signals = []
            for i in range(20, len(out_sample)):
                window_data = out_sample.iloc[:i+1]
                # Note: generate_signal now returns dict; adapt if needed
                signal = test_strategy.generate_signal("test", window_data, pd.Timestamp.now())
                if signal:
                    signals.append(signal)
            
            # Calculate performance metrics (placeholder)
            winning_trades = sum(1 for s in signals if s.get('confidence', 0) > 0.7)
            total_trades = len(signals)
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            results.append({
                'win_rate': win_rate,
                'total_trades': total_trades,
                'optimal_adx': optimal_adx,
                'optimal_atr_multiplier': optimal_atr_multiplier
            })
        
        if results:
            avg_win_rate = np.mean([r['win_rate'] for r in results])
            return {
                'avg_win_rate': avg_win_rate,
                'total_optimization_periods': len(results),
                'recommended_adx_threshold': 25.0,
                'recommended_atr_multiplier': 1.5
            }
        else:
            return {'avg_win_rate': 0, 'total_optimization_periods': 0}

# Example usage and testing (kept for backward compatibility)
if __name__ == "__main__":
    # Create sample data
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    np.random.seed(42)
    prices = 100 + np.random.randn(100).cumsum() * 2
    data = pd.DataFrame({
        'open': prices - np.random.rand(100) * 2,
        'high': prices + np.random.rand(100) * 2,
        'low': prices - np.random.rand(100) * 2,
        'close': prices,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)
    
    # Test strategy
    strategy = NNFXStrategy()
    signal = strategy.generate_signal("TEST", data, pd.Timestamp.now())
    
    print(f"📊 NNFX Strategy Test Results:")
    if signal:
        print(f"Signal: {signal['action']} ({signal['action']})")
        print(f"Confidence: {signal['confidence']:.2%}")
        print(f"ADX: {signal['meta'].get('adx', 0):.2f}")
        print(f"RSI: {signal['meta'].get('rsi', 0):.2f}")
    else:
        print("No signal generated.")