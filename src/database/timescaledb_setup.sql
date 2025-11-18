-- src/database/timescaledb_setup.sql
-- Run this script after installing PostgreSQL and TimescaleDB extension

-- Create database if not exists
CREATE DATABASE trading_system;

-- Connect to database
\c trading_system

-- Enable TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create hypertable for market tick data (synthetic: 1-hour chunks)
CREATE TABLE IF NOT EXISTS market_tick_data (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    bid DOUBLE PRECISION,
    ask DOUBLE PRECISION
);
SELECT create_hypertable('market_tick_data', 'time', chunk_time_interval => INTERVAL '1 hour', if_not_exists => TRUE);  -- For synthetics
ALTER TABLE market_tick_data SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('market_tick_data', INTERVAL '3 days');  -- Compress after 3 days with Zstd

-- Create hypertable for OHLCV data (traditional: 1-day chunks)
CREATE TABLE IF NOT EXISTS ohlcv_data (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT
);
SELECT create_hypertable('ohlcv_data', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);  -- For traditional
ALTER TABLE ohlcv_data SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');
SELECT add_compression_policy('ohlcv_data', INTERVAL '3 days');

-- Retention policy example (3 years for ticks, adjust as needed)
SELECT add_retention_policy('market_tick_data', INTERVAL '3 years');

-- Indexes for query optimization
CREATE INDEX IF NOT EXISTS idx_market_tick_symbol_time ON market_tick_data (symbol, time DESC);
CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_time ON ohlcv_data (symbol, time DESC);