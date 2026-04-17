# scripts/fill_gaps.py
"""
Fill missing data from the last available bar in DB to today.
Uses copy_rates_range with per‑symbol start date.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import logging
import pandas as pd
import MetaTrader5 as mt5
import tempfile

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.events.event_store import EventStore
from src.config.settings import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SYMBOLS = [
    "GainX 400", "GainX 600", "GainX 800", "GainX 999", "GainX 1200",
    "PainX 400", "PainX 600", "PainX 800", "PainX 999", "PainX 1200",
    "FlipX 1", "FlipX 2", "FlipX 3", "FlipX 4", "FlipX 5",
    "FX Vol 20", "FX Vol 40", "FX Vol 60", "FX Vol 80", "FX Vol 99",
    "SFX Vol 20", "SFX Vol 40", "SFX Vol 60", "SFX Vol 80", "SFX Vol 99",
    "TrendX 600", "TrendX 1200", "TrendX 1800",
    "SwitchX 600", "SwitchX 1200", "SwitchX 1800",
    "BreakX 600", "BreakX 1200", "BreakX 1800",
]

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M2": mt5.TIMEFRAME_M2,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}

def get_last_timestamp(store, symbol):
    with store.conn.cursor() as cur:
        cur.execute("SELECT MAX(time) FROM ohlcv_data WHERE symbol = %s", (symbol,))
        return cur.fetchone()[0]

def fill_gaps():
    if not mt5.initialize():
        logger.error("MT5 init failed")
        return
    if not mt5.login(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER):
        logger.error("MT5 login failed")
        mt5.shutdown()
        return

    store = EventStore({
        'host': config.DB_HOST,
        'port': config.DB_PORT,
        'database': config.DB_NAME,
        'user': config.DB_USER,
        'password': config.DB_PASSWORD
    })

    # Create staging table
    with store.conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS ohlcv_staging (LIKE ohlcv_data INCLUDING DEFAULTS);")

    total_rows = 0
    for symbol in SYMBOLS:
        last_ts = get_last_timestamp(store, symbol)
        if last_ts is None:
            from_date = datetime(2024, 1, 1)
            logger.info(f"\n📊 {symbol}: no data, fetching from {from_date}")
        else:
            from_date = last_ts + timedelta(minutes=1)  # avoid last bar duplicate
            logger.info(f"\n📊 {symbol}: last data = {last_ts}, fetching from {from_date}")

        for tf_name, tf_value in TIMEFRAMES.items():
            logger.info(f"  Downloading {symbol} {tf_name}...")
            rates = mt5.copy_rates_range(symbol, tf_value, from_date, datetime.now())
            if rates is None or len(rates) == 0:
                logger.warning(f"    No data returned")
                continue

            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df = df.rename(columns={'tick_volume': 'volume'})
            df['symbol'] = symbol
            df = df[['time', 'symbol', 'open', 'high', 'low', 'close', 'volume']]

            with store.conn.cursor() as cur:
                cur.execute("TRUNCATE ohlcv_staging;")
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
                    tmp_path = tmp.name
                    df.to_csv(tmp_path, index=False, header=False)
                with open(tmp_path, 'r') as f:
                    cur.copy_expert("""
                        COPY ohlcv_staging (time, symbol, open, high, low, close, volume)
                        FROM STDIN WITH (FORMAT CSV)
                    """, f)
                cur.execute("""
                    INSERT INTO ohlcv_data (time, symbol, open, high, low, close, volume)
                    SELECT time, symbol, open, high, low, close, volume FROM ohlcv_staging
                    ON CONFLICT (time, symbol) DO NOTHING;
                """)
                store.conn.commit()
                Path(tmp_path).unlink()

            rows = len(df)
            total_rows += rows
            logger.info(f"    ✅ Added {rows:,} rows for {symbol} {tf_name}")

    mt5.shutdown()
    logger.info(f"\n🎉 Gap fill completed! Total rows added: {total_rows:,}")

if __name__ == "__main__":
    fill_gaps()