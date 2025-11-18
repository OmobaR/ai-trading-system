#docs/architecture/phase2.md
# Phase 2 Documentation: Execution Engine & Risk Core

## Overview
Implements low-latency bridge, risk agent, and basic NNFX strategy. Bridge uses pybind11-embedded Python in C++ DLL, with shared memory option.

## API Specifications
- RiskManagerAgent: `approve_trade(symbol)` returns size.
- NNFXStrategy: `generate_signal(data)` returns signal.
- DLL: InitBridge(), GetTradeSignal(...), DeInitBridge().

## Deployment Guide
1. Compile DLL with CMake/MSVC (Windows for MT5).
2. Place DLL in MT5 MQL5/Libraries.
3. Attach EA to chart in MT5.

## Monitoring and Metrics
- Logs in DLL and Python.
- Add Prometheus for risk metrics.

## Test Suites
See tests/ directory (example below).