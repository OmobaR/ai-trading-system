"""
Hidden Markov Model regime discovery for a single symbol.
Fits Gaussian HMM on winsorized returns and volatility.
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from hmmlearn import hmm
from src.config.settings import config
from pathlib import Path
from scipy.stats import mstats

# Database connection
db_uri = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
engine = create_engine(db_uri)

SYMBOL = "GainX 600"
TIMEFRAME = "M5"
N_COMPONENTS = 3
LOOKBACK = 20
WINSORIZE_LIMITS = (0.01, 0.99)   # cap top/bottom 1%

print(f"Loading data for {SYMBOL}...")
query = f"""
SELECT time, close
FROM ohlcv_{TIMEFRAME.lower()}
WHERE symbol = '{SYMBOL}'
ORDER BY time
"""
df = pd.read_sql(query, engine, parse_dates=['time'])
print(f"Loaded {len(df)} rows")

# Calculate returns and volatility
df['returns'] = np.log(df['close'] / df['close'].shift(1)).fillna(0)
df['volatility'] = df['returns'].rolling(LOOKBACK).std().fillna(0)

# Winsorize to remove outliers
df['returns_w'] = mstats.winsorize(df['returns'], limits=WINSORIZE_LIMITS)
df['volatility_w'] = mstats.winsorize(df['volatility'], limits=WINSORIZE_LIMITS)

# Prepare features (drop rows with NaN)
features = df[['returns_w', 'volatility_w']].dropna().values
print(f"Features shape: {features.shape}")

print("Fitting Gaussian HMM...")
model = hmm.GaussianHMM(n_components=N_COMPONENTS, covariance_type="full", n_iter=100, random_state=42)
model.fit(features)
states = model.predict(features)

# Add states back to DataFrame
df.loc[df[['returns_w','volatility_w']].dropna().index, 'hmm_state'] = states

# Interpret states
print("\nState characteristics (winsorized):")
for i in range(N_COMPONENTS):
    mask = df['hmm_state'] == i
    if mask.sum() > 0:
        mean_ret = df.loc[mask, 'returns'].mean()      # original returns
        mean_vol = df.loc[mask, 'volatility'].mean()
        print(f"  State {i}: count={mask.sum():6d}, mean return = {mean_ret:.6f}, mean volatility = {mean_vol:.6f}")
    else:
        print(f"  State {i}: no data")

# Save
output_dir = Path("data/processed/hmm")
output_dir.mkdir(parents=True, exist_ok=True)
output_file = output_dir / f"{SYMBOL}_hmm_regime.parquet"
df[['time', 'symbol', 'hmm_state']].to_parquet(output_file, index=False)
print(f"\nSaved HMM regimes to {output_file}")