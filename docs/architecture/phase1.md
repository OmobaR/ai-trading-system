# docs/architecture/phase1.md
# Phase 1 Documentation: Core Infrastructure

## Overview
This phase implements the foundational data infrastructure, including an Event Sourcing-based audit trail, TimescaleDB for time-series storage, Redis for real-time features, and a Market Data Agent for ingestion.

## API Specifications

### EventStore Class
- `create_schema()`: Creates the events table and hypertable.
- `append_event(event_type, aggregate_id, data, metadata=None, version=None)`: Appends an immutable event.
- `get_events(aggregate_id=None, event_type=None, start_time=None, end_time=None)`: Retrieves events with filters.
- `reconstruct_state(aggregate_id)`: Reconstructs aggregate state from events (extendable).

### FeatureStore Class
- `set_feature(symbol, feature_name, value)`: Sets a feature using HSET.
- `get_feature(symbol, feature_name)`: Gets a specific feature.
- `get_all_features(symbol)`: Gets all features for a symbol.

### MarketDataAgent Class
- `ingest_data(data)`: Validates, normalizes, stores, and computes features.
- `run()`: Starts the ingestion loop (simulated).
- `stop()`: Stops the agent gracefully.

## Deployment Guide
1. Install Docker and Docker Compose.
2. Run `docker-compose up -d` to start Postgres and Redis.
3. Apply `timescaledb_setup.sql` to Postgres.
4. Build and run the agent: `docker-compose up market_data_agent`.

## Monitoring and Metrics
- Logging: Structured logs via logging module.
- Metrics: Extend with Prometheus client (future: add /metrics endpoint).
- Health Checks: Add liveness probes in Docker (e.g., check DB/Redis ping).

## Test Suites
See tests/ directory (example below).