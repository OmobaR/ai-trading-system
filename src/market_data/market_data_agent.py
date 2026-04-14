import pandas as pd
from datetime import datetime, timedelta
import time
import random
import logging
import asyncio
import os

# MT5 Simulation for Docker compatibility
class MT5Simulator:
    """Simulates MT5 functionality for Docker development"""
    
    TIMEFRAME_M5 = "M5"
    TIMEFRAME_M15 = "M15" 
    TIMEFRAME_H1 = "H1"
    TIMEFRAME_H4 = "H4"
    TIMEFRAME_D1 = "D1"
    TIMEFRAME_W1 = "W1"
    TIMEFRAME_MN1 = "MN1"
    
    @staticmethod
    def initialize():
        logger.info(" MT5 Simulator Active - Using synthetic market data")
        return True
        
    @staticmethod  
    def login(login, password, server):
        logger.info(f" MT5 Simulator - Authenticated: {login}@{server}")
        return True
        
    @staticmethod
    def shutdown():
        logger.info(" MT5 Simulator - Shutdown complete")
        return True
        
    @staticmethod
    def symbol_select(symbol, enable):
        logger.debug(f" MT5 Simulator - Symbol {symbol} {'enabled' if enable else 'disabled'}")
        return enable
        
    @staticmethod  
    def symbol_info_tick(symbol):
        # Generate realistic synthetic tick data
        base_price = 100.0 + hash(symbol) % 50
        spread = 0.0001 * (1 + hash(symbol) % 10)
        
        return type('MockTick', (), {
            'bid': base_price + random.uniform(-0.5, 0.5),
            'ask': base_price + spread + random.uniform(-0.5, 0.5),
            'last': base_price + random.uniform(-0.5, 0.5),
            'volume': random.randint(1000, 5000),
            'time': datetime.now().timestamp()
        })()
    
    @staticmethod
    def copy_rates_range(symbol, timeframe, start_date, end_date):
        # Generate synthetic historical data
        periods = int((end_date - start_date).total_seconds() / (5 * 60))  # M5 data
        if periods <= 0:
            periods = 1000
            
        base_price = 100.0 + hash(symbol) % 50
        data = []
        
        for i in range(periods):
            timestamp = start_date.timestamp() + (i * 5 * 60)
            open_price = base_price + random.uniform(-2, 2)
            high = open_price + random.uniform(0, 1)
            low = open_price - random.uniform(0, 1) 
            close = open_price + random.uniform(-0.5, 0.5)
            volume = random.randint(800, 2000)
            
            data.append([timestamp, open_price, high, low, close, volume])
            
        return data

# Use MT5 simulator in Docker, real MT5 on Windows
if os.environ.get('DOCKER_CONTAINER'):
    mt5 = MT5Simulator
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)
else:
    import MetaTrader5 as mt5
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from events.event_store import EventStore
from database.redis_feature_store import UnifiedRegimeFeatureStore, BaseRegimeFeatures, NNFXSignals

