# AI Trading System – Complete Technical Description

## 1. Overview
This project is a **zero‑cost, local, multi‑agent quant research platform** integrating MetaTrader 5 (MT5) with a Python‑based research pipeline. It runs entirely on a Windows machine (8GB RAM, Intel Celeron B830) using Docker for databases and Parquet for memory‑safe streaming.

## 2. High‑Level Architecture 
┌─────────────────────────────────────────────────────────────────┐
│ LOCAL MACHINE │
├─────────────────────────────────────────────────────────────────┤
│ MT5 Terminal (Weltrade) │ Docker Services │
│ - SAE Engine (MQL5) │ - TimescaleDB (port 5432) │
│ - CSV signal bridge │ - Redis (port 6379) │
├─────────────────────────────────────────────────────────────────┤
│ Python Environment (ai_trading_env) │
│ ├── src/ (live trading) │
│ ├── quant_research_org/ (research pipeline) │
│ │ ├── data_agent → feature_agent → governance_agent │
│ │ ├── regime_agent → filter_agent → strategy_agent │
│ │ ├── risk_agent → backtest_agent → validation_agent │
│ │ ├── optimization_agent → deployment_agent → feedback_agent│
│ │ └── core/ (StateStore, MessageBus, BaseAgent) │
│ ├── data_pipeline/ (data ingestion & cleaning) │
│ └── scripts/ (MT5 live updater, extraction scripts) │
└─────────────────────────────────────────────────────────────────┘

text

## 3. Data Infrastructure
- **TimescaleDB** (Docker) stores per‑timeframe hypertables (`ohlcv_m5`, `ohlcv_m15`, …, `ohlcv_mn1`).
- **13.5 million rows** of clean M5 data for 37 synthetic symbols (500 days).
- **Parquet files** for all intermediate pipeline outputs (memory‑safe, columnar).
- **MT5 live updater** (`scripts/update_from_mt5.py`) fetches new bars directly from MT5.

## 4. Research Pipeline (12 Agents)
All agents are **deterministic** (no LLM calls), **memory‑safe**, and **resumable** (using Parquet artifacts).

| Agent | Responsibility |
|-------|----------------|
| DataAgent | Loads OHLCV data from TimescaleDB |
| FeatureAgent | Computes 22 features: EMAs, RSI, yearly range, ATR, liquidity proxies |
| GovernanceAgent | Removes redundant features (correlation > 0.9); approves 22 features |
| RegimeAgent | Classifies each bar into `trend_continuation`, `weak_trend`, `range`, `breakout`, `transition` and outputs continuous `trend_strength` |
| FilterAgent | Applies min_confidence (0.4) and optionally removes transition bars |
| StrategyAgent | Uses `trend_strength` + volatility filter (`ATR < 1.5× median`) to generate `direction` (±1) and `confidence`; adds mean‑reversion when trend weak |
| RiskAgent | Position sizing based on ATR, confidence scaling, drawdown circuit breaker |
| BacktestAgent | Realistic simulation using `next_close` returns, transaction costs (0.01%) |
| ValidationAgent | Sanity checks (Sharpe, drawdown, win rate) |
| OptimizationAgent | Grid search over parameters (trend threshold, vol multiplier, min confidence, RSI bound) |
| DeploymentAgent | Generates MQL5 EA template (full code with EMAs, RSI, ATR, trade logic) |
| FeedbackAgent | Suggests improvements based on backtest metrics |

## 5. Live Trading Integration
- MT5 reads CSV signals (`SAE_Signals.csv`) → Python `src/main.py` ingests them.
- MQL5 EA (`src/execution/mql5/AutoGen_RegimeEA_v1.mq5`) can run independently, implementing the same regime logic.
- Redis (optional) can be used as a feature cache between research and live system.

## 6. Strategy Performance (Latest Medium Test – 10 symbols, 10,000 bars)

| Metric               | Value   |
|----------------------|---------|
| Total trades         | 359,548 |
| Win rate             | 42.4%   |
| Profit factor        | 1.34    |
| Sharpe ratio         | 0.022   |
| Max drawdown*        | 3904%   |

*Drawdown is unrealistic due to simplified risk model (no position‑sizing limits). In practice, the EA would have per‑trade risk limits and drawdown halts.

## 7. Key Scripts & Entry Points

| Script | Purpose |
|--------|---------|
| `resume_from_regime.py` | Runs full pipeline from regime phase (37 symbols, 500 days) |
| `medium_test_10_symbols.py` | Fast test on 10 symbols, last 10000 bars |
| `optimize_strategy.py` | Sequential grid search for strategy parameters |
| `hmm_all_symbols.py` | Fits HMM regime discovery for all symbols |
| `meta_labeling_v2.py` | XGBoost meta‑labeling (filters strategy signals) |
| `scripts/update_from_mt5.py` | Updates TimescaleDB with latest MT5 data |

## 8. Remaining Work (Roadmap)

| Priority | Task | Expected Improvement |
|----------|------|----------------------|
| High | **Fix risk model** (position sizing, max concurrent trades) | Reduce drawdown < 20% |
| High | **Walk‑forward validation** (train/test splits over time) | Avoid overfitting |
| Medium | **Improve strategy win rate** (tune thresholds, add features) | Win rate > 45% |
| Medium | **Enhance meta‑labeling** (more features, calibrated threshold) | Win rate > 55% |
| Low | **HMM integration** (fix errors, use as regime input) | Alternative regime labels |

## 9. How to Run a Full Backtest

```bash
conda activate ai_trading_env
python resume_from_regime.py
This will take ~12 hours to process 37 symbols with 500 days of M5 data.

10. How to Deploy the MQL5 EA
Open src/execution/mql5/AutoGen_RegimeEA_v1.mq5 in MetaEditor.

Compile (F7) and attach to a chart.

Adjust input parameters (trend threshold, volatility multiplier, etc.) using the optimised values from best_params.txt.

11. Conclusion
This system provides a complete, reproducible, zero‑cost quant research environment. The strategy currently has a positive edge (profit factor 1.34) but requires risk management improvements to become deployable. The infrastructure is ready for further enhancements (walk‑forward, meta‑labeling, improved HMM). All code and data are version‑controlled and can be shared or extended.

Date: May 11, 2026
Author: Olugbenga (OmobaR)
