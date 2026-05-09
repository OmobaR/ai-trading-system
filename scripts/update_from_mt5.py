"""
Update all per‑timeframe hypertables with the latest MT5 data.
Run periodically (e.g., daily) after CSV import to keep data fresh.
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
# Full symbol list (exactly as used in filenames and tables)
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
    "PlusX 1", "QuadX", "FiboX" # <-- newly added in src/config/settings.py and properly case-capitalized
]
#-------------------------------------------------------------
# Timeframes (MT5 constants + corresponding table suffix)
# -------------------------------------------------------------------
TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M2": mt5.TIMEFRAME_M2,   # if you have M2 data, otherwise skip
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}

# We will only process timeframes that actually exist as hypertables.
# If a table is missing (e.g., ohlcv_m2), we skip it.
EXISTING_TABLES = {}  # will be populated at runtime


def get_last_timestamp(store, symbol, table_name):
    """Get the latest time for a given symbol in a specific timeframe table."""
    query = f"SELECT MAX(time) FROM {table_name} WHERE symbol = %s"
    with store.conn.cursor() as cur:
        cur.execute(query, (symbol,))
        result = cur.fetchone()[0]
    return result


def update_timeframe(store, symbol, tf_name, tf_value, table_name):
    """Download new bars from MT5 and upsert into the hypertable."""
    last = get_last_timestamp(store, symbol, table_name)
    if last:
        from_date = last + timedelta(minutes=1)   # avoid duplicate last bar
        logger.info(f"    Last data: {last}, fetching from {from_date}")
    else:
        from_date = datetime(2024, 1, 1)   # fallback – should not happen after CSV load
        logger.info(f"    No existing data, fetching from {from_date}")

    # Download all bars from from_date to now
    rates = mt5.copy_rates_range(symbol, tf_value, from_date, datetime.now())
    if rates is None or len(rates) == 0:
        logger.info(f"    No new data for {symbol} {tf_name}")
        return 0

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.rename(columns={'tick_volume': 'volume'}, inplace=True)
    df['symbol'] = symbol
    df = df[['time', 'symbol', 'open', 'high', 'low', 'close', 'volume']]

    # Upsert using a temporary staging table (fastest)
    with store.conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE IF NOT EXISTS staging_{table_name} (LIKE {table_name} INCLUDING DEFAULTS) ON COMMIT DROP;")
        cur.execute(f"TRUNCATE staging_{table_name};")

        # Insert data into staging table via COPY from CSV
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as tmp:
            tmp_path = tmp.name
            df.to_csv(tmp_path, index=False, header=False)

        with open(tmp_path, 'r') as f:
            cur.copy_expert(f"""
                COPY staging_{table_name} (time, symbol, open, high, low, close, volume)
                FROM STDIN WITH (FORMAT CSV, NULL '')
            """, f)

        # Insert into main table on conflict (time, symbol)
        cur.execute(f"""
            INSERT INTO {table_name} (time, symbol, open, high, low, close, volume)
            SELECT time, symbol, open, high, low, close, volume FROM staging_{table_name}
            ON CONFLICT (time, symbol) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume;
        """)
        store.conn.commit()

        Path(tmp_path).unlink()

    rows = len(df)
    logger.info(f"    ✅ Inserted/Updated {rows:,} rows for {symbol} {tf_name}")
    return rows


def main():
    if not mt5.initialize():
        logger.error("❌ MT5 initialization failed. Make sure MetaTrader 5 is running and logged into Weltrade.")
        return

    # Connect to database
    store = EventStore({
        'host': config.DB_HOST,
        'port': config.DB_PORT,
        'database': config.DB_NAME,
        'user': config.DB_USER,
        'password': config.DB_PASSWORD
    })

    # Determine which timeframe tables actually exist
    with store.conn.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE tablename LIKE 'ohlcv_%'")
        existing = {row[0] for row in cur.fetchall()}
    logger.info(f"Found existing tables: {', '.join(sorted(existing))}")

    total_rows = 0
    for symbol in SYMBOLS:
        logger.info(f"\n📊 Processing {symbol}")
        for tf_name, tf_value in TIMEFRAMES.items():
            table_name = f"ohlcv_{tf_name.lower()}"
            if table_name not in existing:
                logger.warning(f"  Skipping {tf_name}: table {table_name} does not exist")
                continue
            rows = update_timeframe(store, symbol, tf_name, tf_value, table_name)
            total_rows += rows

    mt5.shutdown()
    logger.info(f"\n🎉 Update completed! Total new/updated rows: {total_rows:,}")


if __name__ == "__main__":
    main()