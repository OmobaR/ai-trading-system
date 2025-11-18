# src/market_data/market_data_agent.py
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import time
import random  # For simulation fallback
import logging
from src.events.event_store import EventStore
from src.database.redis_feature_store import FeatureStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MarketDataAgent:
    def __init__(self, db_config, redis_config, mt5_config=None, mode='simulate'):
        self.event_store = EventStore(db_config)
        self.feature_store = FeatureStore(redis_config)
        self.running = False
        self.mode = mode  # 'simulate', 'historical', 'live'
        self.mt5_config = mt5_config or {
            'login': 19345714,
            'password': 'bL$3Vs5)',
            'server': 'Weltrade-Demo'
        }
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
        if self.mode in ['historical', 'live']:
            self._init_mt5()

    def _init_mt5(self):
        if not mt5.initialize():
            raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
        if not mt5.login(self.mt5_config['login'], self.mt5_config['password'], self.mt5_config['server']):
            mt5.shutdown()
            raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")
        logger.info("MT5 connected successfully")

    def _get_start_date(self, symbol):
        if any(x in symbol for x in ["TrendX", "BreakX", "SFX Vol"]):
            return datetime(2025, 6, 16)
        return datetime(2024, 1, 1)

    def _enable_symbol(self, symbol):
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            raise ValueError(f"{symbol} not found")
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                raise ValueError(f"Failed to select {symbol}")
        time.sleep(1)  # Delay for stability

    def _fetch_historical(self, symbol, tf_value, start_date, end_date):
        rates = mt5.copy_rates_range(symbol, tf_value, start_date, end_date)
        if rates is None or len(rates) == 0:
            logger.warning("copy_rates_range failed, falling back to chunked copy_rates_from")
            rates = []
            current_start = start_date
            while current_start < end_date:
                current_end = min(current_start + timedelta(days=30), end_date)
                chunk = mt5.copy_rates_from(symbol, tf_value, current_end, 10000)
                if chunk is not None:
                    rates.extend(chunk)
                current_start = current_end + timedelta(days=1)
                time.sleep(0.1)
        if rates is None or len(rates) == 0:
            logger.warning("All methods failed, fetching recent 1000 bars")
            rates = mt5.copy_rates_from(symbol, tf_value, datetime.now(), 1000)
        return rates

    def validate_data(self, data):
        required_fields = ['time', 'symbol', 'open', 'high', 'low', 'close']  # Updated for OHLCV
        if not all(field in data for field in required_fields):
            raise ValueError("Missing required fields in data")
        return True

    def normalize_data(self, data):
        data['time'] = pd.to_datetime(data['time'], unit='s') if 'time' in data else datetime.utcnow()
        return data

    def ingest_data(self, data):
        try:
            self.validate_data(data)
            normalized = self.normalize_data(data)
            # Store in TimescaleDB (OHLCV for bars; adapt for ticks if needed)
            with self.event_store.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ohlcv_data (time, symbol, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (normalized['time'], normalized['symbol'], normalized.get('open', 0),
                      normalized.get('high', 0), normalized.get('low', 0),
                      normalized.get('close', 0), normalized.get('volume', 0)))
            self.event_store.conn.commit()
            
            # Compute/store features (e.g., ATR; expand with TA-Lib later)
            atr = random.uniform(1.0, 2.0)  # Placeholder; replace with real calc
            self.feature_store.set_feature(normalized['symbol'], 'ATR', atr)
            
            # Audit event
            self.event_store.append_event(
                'data_ingested',
                normalized['symbol'],
                {'open': normalized.get('open'), 'close': normalized.get('close')},
                metadata={'source': self.mode}
            )
            logger.info(f"Ingested data for {normalized['symbol']}")
        except Exception as e:
            logger.error(f"Error ingesting data: {e}")
            raise

    def run_historical(self):
        end_date = datetime.now()
        for symbol in self.symbols:
            self._enable_symbol(symbol)
            start_date = self._get_start_date(symbol)
            for tf_name, tf_value in self.timeframes.items():
                rates = self._fetch_historical(symbol, tf_value, start_date, end_date)
                if rates:
                    df = pd.DataFrame(rates)
                    for _, row in df.iterrows():
                        data = {
                            'time': row['time'], 'symbol': symbol,
                            'open': row['open'], 'high': row['high'],
                            'low': row['low'], 'close': row['close'],
                            'volume': row['tick_volume']
                        }
                        self.ingest_data(data)
                time.sleep(1)  # Rate limit

    def run_live(self):
        while self.running:
            for symbol in self.symbols:
                self._enable_symbol(symbol)
                # Fetch latest tick (or bar); adapt for timeframe
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    data = {
                        'time': tick.time, 'symbol': symbol,
                        'bid': tick.bid, 'ask': tick.ask,
                        'open': tick.last, 'high': tick.last,  # Approximate for tick
                        'low': tick.last, 'close': tick.last,
                        'volume': 0  # Tick volume separate
                    }
                    self.ingest_data(data)
            time.sleep(60)  # Poll every minute; adjust for HFT

    def run_simulate(self):
        while self.running:
            data = {
                'time': datetime.utcnow(), 'symbol': random.choice(self.symbols),
                'open': random.uniform(100, 110), 'high': random.uniform(110, 120),
                'low': random.uniform(90, 100), 'close': random.uniform(100, 110),
                'volume': random.randint(100, 1000)
            }
            self.ingest_data(data)
            time.sleep(1)

    def run(self):
        self.running = True
        if self.mode == 'historical':
            self.run_historical()
        elif self.mode == 'live':
            self.run_live()
        else:
            self.run_simulate()

    def stop(self):
        self.running = False
        if self.mode in ['historical', 'live']:
            mt5.shutdown()
        self.event_store.close()

# Example: Use historical mode
if __name__ == "__main__":
    db_config = {'dbname': 'trading_system', 'user': 'user', 'password': 'password', 'host': 'localhost', 'port': 5432}
    redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
    agent = MarketDataAgent(db_config, redis_config, mode='historical')
    try:
        agent.run()
    except KeyboardInterrupt:
        agent.stop()