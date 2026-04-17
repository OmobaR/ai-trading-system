# scripts/import_historical_csvs.py
"""
Fast bulk CSV importer using a staging table.
Handles duplicates safely via ON CONFLICT.
"""

import sys
from pathlib import Path
import pandas as pd
import glob
import re
import logging
import tempfile
import os

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.events.event_store import EventStore
from src.config.settings import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CSV_FOLDER = r"C:\Users\Olugb\Workspace\MT5_Trading\MT5_Quant_Research\MT5_Historical_Data"

def extract_symbol_and_tf(filename: str):
    name = Path(filename).stem.upper().replace('_', ' ')
    tf_patterns = ['MN1', 'W1', 'D1', 'H4', 'H1', 'M15', 'M5', 'M2', 'M1']
    tf = 'M5'
    for pattern in tf_patterns:
        if pattern in name:
            tf = pattern
            break

    symbol_match = re.search(
        r'(GAINX|PAINX|FLIPX|TRENDX|SWITCHX|BREAKX|PLUSX|QUADX|FIBOX|FX VOL|SFX VOL)[\s_]*(\d+)?',
        name, re.IGNORECASE
    )
    if symbol_match:
        symbol = symbol_match.group(0).strip()
        symbol = re.sub(r'\s+', ' ', symbol)
    else:
        symbol = name.split(tf)[0].strip() if tf in name else name.split(' ')[0]
    return symbol.strip(), tf

def import_csv_folder():
    store = EventStore({
        'host': config.DB_HOST,
        'port': config.DB_PORT,
        'database': config.DB_NAME,
        'user': config.DB_USER,
        'password': config.DB_PASSWORD
    })

    # Create staging table if it doesn't exist
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

    csv_files = glob.glob(str(Path(CSV_FOLDER) / "*.csv"))
    logger.info(f"Found {len(csv_files)} CSV files. Starting fast bulk import (staging table method)...")

    total_rows = 0

    for csv_path in sorted(csv_files):
        try:
            filename = Path(csv_path).name
            symbol, tf = extract_symbol_and_tf(filename)
            logger.info(f"Processing {filename} → {symbol} {tf}")

            # Read CSV, select only needed columns
            df = pd.read_csv(csv_path, usecols=['time', 'open', 'high', 'low', 'close', 'tick_volume'])
            df = df.rename(columns={'tick_volume': 'volume'})
            df['time'] = pd.to_datetime(df['time'])
            df['symbol'] = symbol
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(int)

            # Write to temp CSV for COPY
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as tmp:
                tmp_path = tmp.name
                df[['time', 'symbol', 'open', 'high', 'low', 'close', 'volume']].to_csv(
                    tmp_path, index=False, header=False
                )

            # COPY into staging table
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
                cur.execute("TRUNCATE ohlcv_staging;")  # clear staging for next file

            store.conn.commit()
            rows = len(df)
            total_rows += rows
            logger.info(f"✅ Imported {rows:,} rows → {symbol} {tf}")

            os.unlink(tmp_path)

        except Exception as e:
            logger.error(f"❌ Failed {filename}: {e}")
            store.conn.rollback()
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    logger.info(f"\n🎉 Fast bulk import completed! Total rows upserted: {total_rows:,}")

if __name__ == "__main__":
    import_csv_folder()