## **README.md**

```markdown
# AI Trading System

A production-ready, modular, and extensible autonomous trading platform built in Python.

## Features

- **Market Data Ingestion**: Real-time and historical data from MetaTrader 5 (MT5) - specifically Weltrade's synthetic indices (SyntX).
- **Event Sourcing**: All state changes (trades, signals, data ingestions) recorded via event sourcing.
- **Time-Series Storage**: Efficient storage in TimescaleDB hypertables.
- **Real-Time Feature Store**: Redis for low-latency feature access and regime detection.
- **Modular Components**: Decoupled agents: `MarketDataAgent`, `StrategyAgent`, `RiskAgent`, `ExecutionAgent`, etc.
- **Regime Detection**: Advanced market regime detection using technical indicators and machine learning.
- **NNFX Strategy**: Implementation of the No Nonsense Forex strategy with adaptive regime handling.
- **Risk Management**: Comprehensive risk management with circuit breakers and position sizing.
- **Execution Bridge**: C++ DLL bridge for MQL5 integration.

## Project Structure

```
ai-trading-system/
├── src/                 # Source code
│   ├── config/         # Configuration
│   ├── events/         # Event store
│   ├── market_data/    # Market data agent
│   ├── database/       # Database clients (TimescaleDB, Redis)
│   ├── execution/      # Execution bridge (C++ DLL, MQL5 EA)
│   ├── risk/           # Risk management
│   ├── strategy/       # Trading strategies (NNFX)
│   ├── ml/             # Machine learning models
│   ├── monitoring/     # Monitoring and metrics
│   └── utils/          # Utilities
├── tests/              # Unit, integration, performance tests
├── docker/             # Docker compose files
├── scripts/            # Utility scripts (setup, build, etc.)
├── docs/               # Documentation
└── requirements.txt    # Python dependencies
```

## Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ai-trading-system
   ```

2. **Setup the project**
   ```powershell
   .\scripts\setup_project.ps1
   ```

3. **Build the DLL bridge** (for MT5 integration)
   ```powershell
   .\scripts\build_dll.ps1
   ```

4. **Run the system**
   ```powershell
   .\scripts\run_system.ps1
   ```

## Configuration

Copy `.env.example` to `.env` and set your environment variables (MT5 credentials, database passwords, etc.).

## Testing

Run the test suite:
```bash
python -m pytest tests/ -v
```

## Versioning

We use Semantic Versioning. For the versions available, see the tags on this repository.

## Release

To create a new release:
```powershell
.\scripts\release.ps1 -Version x.x.x
git push origin main --tags
```

## Disclaimer

This software is for educational and research purposes only. Use at your own risk. The authors are not responsible for any financial losses.
```
