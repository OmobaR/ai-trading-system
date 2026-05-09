import sys
import os
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# Add project root to sys.path (adjust if needed)
project_root = r"C:\Users\Olugb\Workspace\ai-trading-system"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import your working configuration
from src.config.settings import config

# Build database URI from config (same method that works elsewhere)
try:
    db_uri = getattr(config, 'DB_URI', None)
    if not db_uri:
        db_user = getattr(config, 'DB_USER', 'postgres')
        db_pass = getattr(config, 'DB_PASSWORD', 'postgres')
        db_host = getattr(config, 'DB_HOST', 'localhost')
        db_port = getattr(config, 'DB_PORT', 5432)
        db_name = getattr(config, 'DB_NAME', 'trading')
        db_uri = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    print(f"✅ Using database: postgresql://{db_user}:****@{db_host}:{db_port}/{db_name}")
except Exception as e:
    print(f"⚠️ Config read error, using fallback: {e}")
    db_uri = "postgresql://postgres:postgres@localhost:5432/trading"

# Create engine (no need for autocommit for read-only)
from sqlalchemy import create_engine
engine = create_engine(db_uri)

# Test connection
try:
    with engine.connect() as conn:
        from sqlalchemy import text
        conn.execute(text("SELECT 1"))
    print("✅ Database connection successful!")
except Exception as e:
    print("❌ Connection failed:", e)
    sys.exit(1)

# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------
def median_interval(series):
    """Return median time difference in seconds."""
    diffs = series.diff().dropna().dt.total_seconds()
    return diffs.median() if not diffs.empty else 0

def classify_timeframe(median_sec):
    """Return 'M1', 'M2', or None (tolerance ±5 seconds)."""
    if 55 <= median_sec <= 65:
        return 'M1'
    elif 115 <= median_sec <= 125:
        return 'M2'
    else:
        return None

# ------------------------------------------------------------------
# Main extraction
# ------------------------------------------------------------------
def main():
    # Query the old mixed table (adjust table name if different – likely 'ohlcv_data')
    query = "SELECT time, symbol, open, high, low, close, volume FROM ohlcv_data ORDER BY symbol, time"
    print("Loading data from local DB...")
    df = pd.read_sql(query, engine, parse_dates=['time'])
    print(f"Total rows: {len(df)}")

    output_dir = "m1_m2_extracted"
    os.makedirs(output_dir, exist_ok=True)

    symbols = df['symbol'].unique()
    print(f"Found {len(symbols)} unique symbols.")

    for symbol in symbols:
        sym_df = df[df['symbol'] == symbol].copy()
        sym_df = sym_df.sort_values('time')
        med_sec = median_interval(sym_df['time'])
        tf = classify_timeframe(med_sec)
        if tf:
            filename = f"{symbol}_{tf}.csv"
            filepath = os.path.join(output_dir, filename)
            sym_df.to_csv(filepath, index=False)
            print(f"Saved {len(sym_df)} rows -> {filename} (median interval {med_sec:.1f}s)")
        else:
            print(f"Skipping {symbol} (median interval {med_sec:.1f}s) – not M1/M2")

    print(f"\n✅ Extraction complete. All CSV files are in '{output_dir}' folder.")
    print("Upload these CSV files to your Codespace folder: data_pipeline/data/csv/")

if __name__ == "__main__":
    main()