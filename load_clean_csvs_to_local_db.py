import os
import re
import pandas as pd
from sqlalchemy import create_engine, text
from src.config.settings import config

# ------------------------------------------------------------
# Database connection
# ------------------------------------------------------------
db_uri = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
engine = create_engine(db_uri)

# ------------------------------------------------------------
# Extract symbol and timeframe from filename
# Example: "BreakX_1200_D1.csv" -> symbol="BreakX 1200", tf="d1"
#          "PainX 600_M5.csv"   -> symbol="PainX 600", tf="m5"
# ------------------------------------------------------------
def parse_filename(filename: str):
    # Remove .csv
    name = filename[:-4]
    # Split on underscores
    parts = name.split('_')
    # Timeframe is the last part (e.g., D1, M5, H1, etc.)
    tf_raw = parts[-1]
    # Symbol is everything before the last underscore, with underscores replaced by spaces
    symbol = ' '.join(parts[:-1])
    # Normalise timeframe: keep as lower case (e.g., "d1", "m5")
    tf = tf_raw.lower()
    return symbol, tf

# ------------------------------------------------------------
# Drop all existing per‑timeframe tables (start fresh)
# ------------------------------------------------------------
with engine.connect() as conn:
    result = conn.execute(text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'ohlcv_%'"))
    tables = [row[0] for row in result]
    for table in tables:
        conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        print(f"Dropped {table}")
    conn.commit()

# ------------------------------------------------------------
# Load each CSV file
# ------------------------------------------------------------
csv_folder = r"C:\Users\Olugb\Workspace\ai-trading-system\clean_data\csv"
for file in os.listdir(csv_folder):
    if not file.endswith('.csv'):
        continue
    
    filepath = os.path.join(csv_folder, file)
    print(f"\nProcessing {file}...")
    
    # Parse symbol and timeframe from filename
    symbol, tf = parse_filename(file)
    table_name = f"ohlcv_{tf}"
    print(f"  Symbol: {symbol}, Timeframe: {tf} -> Table: {table_name}")
    
    # Read CSV
    df = pd.read_csv(filepath, parse_dates=['time'])
    
    # Add symbol column (overwrite if it already exists)
    df['symbol'] = symbol
    
    # Standardise column names: rename 'tick_volume' to 'volume' if present
    if 'tick_volume' in df.columns:
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
    
    # Ensure required columns exist
    required = ['time', 'symbol', 'open', 'high', 'low', 'close', 'volume']
    missing = [col for col in required if col not in df.columns]
    if missing:
        print(f"  ERROR: Missing columns {missing} in {file}")
        continue
    
    # Drop any extra columns (optional, but keeps DB clean)
    df = df[required]
    
    # Create hypertable if not exists
    with engine.connect() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                time TIMESTAMPTZ NOT NULL,
                symbol TEXT NOT NULL,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume DOUBLE PRECISION,
                PRIMARY KEY (time, symbol)
            );
        """))
        # Convert to hypertable
        conn.execute(text(f"SELECT create_hypertable('{table_name}', 'time', if_not_exists => TRUE);"))
        conn.commit()
    
    # Insert data in batches
    df.to_sql(table_name, engine, if_exists='append', index=False, method='multi', chunksize=5000)
    print(f"  Inserted {len(df)} rows into {table_name}")

print("\n✅ All done.")