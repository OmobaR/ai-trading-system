# tests/unit/test_redis_feature_store.py
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os
from unittest.mock import Mock, patch

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.database.redis_feature_store import (
    UnifiedRegimeFeatureStore, 
    BaseRegimeFeatures, 
    NNFXSignals,
    TacticalAllocation
)

class TestUnifiedRegimeFeatureStore:
    @pytest.fixture
    def redis_config(self):
        return {
            'host': 'localhost',
            'port': 6379,
            'db': 0,
            'decode_responses': True
        }
    
    @pytest.fixture
    def sample_ohlcv_data(self):
        return {
            'open': 100.0,
            'high': 102.5,
            'low': 98.5,
            'close': 101.2,
            'volume': 1500
        }
    
    @pytest.fixture
    def sample_historical_data(self):
        dates = pd.date_range('2024-01-01', periods=50, freq='H')
        return pd.DataFrame({
            'open': 100 + np.random.randn(50).cumsum(),
            'high': 102 + np.random.randn(50).cumsum(),
            'low': 98 + np.random.randn(50).cumsum(),
            'close': 101 + np.random.randn(50).cumsum(),
            'volume': np.random.randint(800, 2000, 50)
        }, index=dates)
    
    @pytest.fixture
    def mock_redis(self):
        with patch('redis.Redis') as mock:
            redis_instance = Mock()
            mock.return_value = redis_instance
            redis_instance.ping.return_value = True
            redis_instance.pipeline.return_value = Mock()
            yield redis_instance
    
    def test_initialization(self, redis_config, mock_redis):
        """Test feature store initialization"""
        store = UnifiedRegimeFeatureStore(redis_config)
        
        assert store.client is not None
        assert store.regime_model == 'comprehensive'
        assert 'high_frequency' in store.regime_ttl
        mock_redis.ping.assert_called_once()
    
    @pytest.mark.parametrize("regime_model", [
        'basic', 'technical', 'nnfx', 'comprehensive'
    ])
    def test_different_regime_models(self, redis_config, mock_redis, regime_model):
        """Test initialization with different regime models"""
        store = UnifiedRegimeFeatureStore(redis_config, regime_model=regime_model)
        assert store.regime_model == regime_model
    
    def test_compute_basic_regime_features(self, redis_config, mock_redis, sample_ohlcv_data):
        """Test basic feature computation"""
        store = UnifiedRegimeFeatureStore(redis_config, regime_model='basic')
        
        features = store.compute_basic_regime_features("TEST", sample_ohlcv_data)
        
        assert isinstance(features, BaseRegimeFeatures)
        assert features.volatility > 0
        assert features.trend_strength >= 0
        assert features.volume_profile >= 0
        assert 0 <= features.regime_confidence <= 1
    
    def test_detect_basic_market_regime(self, redis_config, mock_redis):
        """Test basic regime detection"""
        store = UnifiedRegimeFeatureStore(redis_config, regime_model='basic')
        
        # Test different feature combinations
        test_cases = [
            (0.06, 0.03, "trending_high_vol"),   # High vol, high trend
            (0.06, 0.01, "ranging_high_vol"),    # High vol, low trend
            (0.04, 0.03, "trending_low_vol"),    # Low vol, high trend
            (0.04, 0.01, "ranging_low_vol"),     # Low vol, low trend
        ]
        
        for volatility, trend_strength, expected_regime in test_cases:
            features = BaseRegimeFeatures(
                volatility=volatility,
                trend_strength=trend_strength,
                volume_profile=5.0,
                price_momentum=0.01,
                mean_reversion=0.005,
                regime_confidence=0.8
            )
            
            regime = store.detect_basic_market_regime("TEST", features)
            assert regime == expected_regime
    
    def test_compute_unified_regime_features_basic(self, redis_config, mock_redis, sample_ohlcv_data):
        """Test unified feature computation in basic mode"""
        store = UnifiedRegimeFeatureStore(redis_config, regime_model='basic')
        
        features, signals = store.compute_unified_regime_features(
            "TEST", sample_ohlcv_data
        )
        
        assert isinstance(features, BaseRegimeFeatures)
        assert isinstance(signals, NNFXSignals)
        assert features.regime_type in ["trending_high_vol", "ranging_high_vol", 
                                       "trending_low_vol", "ranging_low_vol"]
    
    @patch('talib.ADX')
    @patch('talib.ATR')
    @patch('talib.RSI')
    def test_compute_technical_features(self, mock_rsi, mock_atr, mock_adx, 
                                      redis_config, mock_redis, sample_historical_data):
        """Test technical feature computation"""
        # Mock TA-Lib responses
        mock_adx.return_value = np.array([25.0] * 50)
        mock_atr.return_value = np.array([1.5] * 50)
        mock_rsi.return_value = np.array([55.0] * 50)
        
        store = UnifiedRegimeFeatureStore(redis_config, regime_model='technical')
        
        features = store.compute_technical_features("TEST", sample_historical_data)
        
        assert isinstance(features, BaseRegimeFeatures)
        assert features.adx == 25.0
        assert features.atr == 1.5
        assert features.rsi == 55.0
        assert features.regime_confidence_enhanced > 0
    
    def test_store_ml_features(self, redis_config, mock_redis):
        """Test ML feature storage"""
        store = UnifiedRegimeFeatureStore(redis_config)
        
        features = BaseRegimeFeatures(
            volatility=0.05,
            trend_strength=0.03,
            volume_profile=6.0,
            price_momentum=0.02,
            mean_reversion=0.01,
            regime_confidence=0.85
        )
        
        signals = NNFXSignals(
            nnfx_signal="BUY",
            signal_confidence=0.8,
            baseline_signal="BULLISH",
            confirmation_strength=0.75
        )
        
        # Mock pipeline execution
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 10
        
        store.store_ml_features("TEST", features, "trending_high_vol", signals)
        
        # Verify pipeline was used
        assert mock_pipeline.setex.call_count > 0
        assert mock_pipeline.execute.called
    
    def test_get_current_regime(self, redis_config, mock_redis):
        """Test current regime retrieval"""
        store = UnifiedRegimeFeatureStore(redis_config)
        
        # Mock Redis response
        mock_redis.get.return_value = '"trending_high_vol"'
        
        regime = store.get_current_regime("TEST")
        
        assert regime == "trending_high_vol"
        mock_redis.get.assert_called_with("ml:TEST:regime")
    
    def test_get_bulk_regimes(self, redis_config, mock_redis):
        """Test bulk regime retrieval"""
        store = UnifiedRegimeFeatureStore(redis_config)
        
        # Mock pipeline response
        mock_pipeline = Mock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = ['"trending_high_vol"', '"ranging_low_vol"', None]
        
        symbols = ["SYMBOL1", "SYMBOL2", "SYMBOL3"]
        regimes = store.get_bulk_regimes(symbols)
        
        assert len(regimes) == 3
        assert regimes["SYMBOL1"] == "trending_high_vol"
        assert regimes["SYMBOL2"] == "ranging_low_vol"
        assert regimes["SYMBOL3"] is None
    
    def test_get_regime_statistics(self, redis_config, mock_redis):
        """Test regime statistics calculation"""
        store = UnifiedRegimeFeatureStore(redis_config)
        
        # Mock history data
        mock_history = [
            {'regime': 'trending_high_vol', 'confidence': 0.8},
            {'regime': 'trending_high_vol', 'confidence': 0.9},
            {'regime': 'ranging_low_vol', 'confidence': 0.6},
            {'regime': 'trending_high_vol', 'confidence': 0.85},
        ]
        
        with patch.object(store, 'get_regime_history', return_value=mock_history):
            stats = store.get_regime_statistics("TEST")
            
            assert stats['total_periods'] == 4
            assert stats['current_regime'] == 'trending_high_vol'
            assert 'regime_distribution' in stats
            assert 'regime_stability' in stats
            assert 0 <= stats['regime_stability'] <= 1
    
    def test_calculate_regime_stability(self, redis_config, mock_redis):
        """Test regime stability calculation"""
        store = UnifiedRegimeFeatureStore(redis_config)
        
        # Test stable regime
        stable_regimes = ['trending_high_vol'] * 10
        stability = store._calculate_regime_stability(stable_regimes)
        assert stability == 1.0
        
        # Test changing regime
        changing_regimes = ['trending_high_vol', 'ranging_low_vol'] * 5
        stability = store._calculate_regime_stability(changing_regimes)
        assert stability < 0.5
        
        # Test single regime
        single_regime = ['trending_high_vol']
        stability = store._calculate_regime_stability(single_regime)
        assert stability == 1.0
    
    def test_get_tactical_allocation(self, redis_config, mock_redis):
        """Test tactical allocation calculation"""
        store = UnifiedRegimeFeatureStore(redis_config)
        
        symbols = ["GainX 600", "PainX 400", "TrendX 600"]
        
        # Mock bulk regime response
        with patch.object(store, 'get_bulk_regimes') as mock_bulk:
            mock_bulk.return_value = {
                "GainX 600": "trending_high_vol",
                "PainX 400": "ranging_high_vol", 
                "TrendX 600": "trending_high_vol"
            }
            
            allocation = store.get_tactical_allocation(symbols)
            
            assert isinstance(allocation, TacticalAllocation)
            assert allocation.regime == "trending_high_vol"
            assert allocation.confidence > 0
            assert len(allocation.symbol_weights) == len(symbols)
            assert 'nnfx' in allocation.strategy_weights
    
    def test_export_ml_features(self, redis_config, mock_redis):
        """Test ML feature export"""
        store = UnifiedRegimeFeatureStore(redis_config)
        
        # Mock keys and data
        mock_redis.keys.return_value = [b'ml_training:TEST:20240101_120000']
        mock_redis.get.return_value = '{"symbol": "TEST", "features": {}}'
        
        result = store.export_ml_features_to_csv("TEST", days=7)
        
        assert "Exported" in result or "No training data" in result
        mock_redis.keys.assert_called_with("ml_training:TEST:*")
    
    def test_symbol_regime_profile(self, redis_config, mock_redis):
        """Test comprehensive symbol profile"""
        store = UnifiedRegimeFeatureStore(redis_config)
        
        with patch.object(store, 'get_current_regime', return_value="trending_high_vol"), \
             patch.object(store, 'get_regime_statistics', return_value={'total_periods': 100}), \
             patch.object(store, 'get_ml_features', return_value={'volatility': 0.05}), \
             patch.object(store, 'get_training_data_stats', return_value={'records_per_symbol': {'TEST': 50}}):
            
            profile = store.get_symbol_regime_profile("GainX 600")
            
            assert profile['symbol'] == "GainX 600"
            assert profile['current_regime'] == "trending_high_vol"
            assert profile['symbol_type'] in ['volatility', 'directional', 'synthetic', 'unknown']

if __name__ == "__main__":
    pytest.main([__file__, "-v"])