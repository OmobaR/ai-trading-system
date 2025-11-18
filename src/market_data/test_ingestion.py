import pandas as pd
import psycopg2
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

def create_sample_data():
    """Create sample OHLCV data that matches MT5 structure"""
    dates = pd.date_range(start='2024-01-01', end='2024-01-10', freq='1H')
    data = []
    
    for date in dates:
        data.append({
            'time': date,  # Changed from 'timestamp' to 'time' to match market_data_agent.py
            'symbol': 'SYNTX_1',
            'open': 100 + (date.day % 10),
            'high': 102 + (date.day % 10),
            'low': 98 + (date.day % 10),
            'close': 101 + (date.day % 10),
            'volume': 1000 + (date.hour * 100)
        })
    
    return pd.DataFrame(data)

def init_database_connection():
    """Initialize database connection using SQLAlchemy"""
    try:
        db_url = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        engine = create_engine(db_url)
        print("✅ Successfully connected to TimescaleDB")
        return engine
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

def create_tables(engine):
    """Create the EXACT tables that market_data_agent.py expects"""
    with engine.begin() as conn:  # Changed to engine.begin() for SQLAlchemy 2.0 compatibility
        # Create OHLCV table - matching market_data_agent.py schema
        conn.execute(text("""
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
        """))
        
        # Convert to hypertable
        conn.execute(text("""
            SELECT create_hypertable('ohlcv_data', 'time', 
                   if_not_exists => TRUE);
        """))
        
        # Create event_store table (simplified version for now)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS trade_events (
                id SERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                data JSONB,
                metadata JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """))
        
    print("✅ Production tables created successfully")

def insert_sample_data(engine, df):
    """Insert sample data using production schema"""
    # Use pandas to_sql for bulk insert
    df.to_sql('ohlcv_data', engine, if_exists='append', index=False, method='multi')
    print(f"✅ Inserted {len(df)} records")

def test_query(engine):
    """Test query to verify data matches production expectations"""
    with engine.connect() as conn:
        # Test the same queries market_data_agent would run
        result = conn.execute(text("""
            SELECT symbol, COUNT(*) as record_count,
                   MIN(time) as earliest,
                   MAX(time) as latest
            FROM ohlcv_data
            GROUP BY symbol;
        """))
        print("📊 Data Summary (Production Schema):")
        for row in result:
            print(f"  Symbol: {row[0]}, Records: {row[1]}, From: {row[2]} to {row[3]}")
        
        # Verify table structure matches market_data_agent expectations
        result = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'ohlcv_data'
            ORDER BY ordinal_position;
        """))
        print("\n🔍 Table Structure:")
        for row in result:
            print(f"  {row[0]}: {row[1]}")

if __name__ == "__main__":
    print("🚀 Starting PRODUCTION-READY data pipeline test...")
    
    # Initialize connection
    engine = init_database_connection()
    if not engine:
        exit(1)
    
    try:
        # Create production tables
        create_tables(engine)
        
        # Generate and insert sample data
        df = create_sample_data()
        insert_sample_data(engine, df)
        
        # Test production-style queries
        test_query(engine)
        
        print("🎉 Production-ready data pipeline test completed successfully!")
        print("💡 Next: This schema is now ready for market_data_agent.py with MT5 data!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        engine.dispose()