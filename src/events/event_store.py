# src/events/event_store.py
from typing import Dict, Any, List
from datetime import timedelta
import psycopg2
from psycopg2 import sql
import json
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EventStore:
    def __init__(self, db_config):
        self.db_config = db_config
        self.conn = None
        self.connect()

    def connect(self):
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.conn.autocommit = False
            logger.info("✅ Connected to PostgreSQL database")
        except psycopg2.Error as e:
            logger.error(f"❌ Error connecting to PostgreSQL: {e}")
            raise

    def create_schema(self):
        """Create enhanced event store schema with regime support"""
        try:
            with self.conn.cursor() as cur:
                # Create main events table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id SERIAL PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        aggregate_id TEXT NOT NULL,
                        data JSONB NOT NULL,
                        metadata JSONB NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        version INTEGER NOT NULL DEFAULT 1
                    );
                """)
                
                # Create regime-specific events table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS regime_events (
                        id SERIAL PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        regime_type TEXT NOT NULL,
                        confidence DECIMAL NOT NULL,
                        features JSONB NOT NULL,
                        signals JSONB,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Create OHLCV data table (if not exists)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ohlcv_data (
                        time TIMESTAMPTZ NOT NULL,
                        symbol TEXT NOT NULL,
                        open DECIMAL,
                        high DECIMAL,
                        low DECIMAL,
                        close DECIMAL,
                        volume BIGINT,
                        PRIMARY KEY (time, symbol)
                    );
                """)
                
                # Create indexes for efficient querying
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_events_aggregate_id ON events (aggregate_id);
                    CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp);
                    CREATE INDEX IF NOT EXISTS idx_events_event_type ON events (event_type);
                    CREATE INDEX IF NOT EXISTS idx_regime_events_symbol ON regime_events (symbol);
                    CREATE INDEX IF NOT EXISTS idx_regime_events_timestamp ON regime_events (timestamp);
                    CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_time ON ohlcv_data (symbol, time DESC);
                """)
                
                # Convert to TimescaleDB hypertables
                try:
                    cur.execute("SELECT create_hypertable('events', 'timestamp', if_not_exists => TRUE);")
                    cur.execute("SELECT create_hypertable('regime_events', 'timestamp', if_not_exists => TRUE);")
                    cur.execute("SELECT create_hypertable('ohlcv_data', 'time', if_not_exists => TRUE);")
                except psycopg2.Error as e:
                    logger.warning(f"TimescaleDB extension not available: {e}")
                
                # Add compression for events table
                try:
                    cur.execute("ALTER TABLE events SET (timescaledb.compress, timescaledb.compress_segmentby = 'event_type');")
                    cur.execute("ALTER TABLE regime_events SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');")
                    cur.execute("ALTER TABLE ohlcv_data SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol');")
                except psycopg2.Error as e:
                    logger.warning(f"Could not set compression: {e}")
                
            self.conn.commit()
            logger.info("✅ Event store schema created successfully")
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"❌ Error creating schema: {e}")
            raise

    def append_event(self, event_type, aggregate_id, data, metadata=None, version=None):
        """Append event with enhanced error handling"""
        if metadata is None:
            metadata = {}
        
        if version is None:
            version = 1
            
        try:
            with self.conn.cursor() as cur:
                # Optional version check for optimistic concurrency
                if version > 1:
                    cur.execute("""
                        SELECT version FROM events 
                        WHERE aggregate_id = %s 
                        ORDER BY version DESC LIMIT 1;
                    """, (aggregate_id,))
                    current_version = cur.fetchone()
                    if current_version and current_version[0] >= version:
                        raise ValueError("Concurrency conflict: Event version mismatch")

                cur.execute("""
                    INSERT INTO events (event_type, aggregate_id, data, metadata, version)
                    VALUES (%s, %s, %s, %s, %s);
                """, (event_type, aggregate_id, json.dumps(data), json.dumps(metadata), version))
            
            self.conn.commit()
            logger.debug(f"✅ Appended event: {event_type} for aggregate {aggregate_id}")
        except (psycopg2.Error, ValueError) as e:
            self.conn.rollback()
            logger.error(f"❌ Error appending event: {e}")
            raise

    def append_regime_event(self, symbol: str, regime_type: str, confidence: float, 
                          features: Dict, signals: Dict = None):
        """Append regime-specific event"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO regime_events (symbol, regime_type, confidence, features, signals)
                    VALUES (%s, %s, %s, %s, %s);
                """, (symbol, regime_type, confidence, json.dumps(features), 
                      json.dumps(signals) if signals else None))
            
            self.conn.commit()
            logger.debug(f"✅ Appended regime event for {symbol}: {regime_type}")
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"❌ Error appending regime event: {e}")
            raise

    def get_events(self, aggregate_id=None, event_type=None, start_time=None, end_time=None, limit=1000):
        """Get events with enhanced filtering"""
        try:
            with self.conn.cursor() as cur:
                query = sql.SQL("SELECT * FROM events WHERE TRUE")
                params = []
                
                if aggregate_id:
                    query += sql.SQL(" AND aggregate_id = %s")
                    params.append(aggregate_id)
                if event_type:
                    query += sql.SQL(" AND event_type = %s")
                    params.append(event_type)
                if start_time:
                    query += sql.SQL(" AND timestamp >= %s")
                    params.append(start_time)
                if end_time:
                    query += sql.SQL(" AND timestamp <= %s")
                    params.append(end_time)
                
                query += sql.SQL(" ORDER BY timestamp ASC LIMIT %s;")
                params.append(limit)
                
                cur.execute(query, params)
                return cur.fetchall()
        except psycopg2.Error as e:
            logger.error(f"❌ Error retrieving events: {e}")
            raise

    def get_regime_events(self, symbol=None, regime_type=None, start_time=None, end_time=None, limit=1000):
        """Get regime events with filtering"""
        try:
            with self.conn.cursor() as cur:
                query = sql.SQL("SELECT * FROM regime_events WHERE TRUE")
                params = []
                
                if symbol:
                    query += sql.SQL(" AND symbol = %s")
                    params.append(symbol)
                if regime_type:
                    query += sql.SQL(" AND regime_type = %s")
                    params.append(regime_type)
                if start_time:
                    query += sql.SQL(" AND timestamp >= %s")
                    params.append(start_time)
                if end_time:
                    query += sql.SQL(" AND timestamp <= %s")
                    params.append(end_time)
                
                query += sql.SQL(" ORDER BY timestamp ASC LIMIT %s;")
                params.append(limit)
                
                cur.execute(query, params)
                return cur.fetchall()
        except psycopg2.Error as e:
            logger.error(f"❌ Error retrieving regime events: {e}")
            raise

    def get_regime_statistics(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """Get statistics about regime patterns for a symbol"""
        try:
            with self.conn.cursor() as cur:
                start_time = datetime.now() - timedelta(days=days)
                
                cur.execute("""
                    SELECT 
                        regime_type,
                        COUNT(*) as count,
                        AVG(confidence) as avg_confidence,
                        MIN(timestamp) as first_occurrence,
                        MAX(timestamp) as last_occurrence
                    FROM regime_events 
                    WHERE symbol = %s AND timestamp >= %s
                    GROUP BY regime_type
                    ORDER BY count DESC;
                """, (symbol, start_time))
                
                results = cur.fetchall()
                
                regime_stats = {}
                total_events = 0
                
                for regime_type, count, avg_confidence, first_occurrence, last_occurrence in results:
                    regime_stats[regime_type] = {
                        'count': count,
                        'percentage': 0,  # Will calculate after
                        'avg_confidence': float(avg_confidence) if avg_confidence else 0,
                        'first_occurrence': first_occurrence,
                        'last_occurrence': last_occurrence
                    }
                    total_events += count
                
                # Calculate percentages
                for regime_type in regime_stats:
                    regime_stats[regime_type]['percentage'] = (
                        regime_stats[regime_type]['count'] / total_events * 100
                        if total_events > 0 else 0
                    )
                
                return {
                    'symbol': symbol,
                    'total_events': total_events,
                    'period_days': days,
                    'regimes': regime_stats,
                    'most_common_regime': max(regime_stats, key=lambda x: regime_stats[x]['count']) if regime_stats else None
                }
                
        except psycopg2.Error as e:
            logger.error(f"❌ Error getting regime statistics: {e}")
            return {}

    def reconstruct_state(self, aggregate_id):
        """Reconstruct aggregate state from events"""
        events = self.get_events(aggregate_id=aggregate_id)
        state = {}
        
        for event in events:
            event_type = event[1]
            data = event[3]
            
            # Apply events to reconstruct state
            if event_type == 'signal_generated':
                state['signal'] = data
            elif event_type == 'order_placed':
                state['order'] = data
            elif event_type == 'data_ingested_with_regime':
                state['last_data'] = data
                state['last_regime'] = data.get('regime')
            # Extend for other event types as needed
        
        return state

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("✅ Database connection closed")

# Enhanced example usage
if __name__ == "__main__":
    db_config = {
        'dbname': 'trading_system',
        'user': 'postgres',
        'password': 'password',
        'host': 'localhost',
        'port': 5432
    }
    
    store = EventStore(db_config)
    
    try:
        # Create schema
        store.create_schema()
        
        # Append sample events
        store.append_event(
            event_type='signal_generated',
            aggregate_id='123e4567-e89b-12d3-a456-426614174000',
            data={'symbol': 'GainX 600', 'action': 'buy', 'price': 100.5, 'confidence': 0.85},
            metadata={'strategy': 'nnfx', 'regime': 'trending_high_vol'},
            version=1
        )
        
        # Append regime event
        store.append_regime_event(
            symbol='GainX 600',
            regime_type='trending_high_vol',
            confidence=0.92,
            features={
                'volatility': 0.067,
                'trend_strength': 0.045,
                'adx': 32.5,
                'atr': 0.0034
            },
            signals={
                'nnfx_signal': 'BUY',
                'confidence': 0.88
            }
        )
        
        # Retrieve events
        events = store.get_events(aggregate_id='123e4567-e89b-12d3-a456-426614174000')
        print("📝 Events:", len(events))
        
        regime_events = store.get_regime_events(symbol='GainX 600')
        print("📊 Regime Events:", len(regime_events))
        
        # Get regime statistics
        stats = store.get_regime_statistics('GainX 600', days=7)
        print("📈 Regime Statistics:", stats)
        
        # Reconstruct state
        state = store.reconstruct_state('123e4567-e89b-12d3-a456-426614174000')
        print("🔄 Reconstructed State:", state)
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        store.close()