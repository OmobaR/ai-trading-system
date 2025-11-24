# src/market_data/market_data_agent.py
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import time
import random
import logging
import asyncio
from src.events.event_store import EventStore
from src.database.redis_feature_store import UnifiedRegimeFeatureStore, BaseRegimeFeatures, NNFXSignals

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        """Initialize MT5 connection"""
        if not mt5.initialize():
            raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
        if not mt5.login(self.mt5_config['login'], self.mt5_config['password'], self.mt5_config['server']):
            mt5.shutdown()
            raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")
        logger.info("✅ MT5 connected successfully")

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
            
            logger.info(f"📊 Ingested {normalized['symbol']} | Regime: {regime_features.regime_type} | "
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

    def get_current_regimes(self) -> Dict[str, str]:
        """Get current regimes for all symbols"""
        return self.feature_store.get_bulk_regimes(self.symbols)

    def get_regime_analytics(self, symbol: str) -> Dict[str, Any]:
        """Get regime analytics for a symbol"""
        return self.feature_store.get_regime_statistics(symbol)

    def get_tactical_allocation(self) -> Dict[str, Any]:
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
        print("🎯 COMPREHENSIVE MARKET REGIME DASHBOARD")
        print("="*80)
        
        regime_counts = {}
        for symbol, regime in regimes.items():
            if regime:
                regime_counts[regime] = regime_counts.get(regime, 0) + 1
        
        print("\n📈 REGIME DISTRIBUTION:")
        print("-" * 40)
        for regime, count in regime_counts.items():
            percentage = (count / len(self.symbols)) * 100
            print(f"  {regime:<25} {count:>2} symbols ({percentage:>5.1f}%)")
        
        print("\n💰 TACTICAL ALLOCATION:")
        print("-" * 40)
        print(f"  Dominant Regime: {allocation['regime']}")
        print(f"  Risk Multiplier: {allocation['risk_multiplier']:.2f}")
        print(f"  Allocation Confidence: {allocation['confidence']:.1%}")
        
        print(f"\n  Strategy Weights:")
        for strategy, weight in allocation['strategy_weights'].items():
            print(f"    {strategy:<15} {weight:>5.1%}")
        
        print("\n🔍 SYMBOL DETAILS (Sample):")
        print("-" * 40)
        sample_symbols = self.symbols[:5]
        for symbol in sample_symbols:
            regime = regimes.get(symbol, "Unknown")
            stats = self.get_regime_analytics(symbol)
            stability = stats.get('regime_stability', 0) * 100 if stats else 0
            weight = allocation['symbol_weights'].get(symbol, 0)
            print(f"  {symbol:<15} | {regime:<20} | Stability: {stability:>5.1f}% | Weight: {weight:>5.1%}")
        
        print("\n⚙️  CONFIGURATION:")
        print("-" * 40)
        print(f"  Regime Model: {self.regime_model}")
        print(f"  Mode: {self.mode}")
        print(f"  Total Symbols: {len(self.symbols)}")
        print("="*80)

    async def _check_regime_change(self, symbol: str, new_regime: str):
        """Check if regime has changed significantly"""
        history = self.feature_store.get_regime_history(symbol, limit=10)
        if len(history) >= 5:
            recent_regimes = [h['regime'] for h in history[:5]]
            regime_stability = len(set(recent_regimes)) / len(recent_regimes)
            
            if regime_stability < 0.6:
                logger.warning(f"Regime instability detected for {symbol}: {recent_regimes}")
                # In a full implementation, this would trigger strategy reallocation

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
        """Run simulation data generation"""
        logger.info("Starting simulation data generation")
        
        base_prices = {symbol: 100.0 + i * 10 for i, symbol in enumerate(self.symbols)}
        
        while self.running:
            for symbol in self.symbols:
                try:
                    # Generate realistic price movement with some trends
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
                    
                    self.ingest_data(data)
                    base_prices[symbol] = new_price
                    
                except Exception as e:
                    logger.error(f"Error generating simulation data for {symbol}: {e}")
            
            time.sleep(5)  # Generate data every 5 seconds

    def run(self):
        """Main run method"""
        self.running = True
        
        if self.mode == 'historical':
            self.run_historical()
        elif self.mode == 'live':
            self.run_live()
        elif self.mode == 'simulate':
            self.run_simulate()

    def stop(self):
        """Stop the agent"""
        self.running = False
        if self.mode in ['historical', 'live']:
            mt5.shutdown()
        logger.info("Market Data Agent stopped")

# Updated main execution with enhanced regime dashboard
if __name__ == "__main__":
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'ai_trading_db',
        'user': 'postgres',
        'password': 'password'
    }
    redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
    
    # Test different regime models
    for regime_model in ['basic', 'technical', 'nnfx', 'comprehensive']:
        print(f"\n🚀 Testing Market Data Agent with {regime_model} regime model...")
        
        agent = MarketDataAgent(
            db_config, 
            redis_config, 
            mode='simulate', 
            regime_model=regime_model
        )
        
        try:
            agent.running = True
            
            # Run for a short time to generate data
            import threading
            def run_agent():
                agent.run_simulate()
            
            thread = threading.Thread(target=run_agent)
            thread.daemon = True
            thread.start()
            
            time.sleep(10)  # Let it run for 10 seconds
            agent.stop()
            thread.join(timeout=5)
            
            # Show regime dashboard
            agent.print_regime_dashboard()
            
        except KeyboardInterrupt:
            print("\n🛑 Stopping agent...")
            agent.stop()
        except Exception as e:
            print(f"❌ Error: {e}")
            agent.stop()