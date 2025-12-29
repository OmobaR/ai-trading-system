-- src/database/timescaledb_setup.sql
-- Enhanced TimescaleDB Setup for AI Trading System
-- Run this script after installing PostgreSQL and TimescaleDB extension

-- Create database if not exists
CREATE DATABASE ai_trading_db;

-- Connect to database
\c ai_trading_db

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Enable additional extensions for advanced functionality
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- Query performance monitoring
CREATE EXTENSION IF NOT EXISTS postgis;            -- Geospatial data (if needed)

-- Create hypertable for market tick data (high-frequency: 1-hour chunks)
CREATE TABLE IF NOT EXISTS market_tick_data (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    bid DOUBLE PRECISION,
    ask DOUBLE PRECISION,
    spread DOUBLE PRECISION GENERATED ALWAYS AS (ask - bid) STORED,
    volume INTEGER DEFAULT 0
);

SELECT create_hypertable(
    'market_tick_data', 
    'time', 
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Create hypertable for OHLCV data (traditional: 1-day chunks)
CREATE TABLE IF NOT EXISTS ohlcv_data (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT,
    -- Computed columns for common calculations
    price_range DOUBLE PRECISION GENERATED ALWAYS AS (high - low) STORED,
    price_change DOUBLE PRECISION GENERATED ALWAYS AS (close - open) STORED,
    price_change_pct DOUBLE PRECISION GENERATED ALWAYS AS ((close - open) / open * 100) STORED,
    PRIMARY KEY (time, symbol)
);

SELECT create_hypertable(
    'ohlcv_data', 
    'time', 
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Create enhanced events table for event sourcing
CREATE TABLE IF NOT EXISTS events (
    id SERIAL,
    event_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    data JSONB NOT NULL,
    metadata JSONB NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1
);

SELECT create_hypertable('events', 'timestamp', if_not_exists => TRUE);

-- Create regime events table for regime tracking
CREATE TABLE IF NOT EXISTS regime_events (
    id SERIAL,
    symbol TEXT NOT NULL,
    regime_type TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    features JSONB NOT NULL,
    signals JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    regime_model TEXT DEFAULT 'basic'
);

SELECT create_hypertable('regime_events', 'timestamp', if_not_exists => TRUE);

-- Create ML features table for persistent feature storage
CREATE TABLE IF NOT EXISTS ml_features (
    id SERIAL,
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    features JSONB NOT NULL,
    regime_type TEXT,
    regime_confidence DOUBLE PRECISION,
    nnfx_signal TEXT,
    signal_confidence DOUBLE PRECISION,
    regime_model TEXT
);

SELECT create_hypertable('ml_features', 'timestamp', if_not_exists => TRUE);

-- Create performance metrics table for strategy analysis
CREATE TABLE IF NOT EXISTS performance_metrics (
    id SERIAL,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    returns DOUBLE PRECISION,
    sharpe_ratio DOUBLE PRECISION,
    max_drawdown DOUBLE PRECISION,
    volatility DOUBLE PRECISION,
    metrics JSONB
);

SELECT create_hypertable('performance_metrics', 'timestamp', if_not_exists => TRUE);

-- Enable compression on all hypertables
ALTER TABLE market_tick_data SET (
    timescaledb.compress, 
    timescaledb.compress_segmentby = 'symbol'
);

ALTER TABLE ohlcv_data SET (
    timescaledb.compress, 
    timescaledb.compress_segmentby = 'symbol'
);

ALTER TABLE events SET (
    timescaledb.compress, 
    timescaledb.compress_segmentby = 'event_type'
);

ALTER TABLE regime_events SET (
    timescaledb.compress, 
    timescaledb.compress_segmentby = 'symbol'
);

ALTER TABLE ml_features SET (
    timescaledb.compress, 
    timescaledb.compress_segmentby = 'symbol'
);

ALTER TABLE performance_metrics SET (
    timescaledb.compress, 
    timescaledb.compress_segmentby = 'strategy_id'
);

-- Add compression policies (compress after 1 day)
SELECT add_compression_policy('market_tick_data', INTERVAL '1 day');
SELECT add_compression_policy('ohlcv_data', INTERVAL '1 day');
SELECT add_compression_policy('events', INTERVAL '1 day');
SELECT add_compression_policy('regime_events', INTERVAL '1 day');
SELECT add_compression_policy('ml_features', INTERVAL '1 day');
SELECT add_compression_policy('performance_metrics', INTERVAL '1 day');

-- Retention policies (keep data for different durations)
SELECT add_retention_policy('market_tick_data', INTERVAL '6 months');  -- High-frequency, shorter retention
SELECT add_retention_policy('ohlcv_data', INTERVAL '3 years');         -- OHLCV, longer retention
SELECT add_retention_policy('events', INTERVAL '2 years');             -- Events, medium retention
SELECT add_retention_policy('regime_events', INTERVAL '1 year');       -- Regime events
SELECT add_retention_policy('ml_features', INTERVAL '6 months');       -- ML features
SELECT add_retention_policy('performance_metrics', INTERVAL '1 year'); -- Performance data

-- Create indexes for optimal query performance
-- Market tick data indexes
CREATE INDEX IF NOT EXISTS idx_market_tick_symbol_time 
ON market_tick_data (symbol, time DESC);

CREATE INDEX IF NOT EXISTS idx_market_tick_time 
ON market_tick_data (time DESC);

-- OHLCV data indexes
CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_time 
ON ohlcv_data (symbol, time DESC);

CREATE INDEX IF NOT EXISTS idx_ohlcv_time 
ON ohlcv_data (time DESC);

CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_time_range 
ON ohlcv_data (symbol, time DESC) 
WHERE time > NOW() - INTERVAL '30 days';

-- Events indexes
CREATE INDEX IF NOT EXISTS idx_events_aggregate_id 
ON events (aggregate_id);

CREATE INDEX IF NOT EXISTS idx_events_timestamp 
ON events (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_events_event_type 
ON events (event_type);

CREATE INDEX IF NOT EXISTS idx_events_aggregate_time 
ON events (aggregate_id, timestamp DESC);

-- Regime events indexes
CREATE INDEX IF NOT EXISTS idx_regime_events_symbol 
ON regime_events (symbol);

CREATE INDEX IF NOT EXISTS idx_regime_events_timestamp 
ON regime_events (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_regime_events_regime_type 
ON regime_events (regime_type);

CREATE INDEX IF NOT EXISTS idx_regime_events_symbol_time 
ON regime_events (symbol, timestamp DESC);

-- ML features indexes
CREATE INDEX IF NOT EXISTS idx_ml_features_symbol 
ON ml_features (symbol);

CREATE INDEX IF NOT EXISTS idx_ml_features_timestamp 
ON ml_features (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ml_features_regime 
ON ml_features (regime_type);

CREATE INDEX IF NOT EXISTS idx_ml_features_symbol_time 
ON ml_features (symbol, timestamp DESC);

-- Performance metrics indexes
CREATE INDEX IF NOT EXISTS idx_perf_strategy_time 
ON performance_metrics (strategy_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_perf_symbol_time 
ON performance_metrics (symbol, timestamp DESC);

-- Create continuous aggregates for common queries
-- Daily OHLCV summary
CREATE MATERIALIZED VIEW ohlcv_daily
WITH (timescaledb.continuous) AS
SELECT 
    symbol,
    time_bucket('1 day', time) as bucket,
    FIRST(open, time) as open,
    MAX(high) as high,
    MIN(low) as low,
    LAST(close, time) as close,
    SUM(volume) as volume
FROM ohlcv_data
GROUP BY symbol, bucket
WITH NO DATA;

-- Add refresh policy for daily aggregate (refresh every hour)
SELECT add_continuous_aggregate_policy('ohlcv_daily',
    start_offset => INTERVAL '1 month',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

-- Regime statistics view
CREATE MATERIALIZED VIEW regime_stats_daily
WITH (timescaledb.continuous) AS
SELECT 
    symbol,
    regime_type,
    time_bucket('1 day', timestamp) as bucket,
    COUNT(*) as count,
    AVG(confidence) as avg_confidence,
    MIN(confidence) as min_confidence,
    MAX(confidence) as max_confidence
FROM regime_events
GROUP BY symbol, regime_type, bucket
WITH NO DATA;

SELECT add_continuous_aggregate_policy('regime_stats_daily',
    start_offset => INTERVAL '1 month',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

-- Create useful views for common queries
CREATE OR REPLACE VIEW current_regimes AS
SELECT 
    symbol,
    regime_type,
    confidence,
    timestamp
FROM regime_events
WHERE timestamp = (
    SELECT MAX(timestamp) 
    FROM regime_events AS re 
    WHERE re.symbol = regime_events.symbol
);

CREATE OR REPLACE VIEW regime_transitions AS
SELECT 
    symbol,
    LAG(regime_type) OVER (PARTITION BY symbol ORDER BY timestamp) as previous_regime,
    regime_type as current_regime,
    timestamp,
    EXTRACT(EPOCH FROM (timestamp - LAG(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp))) as seconds_since_change
FROM regime_events;

-- Create functions for common operations
CREATE OR REPLACE FUNCTION get_regime_history(
    p_symbol TEXT,
    p_days INTEGER DEFAULT 30
)
RETURNS TABLE(
    timestamp TIMESTAMPTZ,
    regime_type TEXT,
    confidence DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        re.timestamp,
        re.regime_type,
        re.confidence
    FROM regime_events re
    WHERE re.symbol = p_symbol
        AND re.timestamp >= NOW() - (p_days || ' days')::INTERVAL
    ORDER BY re.timestamp DESC;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION calculate_regime_stats(
    p_symbol TEXT,
    p_start_date TIMESTAMPTZ DEFAULT NOW() - INTERVAL '30 days',
    p_end_date TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE(
    regime_type TEXT,
    occurrence_count BIGINT,
    avg_confidence DOUBLE PRECISION,
    total_duration INTERVAL
) AS $$
BEGIN
    RETURN QUERY
    WITH regime_periods AS (
        SELECT
            regime_type,
            confidence,
            timestamp as start_time,
            LEAD(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) as end_time
        FROM regime_events
        WHERE symbol = p_symbol
            AND timestamp BETWEEN p_start_date AND p_end_date
    )
    SELECT
        regime_type,
        COUNT(*) as occurrence_count,
        AVG(confidence) as avg_confidence,
        SUM(COALESCE(end_time, p_end_date) - start_time) as total_duration
    FROM regime_periods
    GROUP BY regime_type
    ORDER BY occurrence_count DESC;
END;
$$ LANGUAGE plpgsql;

-- Create user for application with limited permissions
CREATE USER trading_app WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE ai_trading_db TO trading_app;
GRANT USAGE ON SCHEMA public TO trading_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO trading_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO trading_app;

-- Create read-only user for analytics
CREATE USER analytics_user WITH PASSWORD 'readonly_password';
GRANT CONNECT ON DATABASE ai_trading_db TO analytics_user;
GRANT USAGE ON SCHEMA public TO analytics_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_user;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO analytics_user;

-- Output completion message
DO $$
BEGIN
    RAISE NOTICE '✅ AI Trading System database setup completed successfully!';
    RAISE NOTICE '📊 Hypertables created: market_tick_data, ohlcv_data, events, regime_events, ml_features, performance_metrics';
    RAISE NOTICE '⚡ Continuous aggregates created: ohlcv_daily, regime_stats_daily';
    RAISE NOTICE '🔑 Users created: trading_app (read/write), analytics_user (read-only)';
    RAISE NOTICE '📈 Indexes and compression policies applied for optimal performance';
END $$;
