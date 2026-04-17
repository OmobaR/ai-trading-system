# scripts/eda_ohlcv.py
"""
Exploratory Data Analysis for OHLCV data.
Generates summary statistics, missing data, and basic plots.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.events.event_store import EventStore
from src.config.settings import config

# Use M2 timeframe (primary for SAE) – adjust if needed
TIMEFRAME = "M2"
# Symbols from your list (same as in backtest)
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

def load_data(symbol, timeframe="M2", limit=500000):
    """Load OHLCV data for a given symbol (any timeframe)."""
    store = EventStore({
        'host': config.DB_HOST,
        'port': config.DB_PORT,
        'database': config.DB_NAME,
        'user': config.DB_USER,
        'password': config.DB_PASSWORD
    })
    # We can't filter by timeframe directly – so we load all bars for the symbol.
    # For EDA, we'll load the last 500k bars (covers long history).
    query = """
        SELECT time, open, high, low, close, volume
        FROM ohlcv_data
        WHERE symbol = %s
        ORDER BY time ASC
        LIMIT %s
    """
    df = pd.read_sql(query, store.conn, params=(symbol, limit), index_col='time', parse_dates=['time'])
    return df

def main():
    print("="*80)
    print("OHLCV DATA EXPLORATORY ANALYSIS")
    print("="*80)
    
    all_stats = []
    for sym in SYMBOLS:
        print(f"\nLoading {sym}...")
        df = load_data(sym)
        if df.empty:
            print(f"  ⚠️ No data for {sym}")
            continue
        
        # Basic info
        start = df.index.min()
        end = df.index.max()
        n_bars = len(df)
        missing = df.isnull().sum().sum()
        
        # Return statistics
        df['returns'] = df['close'].pct_change()
        returns = df['returns'].dropna()
        mean_ret = returns.mean()
        std_ret = returns.std()
        skew = returns.skew()
        kurt = returns.kurtosis()
        
        # Volume stats
        vol_mean = df['volume'].mean()
        vol_std = df['volume'].std()
        
        stats = {
            'symbol': sym,
            'start': start,
            'end': end,
            'bars': n_bars,
            'missing': missing,
            'mean_return': mean_ret,
            'std_return': std_ret,
            'skewness': skew,
            'kurtosis': kurt,
            'volume_mean': vol_mean,
            'volume_std': vol_std,
        }
        all_stats.append(stats)
        print(f"  {n_bars} bars from {start.date()} to {end.date()}")
        print(f"  Mean return: {mean_ret:.6f}, Std: {std_ret:.6f}")
    
    # Create DataFrame of statistics
    df_stats = pd.DataFrame(all_stats)
    print("\n" + "="*80)
    print("SUMMARY STATISTICS (per symbol)")
    print("="*80)
    print(df_stats.to_string(index=False))
    
    # Additional analysis: correlation matrix of returns (using last common period)
    # For simplicity, we'll align all symbols on a common date range (last 30 days)
        # Correlation matrix (last 30 days, hourly resampled)
    print("\n" + "="*80)
    print("CORRELATION MATRIX (last 30 days, hourly resampled)")
    print("="*80)
    
    from datetime import timezone
    common_start = datetime.now(timezone.utc) - pd.Timedelta(days=30)
    returns_dict = {}
    for sym in SYMBOLS:
        df = load_data(sym)
        if df.empty:
            continue
        # Resample to hourly (take last close of each hour)
        # Use 'h' instead of deprecated 'H'
        df_hourly = df['close'].resample('1h').last().dropna()
        df_hourly = df_hourly[df_hourly.index >= common_start]
        rets = df_hourly.pct_change().dropna()
        returns_dict[sym] = rets
    
    if returns_dict:
        returns_df = pd.DataFrame(returns_dict)
        corr = returns_df.corr()
        print(corr.round(2))
        
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
            plt.figure(figsize=(12, 10))
            sns.heatmap(corr, annot=False, cmap='coolwarm', center=0)
            plt.title('Correlation of Hourly Returns (Last 30 Days)')
            plt.tight_layout()
            plt.savefig('correlation_heatmap.png')
            print("\n✅ Saved correlation heatmap to 'correlation_heatmap.png'")
        except Exception as e:
            print(f"Could not save plot: {e}")
    else:
        print("Not enough data for correlation matrix.")
    
    # Save full stats to CSV
    df_stats.to_csv('eda_summary.csv', index=False)
    print("\n✅ Saved summary to 'eda_summary.csv'")

if __name__ == "__main__":
    main()