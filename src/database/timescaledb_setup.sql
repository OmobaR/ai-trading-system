-- TimescaleDB setup for AI Trading System
-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ===================
-- EVENTS TABLE (hypertable)
-- ===================
-- For event sourcing, we often don't need a single-column primary key.
-- We'll use a composite primary key (timestamp, id) to satisfy TimescaleDB.
CREATE TABLE IF NOT EXISTS events (
    id SERIAL,
    event_type TEXT NOT NULL,
    aggregate_id TEXT,
    data JSONB,
    metadata JSONB,
    version INTEGER,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (timestamp, id)
);

-- Convert to hypertable
SELECT create_hypertable('events', 'timestamp', if_not_exists => TRUE);

-- Indexes for fast filtering
CREATE INDEX IF NOT EXISTS idx_events_aggregate_id ON events(aggregate_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type, timestamp DESC);

-- ===================
-- MARKET_DATA TABLE (hypertable)
-- ===================
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL,
    symbol TEXT NOT NULL,
    open DECIMAL(20,8),
    high DECIMAL(20,8),
    low DECIMAL(20,8),
    close DECIMAL(20,8),
    volume BIGINT,
    timestamp TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (timestamp, id)
);

SELECT create_hypertable('market_data', 'timestamp', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_market_data_symbol_timestamp ON market_data(symbol, timestamp DESC);

-- ===================
-- TRADE_SIGNALS TABLE (hypertable)
-- ===================
CREATE TABLE IF NOT EXISTS trade_signals (
    id SERIAL,
    symbol TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    confidence DECIMAL(5,4),
    position_size DECIMAL(10,6),
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    strategy TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (timestamp, id)
);

SELECT create_hypertable('trade_signals', 'timestamp', if_not_exists => TRUE);