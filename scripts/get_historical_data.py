# scripts/get_historical_data.py
"""
Download MAXIMUM available historical data from MT5 to TimescaleDB.
Prioritizes M2, falls back gracefully for M1. Uses copy_rates_from_pos for deepest history.
"""

import sys
from pathlib import Path
import pandas as pd
from datetime import datetime
import argparse
import logging

# ====================== PROJECT PATH FIX ======================
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import MetaTrader5 as mt5
from src.config.settings import config
from src.events.event_store import EventStore

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database config
db_config = {
    'host': config.DB_HOST,
    'port': config.DB_PORT,
    'database': config.DB_NAME,
    'user': config.DB_USER,
    'password': config.DB_PASSWORD
}

# Full symbol list
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

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M2": mt5.TIMEFRAME_M2,      # Preferred fine-grained TF
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}


def fetch_max_history(target_symbol=None):
    """Main function to fetch maximum available history."""
    if not mt5.initialize():
        logger.error("MT5 initialize failed. Make sure MT5 terminal is running and Python integration is enabled.")
        return

    if not mt5.login(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER):
        logger.error(f"MT5 login failed: {mt5.last_error()}")
        mt5.shutdown()
        return

    logger.info("✅ Connected to MT5 - Starting maximum history download...")

    store = EventStore(db_config)
    symbols_to_process = [target_symbol] if target_symbol else SYMBOLS

    for symbol in symbols_to_process:
        if not mt5.symbol_select(symbol, True):
            logger.warning(f"Could not select symbol: {symbol}")
            continue

        logger.info(f"\n📊 Processing {symbol}")

        for tf_name, tf_value in TIMEFRAMES.items():
            logger.info(f"  Fetching {tf_name}...")

            # Shorter history for very fine timeframes
            max_bars = 120000 if tf_name in ["M1", "M2"] else 1000000

            rates = mt5.copy_rates_from_pos(symbol, tf_value, 0, max_bars)

            if rates is None or len(rates) == 0:
                logger.warning(f"    No data available for {tf_name}")
                continue

            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df['symbol'] = symbol
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
            df = df[['time', 'symbol', 'open', 'high', 'low', 'close', 'volume']]

            try:
                with store.conn.cursor() as cur:
                    for _, row in df.iterrows():
                        cur.execute("""
                            INSERT INTO ohlcv_data (time, symbol, open, high, low, close, volume)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (time, symbol) DO UPDATE SET
                                open = EXCLUDED.open,
                                high = EXCLUDED.high,
                                low = EXCLUDED.low,
                                close = EXCLUDED.close,
                                volume = EXCLUDED.volume;
                        """, (row['time'], row['symbol'], float(row['open']), float(row['high']),
                              float(row['low']), float(row['close']), int(row['volume'])))
                store.conn.commit()
                logger.info(f"    ✅ Inserted/updated {len(df):,} bars for {tf_name}")
            except Exception as e:
                logger.error(f"    ❌ DB error for {symbol} {tf_name}: {e}")
                store.conn.rollback()

    mt5.shutdown()
    logger.info("\n🎉 History download completed!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download maximum SyntX history (M2 prioritized)")
    parser.add_argument('--symbol', type=str, help='Process only one symbol (e.g. "PainX 1200")')
    args = parser.parse_args()

    fetch_max_history(target_symbol=args.symbol)