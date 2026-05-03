# Quant Research Organization — Multi-Agent Trading System

A **quant research organization in code**. Not a pipeline — an **orchestrated multi-agent architecture** where each agent owns a constraint, not the system.

---

## Architecture

```
ORCHESTRATOR (Controller)
│
├── DATA AGENT          → clean, validated OHLCV dataset
├── FEATURE AGENT       → proposes 3-layer feature stack (structural/tactical/contextual)
├── GOVERNANCE AGENT    → anti-bloat firewall: KEEP / MERGE / REMOVE
├── [SAE AGENT]         → conditional dimensionality reduction
├── REGIME AGENT        → EMA hierarchy + ADX + liquidity context
├── FILTER AGENT        → bar eligibility based on regime confidence
├── STRATEGY AGENT      → regime-aligned signals (cannot override regime)
├── RISK AGENT          → confidence-scaled, drawdown-aware position sizing
├── BACKTEST AGENT      → simulation with feature consistency + regime correctness checks
├── VALIDATION AGENT    → sanity checks, can halt pipeline
├── OPTIMIZATION AGENT  → walk-forward parameter search
├── DEPLOYMENT AGENT    → MQL5 EA template generation
├── FEEDBACK AGENT      → detects failure patterns, loops back to Feature/Regime
│
└── MEMORY / STATE STORE (shared artifacts)
```

---

## Core Principles

1. **No single agent owns the system. Each agent owns a constraint.**
2. **Governance is mandatory.** Without it, the system **will** overfit.
3. **SAE is conditional.** Triggered only when feature space > 20 dimensions.
4. **Liquidity features are modifiers, not triggers.**
5. **Regime drives everything.** If regime is wrong, everything downstream is wrong.

---

## Quick Start

```bash
cd quant_research_org
pip install -r requirements.txt
python main.py
```

This runs:
- **STEP 1**: Data → Feature → Governance
- **STOP → VALIDATE**: checkpoint before proceeding
- **STEP 2**: Regime Classification
- **Full downstream**: Filter → Strategy → Risk → Backtest → Validation → Optimization → Deployment → Feedback

---

## Project Structure

```
quant_research_org/
├── main.py                     # Entry point
├── requirements.txt
├── core/
│   ├── state_store.py          # Artifact registry + hot cache
│   ├── message_bus.py          # Inter-agent event bus
│   ├── base_agent.py           # Abstract base with artifact I/O
│   └── orchestrator.py         # Pipeline controller
├── agents/
│   ├── data_agent.py           # Phase 1
│   ├── feature_agent.py        # Phase 2
│   ├── governance_agent.py     # Firewall
│   ├── regime_agent.py         # Phase 3
│   ├── filter_agent.py         # Phase 4
│   ├── strategy_agent.py       # Phase 5
│   ├── risk_agent.py           # Phase 6
│   ├── backtest_agent.py       # Phase 7
│   ├── validation_agent.py     # Phase 8
│   ├── optimization_agent.py   # Phase 9
│   ├── deployment_agent.py     # Phase 10 (MQL5)
│   └── feedback_agent.py       # Loopback
├── data/
│   ├── raw/                    # Raw inputs
│   └── processed/              # Artifact outputs + registry
├── config/
├── tests/
└── docs/
```

---

## Agent Contracts

| Agent | Constraint | Input Artifact | Output Artifact |
|-------|-----------|---------------|-----------------|
| Data | Data integrity | Raw data | `clean_ohlcv_dataset` |
| Feature | Feature completeness | Clean dataset | `proposed_feature_set` |
| Governance | Anti-bloat / anti-overfit | Proposed features | `governance_approved_feature_schema` |
| Regime | Regime correctness | Approved features | `regime_labels` |
| Filter | Bar eligibility | Regime labels | `filtered_data` |
| Strategy | Signal consistency with regime | Filtered data | `strategy_signals` |
| Risk | Capital preservation | Signals | `risk_adjusted_orders` |
| Backtest | Simulation integrity | Risk orders | `backtest_report` |
| Validation | Output sanity | Backtest report | `validation_report` |
| Optimization | Parameter robustness | Validation | `optimized_parameters` |
| Deployment | Production readiness | Optimized params | `mql5_ea_template` |
| Feedback | Continuous improvement | Backtest report | `feedback_improvement_plan` |

---

## Extending

To add a new feature layer:
1. Edit `FeatureAgent._build_features()`
2. Re-run STEP 1
3. Governance will auto-evaluate redundancy

To change regime logic:
1. Edit `RegimeAgent._classify_row()`
2. Re-run from STEP 2

---

## From Existing Repos

This architecture supersedes and absorbs concepts from:
- `ai-trading-system`: MT5 ingestion, Redis feature store, NNFX strategy, risk manager
- `alpha_betting_system`: ETL pipeline patterns, Dixon-Coles + XGBoost modeling approach

Key migrations:
- `UnifiedRegimeFeatureStore` → `FeatureAgent` + `RegimeAgent` (separation of concerns)
- `NNFXStrategy` → `StrategyAgent` (regime-aligned, not regime-overriding)
- `RiskManagerAgent` → `RiskAgent` (regime confidence + liquidity proximity integration)
- Event sourcing → `StateStore` artifact registry with lineage tracking
