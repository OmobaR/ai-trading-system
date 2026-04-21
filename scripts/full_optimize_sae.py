"""
SAE Category-Based Optimizer - Regime-Aware Version
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
import logging

from src.strategy.sae_strategy import SAEStrategy
from src.config.settings import config
from src.events.event_store import EventStore
from src.risk.risk_manager import RiskManagerAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# SYMBOL GROUPING (CORE FIX)
# =========================
CATEGORIES = {
    "synthetics": [
        "GainX 400", "GainX 600", "GainX 800", "GainX 999", "GainX 1200",
        "PainX 400", "PainX 600", "PainX 800", "PainX 999", "PainX 1200",
        "FlipX 1", "FlipX 2", "FlipX 3", "FlipX 4", "FlipX 5"
    ],
    "volatility": [
        "FX Vol 20", "FX Vol 40", "FX Vol 60", "FX Vol 80", "FX Vol 99",
        "SFX Vol 20", "SFX Vol 40", "SFX Vol 60", "SFX Vol 80", "SFX Vol 99"
    ],
    "trend": [
        "TrendX 600", "TrendX 1200", "TrendX 1800",
        "SwitchX 600", "SwitchX 1200", "SwitchX 1800"
    ],
    "breakout": [
        "BreakX 600", "BreakX 1200", "BreakX 1800"
    ],
    "special": [
        "PLUSX 1", "QUADX", "FIBOX"
    ]
}

# =========================
# BACKTEST ENGINE
# =========================
def run_backtest(symbol: str, window: int, threshold: float):
    store = EventStore({
        'host': config.DB_HOST,
        'port': config.DB_PORT,
        'database': config.DB_NAME,
        'user': config.DB_USER,
        'password': config.DB_PASSWORD
    })

    query = """
        SELECT time, open, high, low, close, volume
        FROM ohlcv_data
        WHERE symbol = %s
        ORDER BY time ASC
        LIMIT %s
    """

    df = pd.read_sql(
        query,
        store.conn,
        params=(symbol, 50000),
        index_col='time',
        parse_dates=['time']
    )

    if len(df) < 100:
        return None

    risk_manager = RiskManagerAgent(
        redis_config={'host': 'localhost', 'port': 6379, 'db': 0},
        risk_capital=10000.0
    )

    equity = [10000.0]
    trades = 0
    signals = 0

    strategy = SAEStrategy(
        symbol=symbol,
        window=window,
        threshold=threshold,
        initial_capital=10000.0
    )

    for i in range(len(df) - 1):
        row = df.iloc[i].to_dict()
        signal = strategy.generate_signal(symbol, row, df.index[i])

        if signal:
            signals += 1

        if signal and signal["action"] in ["BUY", "SELL"]:
            trades += 1

            entry = df.iloc[i]["close"]
            exit = df.iloc[i + 1]["close"]

            direction = 1 if signal["action"] == "BUY" else -1
            ret = direction * ((exit - entry) / entry)

            pnl = ret * 0.02 * equity[-1]

            risk_manager.update_risk_metrics(pnl, symbol)

            equity.append(max(equity[-1] + pnl, 1000))

    equity = pd.Series(equity)

    total_return = (equity.iloc[-1] - 10000) / 10000
    returns = equity.pct_change().dropna()

    sharpe = (
        (returns.mean() / returns.std()) * np.sqrt(252)
        if returns.std() > 0 else 0
    )

    max_dd = ((equity.cummax() - equity) / equity.cummax()).max()

    return {
        "return": total_return,
        "sharpe": sharpe,
        "trades": trades,
        "signals": signals,
        "max_dd": max_dd
    }


# =========================
# CATEGORY OPTIMIZER
# =========================
def optimize_category(category_name, symbols):
    print(f"\n===== CATEGORY: {category_name.upper()} =====")

    results = []

    for symbol in symbols:
        print(f"\nTesting {symbol}")

        best_local = None

        for window in [20, 30, 60, 90]:
            for threshold in [0.5, 1.0, 1.5, 2.0]:

                metrics = run_backtest(symbol, window, threshold)

                if not metrics:
                    continue

                results.append({
                    "category": category_name,
                    "symbol": symbol,
                    "window": window,
                    "threshold": threshold,
                    **metrics
                })

                print(
                    f"{symbol} | w={window} t={threshold} "
                    f"R={metrics['return']:.2%} "
                    f"S={metrics['sharpe']:.2f} "
                    f"T={metrics['trades']}"
                )

    df = pd.DataFrame(results)

    if len(df) == 0:
        return None

    best = df.loc[df["sharpe"].idxmax()]

    print("\n===== BEST FOR CATEGORY =====")
    print(best)

    return df


# =========================
# MAIN RUNNER
# =========================
def main():
    all_results = []

    for category, symbols in CATEGORIES.items():
        df = optimize_category(category, symbols)

        if df is not None:
            all_results.append(df)

    if len(all_results) == 0:
        print("No results generated.")
        return

    final_df = pd.concat(all_results)

    final_df.to_csv("sae_category_results.csv", index=False)

    print("\n===== GLOBAL SUMMARY =====")
    print(final_df.groupby("category")[["return", "sharpe", "trades"]].mean())

    best_global = final_df.loc[final_df["sharpe"].idxmax()]

    print("\n===== BEST GLOBAL CONFIG =====")
    print(best_global)


if __name__ == "__main__":
    main()