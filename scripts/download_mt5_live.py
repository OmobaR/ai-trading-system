# scripts/download_mt5_live.py
"""
Live MT5 data downloader with gap-filling for all symbols and timeframes.
Run after CSV import to get the most recent bars.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import logging
import pandas as pd
import MetaTrader5 as mt5

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.events.event_store import EventStore
from src.config.settings import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Full symbol list (exactly as stored in ohlcv_data.symbol)
# -------------------------------------------------------------------
SYMBOLS = [
    "GainX 400", "GainX 600", "GainX 800", "GainX 999", "GainX 1200",
    "PainX 400", "PainX 600", "PainX 800", "PainX 999", "PainX 1200",
    "FlipX 1", "FlipX 2", "FlipX 3", "FlipX 4", "FlipX 5",
    "FX Vol 20", "FX Vol 40", "FX Vol 60", "FX Vol 80", "FX Vol 99",
    "SFX Vol 20", "SFX Vol 40", "SFX Vol 60", "SFX Vol 80", "SFX Vol 99",
    "TrendX 600", "TrendX 1200", "TrendX 1800",
    "SwitchX 600", "SwitchX 1200", "SwitchX 1800",
    "BreakX 600", "BreakX 1200", "BreakX 1800",
    "PLUSX 1", "QUADX", "FIBOX"
]

# -------------------------------------------------------------------
# All timeframes (including weekly and monthly)
# -------------------------------------------------------------------
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

# Maximum bars to request per call (safety, MT5 may limit)
MAX_BARS_PER_CALL = 300000   # high enough for M2 over 2 years


def get_last_timestamp(store, symbol):
    """Get the latest timestamp in DB for a given symbol (any timeframe)."""
    with store.conn.cursor() as cur:
        cur.execute("SELECT MAX(time) FROM ohlcv_data WHERE symbol = %s", (symbol,))
        result = cur.fetchone()[0]
    return result


def download_and_store():
    if not mt5.initialize():
        logger.error("❌ MT5 initialization failed")
        return

    store = EventStore({
        'host': config.DB_HOST,
        'port': config.DB_PORT,
        'database': config.DB_NAME,
        'user': config.DB_USER,
        'password': config.DB_PASSWORD
    })

    # Create staging table for fast upsert (same as CSV importer)
    with store.conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE IF NOT EXISTS ohlcv_staging (
                time TIMESTAMPTZ,
                symbol TEXT,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume BIGINT
            );
        """)
        store.conn.commit()

    total_rows = 0

    for symbol in SYMBOLS:
        # Get last data timestamp for this symbol (from any timeframe, but we'll use it for all TFs)
        last_data = get_last_timestamp(store, symbol)
        if last_data:
            from_date = last_data + timedelta(minutes=1)   # avoid last bar duplicate
            logger.info(f"\n📊 {symbol}: last data = {last_data}, fetching from {from_date}")
        else:
            from_date = datetime(2024, 1, 1)
            logger.info(f"\n📊 {symbol}: no existing data, fetching from {from_date}")

        for tf_name, tf_value in TIMEFRAMES.items():
            logger.info(f"  Downloading {symbol} {tf_name}...")

            # Download all bars from from_date to now
            rates = mt5.copy_rates_range(symbol, tf_value, from_date, datetime.now())
            if rates is None or len(rates) == 0:
                logger.warning(f"    No data returned for {symbol} {tf_name}")
                continue

            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df = df.rename(columns={'tick_volume': 'volume'})
            df['symbol'] = symbol
            df = df[['time', 'symbol', 'open', 'high', 'low', 'close', 'volume']]

            # Clear staging table
            with store.conn.cursor() as cur:
                cur.execute("TRUNCATE ohlcv_staging;")

            # Write DataFrame to temporary CSV for fast COPY
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as tmp:
                tmp_path = tmp.name
                df.to_csv(tmp_path, index=False, header=False)

            # COPY into staging
            with store.conn.cursor() as cur:
                with open(tmp_path, 'r') as f:
                    cur.copy_expert("""
                        COPY ohlcv_staging (time, symbol, open, high, low, close, volume)
                        FROM STDIN WITH (FORMAT CSV, NULL '')
                    """, f)

            # Upsert from staging to main table
            with store.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ohlcv_data (time, symbol, open, high, low, close, volume)
                    SELECT time, symbol, open, high, low, close, volume FROM ohlcv_staging
                    ON CONFLICT (time, symbol) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume;
                """)

            store.conn.commit()
            rows = len(df)
            total_rows += rows
            logger.info(f"    ✅ Inserted/Updated {rows:,} rows for {symbol} {tf_name}")

            # Clean up temp file
            Path(tmp_path).unlink()

    mt5.shutdown()
    logger.info(f"\n🎉 Live download completed! Total rows upserted: {total_rows:,}")


if __name__ == "__main__":
    download_and_store()