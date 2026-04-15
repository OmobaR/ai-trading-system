#src/database/redis_feature_store.py
import redis
import json
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import talib
import hashlib
from hmmlearn import hmm
from sklearn.mixture import GaussianMixture

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BaseRegimeFeatures:
    """Base feature set for comprehensive market regime detection"""
    # Core regime features
    volatility: float
    trend_strength: float
    volume_profile: float
    price_momentum: float
    mean_reversion: float
    regime_confidence: float
    
    # Enhanced features
    adx: float = 0.0
    atr: float = 0.0
    rsi: float = 0.0
    kama: float = 0.0
    stoch_k: float = 0.0
    stoch_d: float = 0.0
    
    # Regime classification
    regime_type: str = "unknown"
    regime_confidence_enhanced: float = 0.0

@dataclass  
class NNFXSignals:
    """NNFX-specific trading signals"""
    nnfx_signal: str = "HOLD"
    signal_confidence: float = 0.0
    baseline_signal: str = "NEUTRAL"
    confirmation_strength: float = 0.0

@dataclass
class TacticalAllocation:
    """Regime-based portfolio allocation"""
    regime: str
    symbol_weights: Dict[str, float]
    strategy_weights: Dict[str, float]
    risk_multiplier: float
    confidence: float

class UnifiedRegimeFeatureStore:
    """
    Comprehensive feature store supporting multiple regime detection methods:
    - Basic rule-based regimes
    - NNFX-based regimes 
    - Technical indicator enhanced regimes
    - Probabilistic models (HMM, GMM)
    - ML-ready feature storage and export
    """
    
    def __init__(self, redis_config, regime_model='comprehensive'):
        self.client = redis.Redis(**redis_config)
        self.regime_model = regime_model
        
        try:
            self.client.ping()
            logger.info(f"✅ Connected to Redis with {regime_model} regime detection")
        except redis.ConnectionError as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise
        
        # Enhanced TTL configuration
        self.regime_ttl = {
            'high_frequency': 300,
            'medium_term': 3600, 
            'long_term': 86400,
            'persistent': 0,
            'extended_history': 604800
        }
        
        # Feature templates for different symbol types
        self.symbol_patterns = {
            'volatility': ['GainX', 'PainX', 'FX Vol', 'SFX Vol'],
            'directional': ['FlipX', 'TrendX', 'BreakX', 'SwitchX'],
            'synthetic': ['GainX', 'PainX', 'FlipX', 'FX Vol', 'SFX Vol', 'TrendX', 'SwitchX', 'BreakX']
        }
        
        # NNFX-specific thresholds
        self.nnfx_thresholds = {
            'adx_trending': 25.0,
            'atr_filter': 0.002,
            'rsi_overbought': 70.0,
            'rsi_oversold': 30.0,
            'stoch_overbought': 80.0,
            'stoch_oversold': 20.0
        }

        # Probabilistic models
        self.probabilistic_models = {}
        self.regime_states = {
            'hmm': ['high_vol_trend', 'low_vol_trend', 'high_vol_range', 'low_vol_range', 'transition'],
            'gmm': ['high_vol_bull', 'low_vol_bull', 'high_vol_bear', 'low_vol_bear', 'neutral']
        }

    # ===== CORE REGIME FEATURE METHODS =====
    
    def compute_basic_regime_features(self, symbol: str, ohlcv_data: Dict) -> BaseRegimeFeatures:
        """Compute comprehensive basic features for regime detection"""
        open_price = ohlcv_data.get('open', 0)
        high = ohlcv_data.get('high', 0)
        low = ohlcv_data.get('low', 0)
        close = ohlcv_data.get('close', 0)
        volume = ohlcv_data.get('volume', 1)
        
        # 1. Volatility features
        price_range = high - low
        volatility = price_range / open_price if open_price else 0
        
        # 2. Trend strength
        price_change = close - open_price
        trend_strength = abs(price_change) / open_price if open_price else 0
        
        # 3. Volume profile (normalized)
        volume_profile = min(volume / 1000.0, 10.0)
        
        # 4. Price momentum
        price_momentum = price_change / open_price if open_price else 0
        
        # 5. Mean reversion tendency
        typical_price = (high + low + close) / 3
        mean_reversion = abs(close - typical_price) / typical_price if typical_price else 0
        
        # 6. Regime confidence
        regime_confidence = self._calculate_basic_regime_confidence(
            volatility, trend_strength, volume_profile
        )
        
        return BaseRegimeFeatures(
            volatility=volatility,
            trend_strength=trend_strength,
            volume_profile=volume_profile,
            price_momentum=price_momentum,
            mean_reversion=mean_reversion,
            regime_confidence=regime_confidence
        )
    
    def _calculate_basic_regime_confidence(self, volatility: float, trend_strength: float, volume: float) -> float:
        """Calculate confidence score for basic regime classification"""
        confidence = (volatility * 0.3 + trend_strength * 0.4 + volume * 0.3)
        return min(confidence, 1.0)
    
    def detect_basic_market_regime(self, symbol: str, features: BaseRegimeFeatures) -> str:
        """Detect current market regime based on basic features"""
        if features.volatility > 0.05 and features.trend_strength > 0.02:
            return "trending_high_vol"
        elif features.volatility > 0.05 and features.trend_strength <= 0.02:
            return "ranging_high_vol"
        elif features.volatility <= 0.05 and features.trend_strength > 0.02:
            return "trending_low_vol"
        else:
            return "ranging_low_vol"

    # ===== ENHANCED TECHNICAL FEATURE METHODS =====
    
    def compute_technical_features(self, symbol: str, historical_data: pd.DataFrame) -> BaseRegimeFeatures:
        """Compute enhanced technical features using TA-Lib"""
        if len(historical_data) < 20:
            return self.compute_basic_regime_features(symbol, historical_data.iloc[-1].to_dict() if not historical_data.empty else {})
        
        high = historical_data['high'].values
        low = historical_data['low'].values  
        close = historical_data['close'].values
        volume = historical_data['volume'].values
        
        basic_features = self.compute_basic_regime_features(symbol, historical_data.iloc[-1].to_dict())
        
        try:
            # Trend strength indicators
            adx = talib.ADX(high, low, close, timeperiod=14)[-1] if len(close) >= 14 else 25.0
            
            # Volatility indicators
            atr = talib.ATR(high, low, close, timeperiod=14)[-1] if len(close) >= 14 else 0.0
            
            # Momentum indicators
            rsi = talib.RSI(close, timeperiod=14)[-1] if len(close) >= 14 else 50.0
            
            # Adaptive moving average
            kama = talib.KAMA(close, timeperiod=20)[-1] if len(close) >= 20 else close[-1]
            
            # Oscillators - FIXED
            if len(close) >= 14:
                slowk, slowd = talib.STOCH(high, low, close)
                stoch_k = slowk[-1] if len(slowk) > 0 else 50.0
                stoch_d = slowd[-1] if len(slowd) > 0 else 50.0
            else:
                stoch_k, stoch_d = 50.0, 50.0
            
            basic_features.adx = adx
            basic_features.atr = atr
            basic_features.rsi = rsi
            basic_features.kama = kama
            basic_features.stoch_k = stoch_k
            basic_features.stoch_d = stoch_d
            
            basic_features.regime_confidence_enhanced = self._calculate_enhanced_confidence(
                basic_features, adx, atr, rsi
            )
            
        except Exception as e:
            logger.warning(f"Technical indicator computation failed for {symbol}: {e}")
        
        return basic_features
    
    def _calculate_enhanced_confidence(self, features: BaseRegimeFeatures, adx: float, atr: float, rsi: float) -> float:
        """Calculate enhanced confidence using technical indicators"""
        basic_confidence = features.regime_confidence
        
        adx_strength = min(adx / 50.0, 1.0)
        atr_strength = min(atr / (features.volatility + 0.001), 2.0)
        rsi_clarity = 1.0 - abs(rsi - 50.0) / 50.0
        
        technical_confidence = (adx_strength * 0.4 + atr_strength * 0.3 + rsi_clarity * 0.3)
        
        combined = (basic_confidence * 0.6 + technical_confidence * 0.4)
        return min(combined, 1.0)
    
    def detect_technical_regime(self, symbol: str, features: BaseRegimeFeatures) -> str:
        """Detect regime using technical indicators"""
        is_trending = features.adx > self.nnfx_thresholds['adx_trending']
        is_high_vol = features.volatility > 0.05

        if is_trending and is_high_vol:
            return "trending_high_vol"
        elif is_trending and not is_high_vol:
            return "trending_low_vol" 
        elif not is_trending and is_high_vol:
            return "ranging_high_vol"
        else:
            return "ranging_low_vol"

    # ===== NNFX-SPECIFIC METHODS =====
    
    def compute_nnfx_signals(self, symbol: str, features: BaseRegimeFeatures) -> NNFXSignals:
        """Generate NNFX-specific trading signals"""
        signals = NNFXSignals()
        
        if "trending" not in features.regime_type:
            signals.nnfx_signal = "HOLD"
            signals.signal_confidence = 0.3
            return signals
        
        current_price = features.kama
        price_above_kama = current_price > features.kama
        
        strong_trend = features.adx > 30.0
        momentum_bullish = (features.rsi > 50.0 and features.stoch_k > features.stoch_d and features.stoch_k > 50.0)
        momentum_bearish = (features.rsi < 50.0 and features.stoch_k < features.stoch_d and features.stoch_k < 50.0)
        
        if price_above_kama and strong_trend and momentum_bullish:
            signals.nnfx_signal = "BUY"
            signals.baseline_signal = "BULLISH"
            signals.signal_confidence = min(0.9, features.regime_confidence_enhanced)
        elif not price_above_kama and strong_trend and momentum_bearish:
            signals.nnfx_signal = "SELL" 
            signals.baseline_signal = "BEARISH"
            signals.signal_confidence = min(0.9, features.regime_confidence_enhanced)
        else:
            signals.nnfx_signal = "HOLD"
            signals.baseline_signal = "NEUTRAL"
            signals.signal_confidence = 0.5
        
        signals.confirmation_strength = features.adx / 50.0
        
        return signals

    # ===== PROBABILISTIC MODEL METHODS =====
    
    def setup_probabilistic_regimes(self, model_type='hmm'):
        """Setup for probabilistic regime detection models"""
        self.probabilistic_models = {}
        logger.info(f"Initialized probabilistic regime models for {model_type}")

    def compute_probabilistic_regime(self, symbol: str, feature_matrix: np.ndarray, model_type='hmm'):
        """Compute regime using probabilistic models"""
        if model_type not in self.probabilistic_models:
            self._train_probabilistic_model(symbol, feature_matrix, model_type)
        
        model = self.probabilistic_models.get(f"{symbol}_{model_type}")
        if model and feature_matrix.size > 0:
            try:
                probabilities = model.predict_proba(feature_matrix.reshape(1, -1))
                regime_idx = np.argmax(probabilities)
                confidence = probabilities[0][regime_idx]
                
                return {
                    'regime': self.regime_states[model_type][regime_idx],
                    'confidence': float(confidence),
                    'probabilities': probabilities[0].tolist(),
                    'model': model_type
                }
            except Exception as e:
                logger.warning(f"Probabilistic prediction failed: {e}")
        
        return None

    def _train_probabilistic_model(self, symbol: str, features: np.ndarray, model_type='hmm'):
        """Train probabilistic model on historical features"""
        try:
            if model_type == 'hmm':
                model = hmm.GaussianHMM(n_components=5, covariance_type="diag", n_iter=1000, random_state=42)
            elif model_type == 'gmm':
                model = GaussianMixture(n_components=5, covariance_type='full', random_state=42)
            else:
                return
            
            if features.size == 0:
                return
                
            training_data = features.reshape(-1, 1) if len(features.shape) == 1 else features
            
            if len(training_data) > 0:
                model.fit(training_data)
                self.probabilistic_models[f"{symbol}_{model_type}"] = model
                logger.info(f"Trained {model_type} model for {symbol}")
                
        except Exception as e:
            logger.error(f"Failed to train {model_type} model: {e}")

    def detect_volatility_regimes(self, symbol: str, lookback_days: int = 30):
        """Use GMM to cluster volatility regimes"""
        history = self.get_regime_history(symbol, limit=lookback_days * 24, extended=True)
        
        if len(history) < 50:
            return None
        
        volatilities = []
        volumes = []
        for event in history:
            if 'volatility' in event and 'volume_profile' in event:
                volatilities.append(event['volatility'])
                volumes.append(event['volume_profile'])
        
        if len(volatilities) < 50:
            return None
            
        X = np.column_stack([volatilities, volumes])
        
        try:
            gmm = GaussianMixture(n_components=3, covariance_type='full', random_state=42)
            clusters = gmm.fit_predict(X)
            
            cluster_stats = {}
            for cluster_id in range(3):
                cluster_data = X[clusters == cluster_id]
                if len(cluster_data) > 0:
                    cluster_stats[cluster_id] = {
                        'mean_volatility': np.mean(cluster_data[:, 0]),
                        'mean_volume': np.mean(cluster_data[:, 1]),
                        'count': len(cluster_data),
                        'regime_label': self._label_volatility_cluster(cluster_data)
                    }
            
            current_features = np.array([[volatilities[0], volumes[0]]])
            current_cluster = gmm.predict(current_features)[0]
            
            return {
                'current_regime': cluster_stats[current_cluster]['regime_label'],
                'cluster_stats': cluster_stats,
                'model': 'gmm_volatility',
                'confidence': max(gmm.predict_proba(current_features)[0])
            }
        except Exception as e:
            logger.error(f"GMM volatility detection failed: {e}")
            return None

    def _label_volatility_cluster(self, cluster_data):
        """Label volatility clusters based on characteristics"""
        if cluster_data.size == 0:
            return "unknown"
            
        mean_vol = np.mean(cluster_data[:, 0])
        mean_vol_idx = np.mean(cluster_data[:, 1])
        
        if mean_vol > 0.06 and mean_vol_idx > 5:
            return "high_vol_high_volume"
        elif mean_vol > 0.06 and mean_vol_idx <= 5:
            return "high_vol_low_volume"
        elif mean_vol <= 0.03 and mean_vol_idx > 5:
            return "low_vol_high_volume"
        else:
            return "low_vol_low_volume"

    # ===== UNIFIED REGIME DETECTION =====
    
    def compute_unified_regime_features(self, symbol: str, ohlcv_data: Dict, historical_data: pd.DataFrame = None) -> Tuple[BaseRegimeFeatures, NNFXSignals]:
        """Unified method to compute all features based on regime model"""
        
        if self.regime_model == 'basic':
            features = self.compute_basic_regime_features(symbol, ohlcv_data)
            features.regime_type = self.detect_basic_market_regime(symbol, features)
            signals = NNFXSignals()
            
        elif self.regime_model == 'technical':
            if historical_data is not None and len(historical_data) >= 20:
                features = self.compute_technical_features(symbol, historical_data)
                features.regime_type = self.detect_technical_regime(symbol, features)
            else:
                features = self.compute_basic_regime_features(symbol, ohlcv_data)
                features.regime_type = self.detect_basic_market_regime(symbol, features)
            signals = NNFXSignals()
            
        elif self.regime_model == 'nnfx':
            if historical_data is not None and len(historical_data) >= 20:
                features = self.compute_technical_features(symbol, historical_data)
                features.regime_type = self.detect_technical_regime(symbol, features)
                signals = self.compute_nnfx_signals(symbol, features)
            else:
                features = self.compute_basic_regime_features(symbol, ohlcv_data)
                features.regime_type = self.detect_basic_market_regime(symbol, features)
                signals = NNFXSignals()
                
        else:  # 'comprehensive' - default
            if historical_data is not None and len(historical_data) >= 20:
                features = self.compute_technical_features(symbol, historical_data)
                features.regime_type = self.detect_technical_regime(symbol, features)
                signals = self.compute_nnfx_signals(symbol, features)
            else:
                features = self.compute_basic_regime_features(symbol, ohlcv_data)
                features.regime_type = self.detect_basic_market_regime(symbol, features)
                signals = NNFXSignals()
        
        return features, signals

    # ===== HYBRID STORAGE METHODS =====
    
    def store_ml_features(self, symbol: str, features: BaseRegimeFeatures, regime: str, signals: NNFXSignals = None):
        """Store features for ML model serving (individual keys)"""
        timestamp = datetime.utcnow().isoformat()
        
        feature_data = {
            'volatility': features.volatility,
            'trend_strength': features.trend_strength,
            'volume_profile': features.volume_profile,
            'price_momentum': features.price_momentum,
            'mean_reversion': features.mean_reversion,
            'regime_confidence': features.regime_confidence,
            'regime': regime,
            'timestamp': timestamp,
            'symbol': symbol
        }
        
        if features.adx > 0:
            feature_data.update({
                'adx': features.adx,
                'atr': features.atr,
                'rsi': features.rsi,
                'kama': features.kama,
                'stoch_k': features.stoch_k,
                'stoch_d': features.stoch_d,
                'regime_confidence_enhanced': features.regime_confidence_enhanced
            })
        
        if signals and signals.nnfx_signal != "HOLD":
            feature_data.update({
                'nnfx_signal': signals.nnfx_signal,
                'signal_confidence': signals.signal_confidence,
                'baseline_signal': signals.baseline_signal,
                'confirmation_strength': signals.confirmation_strength
            })
        
        pipe = self.client.pipeline()
        for feature_name, value in feature_data.items():
            key = f"ml:{symbol}:{feature_name}"
            pipe.setex(key, self.regime_ttl['high_frequency'], json.dumps(value))
        pipe.execute()
        
        logger.debug(f"Stored ML features for {symbol} regime: {regime}")

    def store_strategy_features(self, symbol: str, features: BaseRegimeFeatures, regime: str, signals: NNFXSignals = None):
        """Store features for strategy development (hash-based)"""
        timestamp = datetime.utcnow().isoformat()
        
        strategy_data = {
            'regime': regime,
            'confidence': features.regime_confidence,
            'volatility': features.volatility,
            'trend': features.trend_strength,
            'timestamp': timestamp,
            'regime_model': self.regime_model
        }
        
        if features.regime_confidence_enhanced > 0:
            strategy_data['confidence_enhanced'] = features.regime_confidence_enhanced
            strategy_data['adx'] = features.adx
        
        if signals:
            strategy_data.update({
                'nnfx_signal': signals.nnfx_signal,
                'signal_confidence': signals.signal_confidence
            })
        
        key = f"strategy:{symbol}"
        self.client.hset(key, mapping={k: json.dumps(v) for k, v in strategy_data.items()})
        self.client.expire(key, self.regime_ttl['medium_term'])
    
    def store_regime_history(self, symbol: str, regime: str, confidence: float, signals: NNFXSignals = None):
        """Store regime history for pattern analysis"""
        history_key = f"regime_history:{symbol}"
        regime_event = {
            'regime': regime,
            'confidence': confidence,
            'timestamp': datetime.utcnow().isoformat(),
            'model': self.regime_model
        }
        
        if signals:
            regime_event.update({
                'nnfx_signal': signals.nnfx_signal,
                'signal_confidence': signals.signal_confidence
            })
        
        self.client.lpush(history_key, json.dumps(regime_event))
        self.client.ltrim(history_key, 0, 99)
        self.client.expire(history_key, self.regime_ttl['long_term'])
        
        extended_key = f"regime_history_extended:{symbol}"
        self.client.lpush(extended_key, json.dumps(regime_event))
        self.client.ltrim(extended_key, 0, 999)
        self.client.expire(extended_key, self.regime_ttl['extended_history'])

    # ===== RETRIEVAL METHODS =====
    
    def get_ml_features(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get all ML features for a symbol"""
        feature_names = ['volatility', 'trend_strength', 'volume_profile', 
                        'price_momentum', 'mean_reversion', 'regime_confidence', 'regime']
        
        enhanced_features = ['adx', 'atr', 'rsi', 'kama', 'stoch_k', 'stoch_d', 
                           'regime_confidence_enhanced', 'nnfx_signal', 'signal_confidence']
        
        all_features = feature_names + enhanced_features
        
        pipe = self.client.pipeline()
        for name in all_features:
            pipe.get(f"ml:{symbol}:{name}")
        results = pipe.execute()
        
        features = {}
        for name, result in zip(all_features, results):
            if result:
                features[name] = json.loads(result)
        
        return features if features else None
    
    def get_current_regime(self, symbol: str) -> Optional[str]:
        """Get current regime for a symbol"""
        regime_data = self.client.get(f"ml:{symbol}:regime")
        return json.loads(regime_data) if regime_data else None
    
    def get_regime_history(self, symbol: str, limit: int = 20, extended: bool = False) -> List[Dict]:
        """Get regime history for pattern analysis"""
        history_key = f"regime_history_extended:{symbol}" if extended else f"regime_history:{symbol}"
        raw_history = self.client.lrange(history_key, 0, limit - 1)
        
        history = []
        for item in raw_history:
            try:
                history.append(json.loads(item))
            except json.JSONDecodeError:
                continue
        
        return history
    
    def get_strategy_features(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get strategy features for backtesting"""
        key = f"strategy:{symbol}"
        features = self.client.hgetall(key)
        return {k.decode(): json.loads(v) for k, v in features.items()} if features else None

    # ===== BATCH OPERATIONS =====
    
    def bulk_store_regimes(self, regime_data: Dict[str, Tuple[BaseRegimeFeatures, str, NNFXSignals]]):
        """Bulk store regime data for multiple symbols"""
        pipe = self.client.pipeline()
        
        for symbol, (features, regime, signals) in regime_data.items():
            feature_dict = {
                'volatility': features.volatility,
                'trend_strength': features.trend_strength,
                'volume_profile': features.volume_profile,
                'price_momentum': features.price_momentum,
                'mean_reversion': features.mean_reversion,
                'regime_confidence': features.regime_confidence,
                'regime': regime,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            if features.regime_confidence_enhanced > 0:
                feature_dict.update({
                    'adx': features.adx,
                    'atr': features.atr,
                    'rsi': features.rsi,
                    'regime_confidence_enhanced': features.regime_confidence_enhanced
                })
            
            if signals:
                feature_dict.update({
                    'nnfx_signal': signals.nnfx_signal,
                    'signal_confidence': signals.signal_confidence
                })
            
            for feature_name, value in feature_dict.items():
                key = f"ml:{symbol}:{feature_name}"
                pipe.setex(key, self.regime_ttl['high_frequency'], json.dumps(value))
            
            history_key = f"regime_history:{symbol}"
            regime_event = {
                'regime': regime,
                'confidence': features.regime_confidence,
                'timestamp': datetime.utcnow().isoformat(),
                'model': self.regime_model
            }
            if signals:
                regime_event.update({
                    'nnfx_signal': signals.nnfx_signal,
                    'signal_confidence': signals.signal_confidence
                })
                
            pipe.lpush(history_key, json.dumps(regime_event))
            pipe.ltrim(history_key, 0, 99)
        
        pipe.execute()
    
    def get_bulk_regimes(self, symbols: List[str]) -> Dict[str, Optional[str]]:
        """Get current regimes for multiple symbols"""
        pipe = self.client.pipeline()
        
        for symbol in symbols:
            pipe.get(f"ml:{symbol}:regime")
        
        results = pipe.execute()
        regimes = {}
        
        for symbol, result in zip(symbols, results):
            regimes[symbol] = json.loads(result) if result else None
        
        return regimes

    # ===== ML TRAINING DATA METHODS =====
    
    def store_ml_training_features(self, symbol: str, features: BaseRegimeFeatures, 
                                signals: NNFXSignals, ohlcv_data: Dict, timestamp: datetime):
        """Store features persistently for ML training (no TTL)"""
        feature_package = {
            'symbol': symbol,
            'timestamp': timestamp.isoformat(),
            # ... rest of dictionary
        }
        
        key = f"ml_training:{symbol}:{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        # Convert datetime objects to ISO format strings
        def json_serial(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
        
        self.client.set(key, json.dumps(feature_package, default=json_serial))
        
        recent_key = f"ml_recent:{symbol}"
        self.client.lpush(recent_key, json.dumps(feature_package, default=json_serial))  # FIX HERE
        self.client.ltrim(recent_key, 0, 999)
        self.client.expire(recent_key, self.regime_ttl['long_term'])

    def export_ml_features_to_csv(self, symbol: str, days: int = 30) -> str:
        """Export features to CSV for ML training"""
        pattern = f"ml_training:{symbol}:*"
        keys = self.client.keys(pattern)
        
        if not keys:
            return f"No training data found for {symbol}"
        
        features_list = []
        for key in keys:
            data = self.client.get(key)
            if data:
                features_list.append(json.loads(data))
        
        if not features_list:
            return f"No features extracted for {symbol}"
        
        flattened_data = []
        for item in features_list:
            flat_item = {
                'timestamp': item['timestamp'],
                'symbol': item['symbol'],
                'regime': item['regime'],
                'regime_model': item['regime_model'],
                **item['basic_features'],
                **item['technical_features'],
                **item['signals']
            }
            flat_item.update({
                f"ohlcv_{k}": v for k, v in item['ohlcv'].items()
            })
            flattened_data.append(flat_item)
        
        df = pd.DataFrame(flattened_data)
        
        filename = f"ml_features_{symbol}_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False)
        
        return f"Exported {len(df)} records to {filename}"
    
    def get_training_data_stats(self) -> Dict[str, Any]:
        """Get statistics about ML training data"""
        pattern = "ml_training:*"
        keys = self.client.keys(pattern)
        
        symbols = {}
        models = {}
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            parts = key_str.split(':')
            if len(parts) >= 2:
                symbol = parts[1]
                symbols[symbol] = symbols.get(symbol, 0) + 1
                
                data = self.client.get(key)
                if data:
                    try:
                        parsed = json.loads(data)
                        model = parsed.get('regime_model', 'unknown')
                        models[model] = models.get(model, 0) + 1
                    except:
                        pass
        
        return {
            'total_records': len(keys),
            'records_per_symbol': symbols,
            'records_per_model': models,
            'total_symbols': len(symbols)
        }

    # ===== ADAPTIVE STRATEGY ENGINE =====
    
    def _initialize_allocation_rules(self):
        """Define how to allocate based on detected regimes"""
        return {
            'trending_high_vol': {
                'strategies': {'nnfx': 0.7, 'breakout': 0.3, 'mean_reversion': 0.0},
                'risk_multiplier': 1.0,
                'symbol_bias': {'TrendX': 0.4, 'GainX': 0.3, 'BreakX': 0.3}
            },
            'trending_low_vol': {
                'strategies': {'nnfx': 0.8, 'breakout': 0.2, 'mean_reversion': 0.0},
                'risk_multiplier': 0.8,
                'symbol_bias': {'TrendX': 0.6, 'FlipX': 0.4}
            },
            'ranging_high_vol': {
                'strategies': {'mean_reversion': 0.6, 'breakout': 0.4, 'nnfx': 0.0},
                'risk_multiplier': 0.6,
                'symbol_bias': {'GainX': 0.5, 'PainX': 0.3, 'SwitchX': 0.2}
            },
            'ranging_low_vol': {
                'strategies': {'mean_reversion': 0.9, 'breakout': 0.1, 'nnfx': 0.0},
                'risk_multiplier': 0.4,
                'symbol_bias': {'FlipX': 0.6, 'SwitchX': 0.4}
            }
        }
    
    def get_tactical_allocation(self, symbols: List[str]) -> TacticalAllocation:
        """Get current tactical allocation based on regime"""
        regimes = self.get_bulk_regimes(symbols)
        
        regime_counts = {}
        for symbol, regime in regimes.items():
            if regime:
                regime_counts[regime] = regime_counts.get(regime, 0) + 1
        
        dominant_regime = max(regime_counts, key=regime_counts.get) if regime_counts else 'ranging_low_vol'
        rules = self._initialize_allocation_rules().get(dominant_regime, self._initialize_allocation_rules()['ranging_low_vol'])
        
        symbol_weights = {}
        for symbol in symbols:
            symbol_regime = regimes.get(symbol, 'ranging_low_vol')
            base_weight = rules['symbol_bias'].get(symbol, 0.1)
            
            if symbol_regime == dominant_regime:
                symbol_weights[symbol] = base_weight * 1.5
            else:
                symbol_weights[symbol] = base_weight * 0.5
        
        total = sum(symbol_weights.values())
        symbol_weights = {k: v/total for k, v in symbol_weights.items()}
        
        return TacticalAllocation(
            regime=dominant_regime,
            symbol_weights=symbol_weights,
            strategy_weights=rules['strategies'],
            risk_multiplier=rules['risk_multiplier'],
            confidence=len(regime_counts) / len(symbols) if symbols else 0.0
        )

    # ===== ANALYTICS METHODS =====
    
    def get_regime_statistics(self, symbol: str, extended: bool = False) -> Dict[str, Any]:
        """Get statistics about regime patterns"""
        history = self.get_regime_history(symbol, limit=100, extended=extended)
        
        if not history:
            return {}
        
        regimes = [event['regime'] for event in history]
        confidences = [event.get('confidence', 0) for event in history]
        models = [event.get('model', 'unknown') for event in history]
        
        regime_counts = {}
        model_counts = {}
        
        for regime, model in zip(regimes, models):
            regime_counts[regime] = regime_counts.get(regime, 0) + 1
            model_counts[model] = model_counts.get(model, 0) + 1
        
        total_periods = len(regimes)
        regime_percentages = {regime: count/total_periods for regime, count in regime_counts.items()}
        model_percentages = {model: count/total_periods for model, count in model_counts.items()}
        
        signals = [event.get('nnfx_signal', 'HOLD') for event in history if 'nnfx_signal' in event]
        signal_counts = {}
        for signal in signals:
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
        
        return {
            'total_periods': total_periods,
            'regime_distribution': regime_percentages,
            'model_distribution': model_percentages,
            'signal_distribution': signal_counts,
            'avg_confidence': np.mean(confidences) if confidences else 0,
            'current_regime': regimes[0] if regimes else None,
            'regime_stability': self._calculate_regime_stability(regimes),
            'primary_model': max(model_counts, key=model_counts.get) if model_counts else 'unknown'
        }
    
    def _calculate_regime_stability(self, regimes: List[str]) -> float:
        """Calculate how stable regimes have been"""
        if len(regimes) <= 1:
            return 1.0
        
        changes = 0
        for i in range(1, len(regimes)):
            if regimes[i] != regimes[i-1]:
                changes += 1
        
        stability = 1.0 - (changes / (len(regimes) - 1))
        return stability

    # ===== SYMBOL-SPECIFIC METHODS =====
    
    def get_symbol_regime_profile(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive regime profile for a symbol"""
        current_regime = self.get_current_regime(symbol)
        stats = self.get_regime_statistics(symbol, extended=True)
        ml_features = self.get_ml_features(symbol)
        strategy_features = self.get_strategy_features(symbol)
        training_stats = self.get_training_data_stats()
        
        symbol_type = "unknown"
        for pattern_type, patterns in self.symbol_patterns.items():
            if any(pattern in symbol for pattern in patterns):
                symbol_type = pattern_type
                break
        
        return {
            'symbol': symbol,
            'symbol_type': symbol_type,
            'current_regime': current_regime,
            'statistics': stats,
            'ml_features_available': ml_features is not None,
            'strategy_features_available': strategy_features is not None,
            'training_records': training_stats['records_per_symbol'].get(symbol, 0),
            'regime_model': self.regime_model,
            'timestamp': datetime.utcnow().isoformat()
        }

# Example usage and testing
if __name__ == "__main__":
    redis_config = {
        'host': 'localhost',
        'port': 6379,
        'db': 0
    }
    
    # Test with different regime models
    for model in ['basic', 'technical', 'nnfx', 'comprehensive']:
        print(f"\n🧪 Testing {model} regime model:")
        print("=" * 50)
        
        store = UnifiedRegimeFeatureStore(redis_config, regime_model=model)
        
        # Sample OHLCV data
        sample_data = {
            'open': 100.0,
            'high': 102.0,
            'low': 98.0,
            'close': 101.5,
            'volume': 1500
        }
        
        # Sample historical data
        dates = pd.date_range(end=datetime.now(), periods=50, freq='H')
        historical_data = pd.DataFrame({
            'open': 100 + np.random.randn(50).cumsum(),
            'high': 102 + np.random.randn(50).cumsum(),
            'low': 98 + np.random.randn(50).cumsum(), 
            'close': 101 + np.random.randn(50).cumsum(),
            'volume': np.random.randint(800, 2000, 50)
        }, index=dates)
        
        # Compute features
        features, signals = store.compute_unified_regime_features("GainX 600", sample_data, historical_data)
        
        print(f"📊 Regime: {features.regime_type}")
        print(f"📈 Confidence: {features.regime_confidence:.3f}")
        print(f"🎯 Enhanced Confidence: {features.regime_confidence_enhanced:.3f}")
        
        if signals.nnfx_signal != "HOLD":
            print(f"💰 NNFX Signal: {signals.nnfx_signal} (Confidence: {signals.signal_confidence:.3f})")
        
        # Store features
        store.store_ml_features("GainX 600", features, features.regime_type, signals)
        store.store_strategy_features("GainX 600", features, features.regime_type, signals)
        store.store_regime_history("GainX 600", features.regime_type, features.regime_confidence, signals)
        store.store_ml_training_features("GainX 600", features, signals, sample_data, datetime.now())
        
        # Verify retrieval
        retrieved = store.get_ml_features("GainX 600")
        print(f"✅ Features stored and retrieved: {retrieved is not None}")
        
        stats = store.get_regime_statistics("GainX 600")
        print(f"📈 Regime statistics: {stats.get('regime_distribution', {})}")
        
        profile = store.get_symbol_regime_profile("GainX 600")
        print(f"🔍 Symbol profile type: {profile['symbol_type']}")