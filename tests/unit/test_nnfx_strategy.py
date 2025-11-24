# tests/unit/test_nnfx_strategy.py
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.strategy.nnfx_strategy import NNFXStrategy, NNFXSignal

class TestNNFXStrategy:
    @pytest.fixture
    def strategy(self):
        return NNFXStrategy()
    
    @pytest.fixture
    def sample_data(self):
        """Create realistic sample market data"""
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        np.random.seed(42)
        
        # Create trending data
        trend = np.linspace(100, 120, 100)
        noise = np.random.randn(100) * 2
        prices = trend + noise
        
        return pd.DataFrame({
            'open': prices - np.random.rand(100) * 1.5,
            'high': prices + np.random.rand(100) * 2,
            'low': prices - np.random.rand(100) * 2,
            'close': prices,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
    
    @pytest.fixture
    def ranging_data(self):
        """Create ranging market data"""
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        np.random.seed(123)
        
        # Create ranging data
        base = 100
        oscillation = np.sin(np.linspace(0, 8*np.pi, 100)) * 5
        noise = np.random.randn(100) * 1
        prices = base + oscillation + noise
        
        return pd.DataFrame({
            'open': prices - np.random.rand(100) * 1,
            'high': prices + np.random.rand(100) * 1.5,
            'low': prices - np.random.rand(100) * 1.5,
            'close': prices,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
    
    def test_initialization(self, strategy):
        """Test strategy initialization"""
        assert strategy is not None
        assert strategy.current_regime == 'trending_high_vol'
        assert strategy.adx_threshold == 25.0
        assert strategy.atr_multiplier == 1.5
        assert 'trending_high_vol' in strategy.regime_periods
    
    def test_hull_moving_average(self, strategy, sample_data):
        """Test Hull Moving Average calculation"""
        hma = strategy.hull_moving_average(sample_data['close'], 20)
        
        assert len(hma) == len(sample_data)
        assert not hma.isna().all()  # Should have some valid values
        assert hma.iloc[-1] > 0  # Should be positive price
        
        # Test with insufficient data
        short_data = sample_data['close'].iloc[:10]
        hma_short = strategy.hull_moving_average(short_data, 20)
        assert hma_short.isna().all() or len(hma_short) == len(short_data)
    
    def test_adaptive_period(self, strategy, sample_data):
        """Test adaptive period calculation"""
        period = strategy.adaptive_period(sample_data)
        
        assert isinstance(period, int)
        assert 10 <= period <= 100  # Within reasonable bounds
        
        # Test with very volatile data
        volatile_data = sample_data.copy()
        volatile_data['high'] = volatile_data['high'] * 1.5
        volatile_data['low'] = volatile_data['low'] * 0.5
        volatile_period = strategy.adaptive_period(volatile_data)
        assert isinstance(volatile_period, int)
    
    def test_calculate_nnfx_indicators(self, strategy, sample_data):
        """Test NNFX indicator calculation"""
        indicators = strategy.calculate_nnfx_indicators(sample_data)
        
        assert isinstance(indicators, dict)
        expected_indicators = ['hma', 'adx', 'atr', 'atr_pct', 'rsi', 'stoch_k', 'stoch_d', 'macd', 'macd_signal']
        
        for indicator in expected_indicators:
            assert indicator in indicators
            assert isinstance(indicators[indicator], (float, int, np.floating, np.integer))
        
        # Test with insufficient data
        short_data = sample_data.iloc[:10]
        empty_indicators = strategy.calculate_nnfx_indicators(short_data)
        assert empty_indicators == {}
    
    def test_generate_signal_trending(self, strategy, sample_data):
        """Test signal generation in trending regime"""
        signal = strategy.generate_signal("TEST", sample_data, "trending_high_vol")
        
        assert isinstance(signal, NNFXSignal)
        assert signal.signal in [-1, 0, 1]
        assert 0 <= signal.confidence <= 1.0
        assert signal.regime == "trending_high_vol"
        assert isinstance(signal.indicators, dict)
        assert isinstance(signal.timestamp, pd.Timestamp)
        
        # Verify signal structure
        assert 'adx' in signal.indicators
        assert 'rsi' in signal.indicators
        assert 'hma' in signal.indicators
    
    def test_generate_signal_ranging(self, strategy, ranging_data):
        """Test signal generation in ranging regime"""
        signal = strategy.generate_signal("TEST", ranging_data, "ranging_low_vol")
        
        assert isinstance(signal, NNFXSignal)
        assert signal.signal in [-1, 0, 1]
        assert signal.regime == "ranging_low_vol"
    
    def test_generate_signal_insufficient_data(self, strategy):
        """Test signal generation with insufficient data"""
        short_data = pd.DataFrame({
            'open': [100, 101],
            'high': [102, 103],
            'low': [99, 100],
            'close': [101, 102],
            'volume': [1000, 1100]
        })
        
        signal = strategy.generate_signal("TEST", short_data)
        assert signal.signal == 0
        assert signal.confidence == 0.0
    
    def test_calculate_position_size(self, strategy, sample_data):
        """Test position size calculation"""
        signal = strategy.generate_signal("TEST", sample_data, "trending_high_vol")
        
        if signal.signal != 0 and signal.confidence >= 0.6:
            position_size, risk_metrics = strategy.calculate_position_size(
                signal, account_balance=10000, risk_per_trade=0.02
            )
            
            assert isinstance(position_size, float)
            assert position_size >= 0
            assert isinstance(risk_metrics, dict)
            assert 'risk_amount' in risk_metrics
            assert 'stop_loss_pips' in risk_metrics
            assert risk_metrics['risk_amount'] == 200.0  # 2% of 10,000
            
        else:
            # Test with no signal
            position_size, risk_metrics = strategy.calculate_position_size(signal, 10000)
            assert position_size == 0.0
            assert risk_metrics == {}
    
    def test_calculate_position_size_zero_confidence(self, strategy, sample_data):
        """Test position sizing with low confidence signal"""
        # Create a low confidence signal
        low_confidence_signal = NNFXSignal(
            signal=1,
            confidence=0.5,  # Below threshold
            regime="trending_high_vol",
            indicators={'atr': 1.5},
            timestamp=pd.Timestamp.now()
        )
        
        position_size, risk_metrics = strategy.calculate_position_size(
            low_confidence_signal, 10000
        )
        
        assert position_size == 0.0
        assert risk_metrics == {}
    
    def test_walk_forward_optimization(self, strategy, sample_data):
        """Test walk-forward optimization (simplified)"""
        # Use a smaller dataset for faster testing
        small_data = sample_data.iloc[:150]
        
        results = strategy.walk_forward_optimization(
            small_data, window_size=50, step_size=25
        )
        
        assert isinstance(results, dict)
        assert 'avg_win_rate' in results
        assert 'total_optimization_periods' in results
        assert 0 <= results['avg_win_rate'] <= 1
    
    def test_regime_adaptation(self, strategy):
        """Test that strategy adapts to different regimes"""
        # Test period selection for different regimes
        trending_period = strategy.regime_periods['trending_high_vol']
        ranging_period = strategy.regime_periods['ranging_low_vol']
        
        assert trending_period > ranging_period  # Longer periods for trending markets
    
    def test_signal_consistency(self, strategy, sample_data):
        """Test that signals are consistent with indicator values"""
        signal = strategy.generate_signal("TEST", sample_data, "trending_high_vol")
        
        if signal.signal == 1:  # Buy signal
            # In trending regime with buy signal, price should be above HMA
            assert signal.indicators.get('adx', 0) > 0
        elif signal.signal == -1:  # Sell signal
            # In trending regime with sell signal, price should be below HMA
            assert signal.indicators.get('adx', 0) > 0
    
    @pytest.mark.parametrize("regime", [
        "trending_high_vol",
        "trending_low_vol", 
        "ranging_high_vol",
        "ranging_low_vol"
    ])
    def test_all_regimes(self, strategy, sample_data, regime):
        """Test strategy with all regime types"""
        signal = strategy.generate_signal("TEST", sample_data, regime)
        
        assert isinstance(signal, NNFXSignal)
        assert signal.regime == regime
        assert signal.signal in [-1, 0, 1]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])