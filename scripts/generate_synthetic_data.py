#!/usr/bin/env python3
"""
Generate synthetic historical OHLCV data for backtesting.
Run from project root: python scripts/generate_synthetic_data.py
"""

import os
import sys
import random
from datetime import datetime, timedelta
import psycopg2

# Database config from environment
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'dbname': os.getenv('POSTGRES_DB', 'ai_trading_db'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'password')
}

def generate_synthetic_data(symbols, days=30, timeframe_hours=1):
    """Generate synthetic OHLCV data and insert into ohlcv_data"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    num_bars = int(days * 24 / timeframe_hours)
    
    print(f"Generating {num_bars} bars per symbol from {start_date} to {end_date}")
    
    insert_sql = """
        INSERT INTO ohlcv_data (time, symbol, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (time, symbol) DO NOTHING
    """
    
    for symbol in symbols:
        print(f"  Generating for {symbol}...")
        base_price = 100.0 + random.uniform(0, 50)
        rows = []
        for i in range(num_bars):
            timestamp = start_date + timedelta(hours=i * timeframe_hours)
            # Random walk with drift
            change = random.gauss(0, 0.01)  # 1% volatility
            close = base_price * (1 + change)
            open_price = base_price
            high = max(open_price, close) + abs(change) * base_price * random.uniform(0, 0.5)
            low = min(open_price, close) - abs(change) * base_price * random.uniform(0, 0.5)
            volume = int(random.uniform(500, 5000))
            rows.append((timestamp, symbol, open_price, high, low, close, volume))
            base_price = close
        
        # Use executemany (works with multiple %s placeholders)
        cur.executemany(insert_sql, rows)
        conn.commit()
        print(f"    Inserted {len(rows)} rows.")
    
    cur.close()
    conn.close()
    print("Synthetic data generation complete.")

if __name__ == "__main__":
    symbols = [
        "GainX 400", "GainX 600", "GainX 800",
        "PainX 400", "PainX 600",
        "TrendX 600", "BreakX 600", "FlipX 1"
    ]
    generate_synthetic_data(symbols, days=30, timeframe_hours=1)