class MarketDataAgent:
    def __init__(self, db_config, redis_config, mt5_config=None, mode='simulate', regime_model='comprehensive'):
        self.event_store = EventStore(db_config)
        self.feature_store = UnifiedRegimeFeatureStore(redis_config, regime_model=regime_model)
        self.running = False
        self.mode = mode
        self.regime_model = regime_model
        self.mt5_config = mt5_config or {
            'login': 19345714,
            'password': 'bL$3Vs5)',
            'server': 'Weltrade-Demo'
        }
        
        # Enhanced symbol list with regime-aware grouping
        self.symbols = [
            "GainX 400", "GainX 600", "GainX 800", "GainX 999", "GainX 1200",
            "PainX 400", "PainX 600", "PainX 800", "PainX 999", "PainX 1200",
            "FlipX 1", "FlipX 2", "FlipX 3", "FlipX 4", "FlipX 5",
            "FX Vol 20", "FX Vol 40", "FX Vol 60", "FX Vol 80", "FX Vol 99",
            "SFX Vol 20", "SFX Vol 40", "SFX Vol 60", "SFX Vol 80", "SFX Vol 99",
            "TrendX 600", "TrendX 1200", "TrendX 1800",
            "SwitchX 600", "SwitchX 1200", "SwitchX 1800",
            "BreakX 600", "BreakX 1200", "BreakX 1800"
        ]
        
        self.timeframes = {
            "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1
        }
        
        # Regime tracking
        self.current_regimes = {}
        self.regime_history = {}
        
        if self.mode in ['historical', 'live']:
            self._init_mt5()

    def _init_mt5(self):
        """Initialize MT5 connection or simulator"""
        if not mt5.initialize():
            logger.warning("MT5 initialization failed, switching to simulate mode")
            self.mode = 'simulate'
            return
            
        if not mt5.login(self.mt5_config['login'], self.mt5_config['password'], self.mt5_config['server']):
            mt5.shutdown()
            logger.warning("MT5 login failed, switching to simulate mode")
            self.mode = 'simulate'
            return
            
        logger.info(" Market data source initialized successfully")

    # ... REST OF YOUR EXISTING MarketDataAgent CODE ...
    # (Keep all your existing methods: _get_start_date, _enable_symbol, _fetch_historical,
    # validate_data, normalize_data, ingest_data, run_historical, run_live, run_simulate, etc.)
    
    def _get_start_date(self, timeframe):
        """Calculate start date for historical data based on timeframe"""
        now = datetime.now()
        if timeframe == mt5.TIMEFRAME_M5:
            return now - timedelta(days=30)
        elif timeframe == mt5.TIMEFRAME_H1:
            return now - timedelta(days=90)
        elif timeframe == mt5.TIMEFRAME_D1:
            return now - timedelta(days=365)
        else:
            return now - timedelta(days=30)

    def _enable_symbol(self, symbol):
        """Enable a symbol in MT5"""
        if not mt5.symbol_select(symbol, True):
            logger.warning(f"Could not enable symbol {symbol}")
            return False
        return True

    def _fetch_historical(self, symbol, timeframe, start_date, end_date):
        """Fetch historical data from MT5 with chunking"""
        rates = mt5.copy_rates_range(symbol, timeframe, start_date, end_date)
        if rates is None:
            logger.warning(f"Failed to fetch data for {symbol}, trying fallback...")
            rates = mt5.copy_rates_from(symbol, timeframe, start_date, 1000)
        return rates

    def validate_data(self, data):
        """Validate OHLCV data"""
        required = ['time', 'symbol', 'open', 'high', 'low', 'close']
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        if data['high'] < data['low']:
            raise ValueError("High price cannot be less than low price")
        
        if data['open'] <= 0 or data['close'] <= 0:
            raise ValueError("Prices must be positive")

    def normalize_data(self, data):
        """Normalize data for storage"""
        normalized = data.copy()
        
        # Convert timestamp to datetime if needed
        if isinstance(normalized['time'], (int, float)):
            normalized['time'] = datetime.fromtimestamp(normalized['time'])
        
        # Ensure volume is integer
        if 'volume' in normalized:
            normalized['volume'] = int(normalized['volume'])
        
        return normalized

    def ingest_data(self, data):
        """Enhanced ingestion with unified regime detection"""
        try:
            self.validate_data(data)
            normalized = self.normalize_data(data)
            
            # Store in TimescaleDB
            with self.event_store.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ohlcv_data (time, symbol, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (time, symbol) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume;
                """, (normalized['time'], normalized['symbol'], normalized.get('open', 0),
                      normalized.get('high', 0), normalized.get('low', 0),
                      normalized.get('close', 0), normalized.get('volume', 0)))
            self.event_store.conn.commit()
            
            # Get historical data for enhanced feature computation
            historical_data = self._get_recent_historical_data(normalized['symbol'])
            
            # Compute unified regime features
            regime_features, nnfx_signals = self.feature_store.compute_unified_regime_features(
                normalized['symbol'], 
                normalized,
                historical_data
            )
            
            # Store in Redis using unified approach
            self.feature_store.store_ml_features(
                normalized['symbol'], 
                regime_features, 
                regime_features.regime_type, 
                nnfx_signals
            )
            self.feature_store.store_strategy_features(
                normalized['symbol'], 
                regime_features, 
                regime_features.regime_type, 
                nnfx_signals
            )
            self.feature_store.store_regime_history(
                normalized['symbol'], 
                regime_features.regime_type, 
                regime_features.regime_confidence, 
                nnfx_signals
            )
            
            # Store for ML training
            self.feature_store.store_ml_training_features(
                normalized['symbol'], 
                regime_features, 
                nnfx_signals, 
                normalized, 
                datetime.now()
            )
            
            # Update local regime tracking
            self.current_regimes[normalized['symbol']] = {
                'regime': regime_features.regime_type,
                'confidence': regime_features.regime_confidence,
                'enhanced_confidence': regime_features.regime_confidence_enhanced,
                'nnfx_signal': nnfx_signals.nnfx_signal,
                'timestamp': normalized['time']
            }
            
            # Enhanced audit event with comprehensive regime info
            self.event_store.append_event(
                'data_ingested_with_regime',
                normalized['symbol'],
                {
                    'open': normalized.get('open'),
                    'close': normalized.get('close'),
                    'regime': regime_features.regime_type,
                    'confidence': regime_features.regime_confidence,
                    'enhanced_confidence': regime_features.regime_confidence_enhanced,
                    'volatility': regime_features.volatility,
                    'trend_strength': regime_features.trend_strength,
                    'nnfx_signal': nnfx_signals.nnfx_signal,
                    'signal_confidence': nnfx_signals.signal_confidence
                },
                metadata={
                    'source': self.mode,
                    'regime_model': self.regime_model,
                    'regime_features': {
                        'volatility': regime_features.volatility,
                        'trend_strength': regime_features.trend_strength,
                        'volume_profile': regime_features.volume_profile,
                        'adx': regime_features.adx,
                        'atr': regime_features.atr,
                        'rsi': regime_features.rsi
                    }
                }
            )
            
            logger.info(f" Ingested {normalized['symbol']} | Regime: {regime_features.regime_type} | "
                       f"Confidence: {regime_features.regime_confidence:.3f} | "
                       f"NNFX: {nnfx_signals.nnfx_signal}")
            
        except Exception as e:
            logger.error(f"Error ingesting data: {e}")
            raise

    def _get_recent_historical_data(self, symbol, periods=50):
        """Get recent historical data for enhanced feature computation"""
        try:
            # This would typically fetch from TimescaleDB
            # For now, return empty DataFrame
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"Could not fetch historical data for {symbol}: {e}")
            return pd.DataFrame()

    def get_current_regimes(self):
        """Get current regimes for all symbols"""
        return self.feature_store.get_bulk_regimes(self.symbols)

    def get_regime_analytics(self, symbol):
        """Get regime analytics for a symbol"""
        return self.feature_store.get_regime_statistics(symbol)

    def get_tactical_allocation(self):
        """Get tactical allocation based on current regimes"""
        allocation = self.feature_store.get_tactical_allocation(self.symbols)
        return {
            'regime': allocation.regime,
            'symbol_weights': allocation.symbol_weights,
            'strategy_weights': allocation.strategy_weights,
            'risk_multiplier': allocation.risk_multiplier,
            'confidence': allocation.confidence,
            'timestamp': datetime.utcnow().isoformat()
        }

    def print_regime_dashboard(self):
        """Print a comprehensive regime dashboard"""
        regimes = self.get_current_regimes()
        allocation = self.get_tactical_allocation()
        
        print("\n" + "="*80)
        print(" COMPREHENSIVE MARKET REGIME DASHBOARD")
        print("="*80)
        
        regime_counts = {}
        for symbol, regime in regimes.items():
            if regime:
                regime_counts[regime] = regime_counts.get(regime, 0) + 1
        
        print("\n REGIME DISTRIBUTION:")
        print("-" * 40)
        for regime, count in regime_counts.items():
            percentage = (count / len(self.symbols)) * 100
            print(f"  {regime:<25} {count:>2} symbols ({percentage:>5.1f}%)")
        
        print("\n TACTICAL ALLOCATION:")
        print("-" * 40)
        print(f"  Dominant Regime: {allocation['regime']}")
        print(f"  Risk Multiplier: {allocation['risk_multiplier']:.2f}")
        print(f"  Allocation Confidence: {allocation['confidence']:.1%}")
        
        print(f"\n  Strategy Weights:")
        for strategy, weight in allocation['strategy_weights'].items():
            print(f"    {strategy:<15} {weight:>5.1%}")
        
        print("\n SYMBOL DETAILS (Sample):")
        print("-" * 40)
        sample_symbols = self.symbols[:5]
        for symbol in sample_symbols:
            regime = regimes.get(symbol, "Unknown")
            stats = self.get_regime_analytics(symbol)
            stability = stats.get('regime_stability', 0) * 100 if stats else 0
            weight = allocation['symbol_weights'].get(symbol, 0)
            print(f"  {symbol:<15} | {regime:<20} | Stability: {stability:>5.1f}% | Weight: {weight:>5.1%}")
        
        print("\n  CONFIGURATION:")
        print("-" * 40)
        print(f"  Regime Model: {self.regime_model}")
        print(f"  Mode: {self.mode}")
        print(f"  Total Symbols: {len(self.symbols)}")
        print("="*80)

    async def _check_regime_change(self, symbol, new_regime):
        """Check if regime has changed significantly"""
        history = self.feature_store.get_regime_history(symbol, limit=10)
        if len(history) >= 5:
            recent_regimes = [h['regime'] for h in history[:5]]
            regime_stability = len(set(recent_regimes)) / len(recent_regimes)
            
            if regime_stability < 0.6:
                logger.warning(f"Regime instability detected for {symbol}: {recent_regimes}")

    def run_historical(self, days=30, timeframe="H1"):
        """Run historical data ingestion"""
        logger.info(f"Starting historical data ingestion for {days} days")
        start_date = datetime.now() - timedelta(days=days)
        
        for symbol in self.symbols:
            if not self._enable_symbol(symbol):
                continue
                
            try:
                rates = self._fetch_historical(
                    symbol, 
                    self.timeframes[timeframe], 
                    start_date, 
                    datetime.now()
                )
                
                if rates is not None:
                    for rate in rates:
                        data = {
                            'time': datetime.fromtimestamp(rate[0]),
                            'symbol': symbol,
                            'open': rate[1],
                            'high': rate[2],
                            'low': rate[3],
                            'close': rate[4],
                            'volume': rate[5] if len(rate) > 5 else 1000
                        }
                        self.ingest_data(data)
                
                logger.info(f"Historical data completed for {symbol}")
                
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
            
            time.sleep(0.1)  # Rate limiting

    def run_live(self):
        """Run live data ingestion"""
        logger.info("Starting live data ingestion")
        
        while self.running:
            for symbol in self.symbols:
                try:
                    tick = mt5.symbol_info_tick(symbol)
                    if tick is None:
                        continue
                    
                    data = {
                        'time': datetime.now(),
                        'symbol': symbol,
                        'open': tick.bid,
                        'high': tick.bid,
                        'low': tick.bid,
                        'close': tick.bid,
                        'volume': 1000
                    }
                    
                    self.ingest_data(data)
                    
                except Exception as e:
                    logger.error(f"Error processing live data for {symbol}: {e}")
            
            time.sleep(60)  # Poll every 60 seconds

    def run_simulate(self):
        logger.info("Starting simulation data generation")
        import traceback
        base_prices = {symbol: 100.0 + i * 10 for i, symbol in enumerate(self.symbols)}
        
        iteration = 0
        while self.running:
            iteration += 1
            logger.debug(f"Simulation loop iteration {iteration}")
            for symbol in self.symbols:
                try:
                    base = base_prices[symbol]
                    change = random.uniform(-2.0, 2.0)
                    new_price = base + change
                    
                    data = {
                        'time': datetime.now(),
                        'symbol': symbol,
                        'open': base,
                        'high': max(base, new_price) + random.uniform(0, 1.0),
                        'low': min(base, new_price) - random.uniform(0, 1.0),
                        'close': new_price,
                        'volume': random.randint(800, 2000)
                    }
                    
                    logger.debug(f"Generated data for {symbol}: {data['close']}")
                    self.ingest_data(data)
                    base_prices[symbol] = new_price
                    
                except Exception as e:
                    logger.error(f"Error in simulation loop for {symbol}: {e}")
                    logger.error(traceback.format_exc())
            
            logger.debug(f"Sleeping for 5 seconds")
            time.sleep(5)
        logger.info("Simulation loop ended")

    def run(self):
        logger.info(f"run() called, mode={self.mode}")
        self.running = True
        logger.debug(f"self.running set to {self.running}")
        if self.mode == 'historical':
            self.run_historical()
        elif self.mode == 'live':
            self.run_live()
        elif self.mode == 'simulate':
            self.run_simulate()
        logger.info(f"run() finished, self.running={self.running}")

    def run_simulate(self):
        logger.info("Starting simulation data generation")
        logger.debug(f"run_simulate: self.running = {self.running}")
        
        # Force running to True for this run (temporary fix)
        if not self.running:
            logger.warning("run_simulate: self.running was False, setting to True")
            self.running = True
        
        base_prices = {symbol: 100.0 + i * 10 for i, symbol in enumerate(self.symbols)}
        iteration = 0
        
        logger.debug("Entering main loop")
        while self.running:
            iteration += 1
            logger.debug(f"Loop iteration {iteration} start")
            
            for symbol in self.symbols:
                try:
                    base = base_prices[symbol]
                    change = random.uniform(-2.0, 2.0)
                    new_price = base + change
                    
                    data = {
                        'time': datetime.now(),
                        'symbol': symbol,
                        'open': base,
                        'high': max(base, new_price) + random.uniform(0, 1.0),
                        'low': min(base, new_price) - random.uniform(0, 1.0),
                        'close': new_price,
                        'volume': random.randint(800, 2000)
                    }
                    
                    logger.debug(f"Generated data for {symbol}: close={data['close']:.4f}")
                    
                    # Call ingest_data and log result
                    self.ingest_data(data)
                    logger.debug(f"Ingested {symbol}")
                    
                    base_prices[symbol] = new_price
                    
                except Exception as e:
                    import traceback
                    logger.error(f"Error in simulation loop for {symbol}: {e}")
                    logger.error(traceback.format_exc())
            
            logger.debug(f"Sleeping for 5 seconds (iteration {iteration})")
            time.sleep(5)
        
        logger.info("Simulation loop ended")

    def stop(self):
        """Stop the agent"""
        self.running = False
        if self.mode in ['historical', 'live']:
            mt5.shutdown()
        logger.info("Market Data Agent stopped")



