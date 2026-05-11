"""
Hidden Markov Model regime discovery for all symbols (robust to outliers).
Fits per‑symbol HMM, saves unified Parquet file.
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from hmmlearn import hmm
from src.config.settings import config
from pathlib import Path
import time
from scipy.stats import mstats

# Database connection
db_uri = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
engine = create_engine(db_uri)

TIMEFRAME = "M5"
N_COMPONENTS = 3
LOOKBACK = 20
WINSORIZE_LIMITS = (0.01, 0.99)   # cap top/bottom 1%

# Get symbol list
print("Fetching symbol list...")
symbols = pd.read_sql("SELECT DISTINCT symbol FROM ohlcv_m5 ORDER BY symbol", engine)['symbol'].tolist()
print(f"Found {len(symbols)} symbols")

output_dir = Path("data/processed/hmm")
output_dir.mkdir(parents=True, exist_ok=True)
all_regime_dfs = []

start = time.time()
for idx, symbol in enumerate(symbols):
    print(f"\n[{idx+1}/{len(symbols)}] {symbol}...")
    query = f"SELECT time, close FROM ohlcv_{TIMEFRAME.lower()} WHERE symbol = '{symbol}' ORDER BY time"
    df = pd.read_sql(query, engine, parse_dates=['time'])
    if len(df) < 200:
        print("  Skipping (insufficient rows)")
        continue
    
    df['returns'] = np.log(df['close'] / df['close'].shift(1)).fillna(0)
    df['volatility'] = df['returns'].rolling(LOOKBACK).std().fillna(0)
    
    # Winsorize
    df['returns_w'] = mstats.winsorize(df['returns'], limits=WINSORIZE_LIMITS)
    df['volatility_w'] = mstats.winsorize(df['volatility'], limits=WINSORIZE_LIMITS)
    
    features = df[['returns_w', 'volatility_w']].dropna().values
    if len(features) < 100:
        print("  Not enough features")
        continue
    
    try:
        model = hmm.GaussianHMM(n_components=N_COMPONENTS, covariance_type="full", n_iter=100, random_state=42)
        model.fit(features)
        states = model.predict(features)
    except Exception as e:
        print(f"  HMM failed: {e}")
        continue
    
    df.loc[df[['returns_w','volatility_w']].dropna().index, 'hmm_state'] = states
    df['symbol'] = symbol
    out = df[['time', 'symbol', 'hmm_state']].dropna()
    all_regime_dfs.append(out)
    out.to_parquet(output_dir / f"{symbol}_hmm_regime.parquet", index=False)
    print(f"  Saved {len(out)} rows")

if all_regime_dfs:
    combined = pd.concat(all_regime_dfs, ignore_index=True)
    combined.to_parquet(output_dir / "all_symbols_hmm_regime.parquet", index=False)
    print(f"\n✅ Combined HMM regimes saved: {len(combined)} rows")
else:
    print("No HMM data generated.")

print(f"Elapsed: {time.time()-start:.1f} seconds")