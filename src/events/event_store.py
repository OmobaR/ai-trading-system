# src/events/event_store.py
import psycopg2
from psycopg2 import sql
import json
from datetime import datetime
import logging

# Set up logging
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
            self.conn.autocommit = False  # For transactional integrity
            logger.info("Connected to PostgreSQL database")
        except psycopg2.Error as e:
            logger.error(f"Error connecting to PostgreSQL: {e}")
            raise

    def create_schema(self):
        try:
            with self.conn.cursor() as cur:
                # Create events table if not exists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id SERIAL PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        aggregate_id UUID NOT NULL,
                        data JSONB NOT NULL,
                        metadata JSONB NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        version INTEGER NOT NULL
                    );
                """)
                
                # Create index for efficient querying
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_events_aggregate_id ON events (aggregate_id);
                    CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp);
                    CREATE INDEX IF NOT EXISTS idx_events_event_type ON events (event_type);
                """)
                
                # Make it a TimescaleDB hypertable for time-series optimization
                cur.execute("""
                    SELECT create_hypertable('events', 'timestamp', if_not_exists => TRUE);
                """)
                
            self.conn.commit()
            logger.info("Event store schema created successfully")
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Error creating schema: {e}")
            raise

    def append_event(self, event_type, aggregate_id, data, metadata=None, version=None):
        if metadata is None:
            metadata = {}
        try:
            with self.conn.cursor() as cur:
                # Optional version check for optimistic concurrency
                if version is not None:
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
            logger.info(f"Appended event: {event_type} for aggregate {aggregate_id}")
        except (psycopg2.Error, ValueError) as e:
            self.conn.rollback()
            logger.error(f"Error appending event: {e}")
            raise

    def get_events(self, aggregate_id=None, event_type=None, start_time=None, end_time=None):
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
                
                query += sql.SQL(" ORDER BY timestamp ASC;")
                
                cur.execute(query, params)
                return cur.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Error retrieving events: {e}")
            raise

    def reconstruct_state(self, aggregate_id):
        events = self.get_events(aggregate_id=aggregate_id)
        state = {}  # Initial empty state
        for event in events:
            # Apply events to reconstruct state (domain-specific logic here)
            # Example: For trade lifecycle
            if event[1] == 'signal_generated':
                state['signal'] = event[3]  # data
            elif event[1] == 'order_placed':
                state['order'] = event[3]
            # ... extend for other event types
        return state

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

# Example usage (for testing)
if __name__ == "__main__":
    db_config = {
        'dbname': 'trading_system',
        'user': 'user',
        'password': 'password',
        'host': 'localhost',
        'port': 5432
    }
    store = EventStore(db_config)
    try:
        store.create_schema()
        # Append sample event
        store.append_event(
            event_type='signal_generated',
            aggregate_id='123e4567-e89b-12d3-a456-426614174000',
            data={'symbol': 'VIX75', 'action': 'buy', 'price': 100.5},
            metadata={'user': 'system'},
            version=1
        )
        events = store.get_events(aggregate_id='123e4567-e89b-12d3-a456-426614174000')
        print(events)
        state = store.reconstruct_state('123e4567-e89b-12d3-a456-426614174000')
        print(state)
    finally:
        store.close()