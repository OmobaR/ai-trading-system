"""
SQLAlchemy models and TimescaleDB utilities.
Compatible with existing connection logic.
"""
from contextlib import contextmanager
from typing import Generator, List

import pandas as pd
from sqlalchemy import (
    Column, DateTime, Float, String, create_engine, text, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker

from data_pipeline.config.settings import get_config
from data_pipeline.config.timeframes import Timeframe, get_table_name
from data_pipeline.core.logger import get_logger

logger = get_logger("database")
Base = declarative_base()


def get_engine():
    config = get_config()
    return create_engine(config.db_uri, isolation_level=config.db_isolation_level)


def get_session_factory():
    return sessionmaker(bind=get_engine())


@contextmanager
def get_session() -> Generator:
    Session = get_session_factory()
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_connection() -> Generator:
    engine = get_engine()
    conn = engine.raw_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_ohlcv_model(table_name: str):
    class OHLCV(Base):
        __tablename__ = table_name
        __table_args__ = (
            UniqueConstraint("time", "symbol", name=f"{table_name}_pk"),
            {"extend_existing": True}
        )

        time = Column(DateTime(timezone=True), primary_key=True, nullable=False)
        symbol = Column(String(50), primary_key=True, nullable=False)
        open = Column(Float, nullable=False)
        high = Column(Float, nullable=False)
        low = Column(Float, nullable=False)
        close = Column(Float, nullable=False)
        volume = Column(Float, nullable=False)

        def __repr__(self):
            return f"<OHLCV({self.symbol}, {self.time})>"

    OHLCV.__name__ = f"OHLCV_{table_name}"
    return OHLCV


OHLCV_MODELS = {
    tf: create_ohlcv_model(get_table_name(tf))
    for tf in Timeframe
}


def create_hypertable(tf: Timeframe):
    table_name = get_table_name(tf)
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{table_name}'
            );
        """))
        exists = result.scalar()

        if not exists:
            model = OHLCV_MODELS[tf]
            model.__table__.create(engine)

            conn.execute(text(f"""
                SELECT create_hypertable('{table_name}', 'time', 
                    if_not_exists => TRUE, 
                    chunk_time_interval => INTERVAL '1 day');
            """))
            logger.info(f"Created hypertable: {table_name}")
        else:
            logger.info(f"Hypertable already exists: {table_name}")


def create_all_hypertables():
    for tf in Timeframe:
        create_hypertable(tf)


def bulk_insert_dataframe(df: pd.DataFrame, tf: Timeframe):
    if df.empty:
        return 0

    table_name = get_table_name(tf)
    required = ["time", "symbol", "open", "high", "low", "close", "volume"]
    df = df[required].copy()

    engine = get_engine()
    df.to_sql(
        table_name, engine, if_exists="append", 
        index=False, method="multi", chunksize=10000
    )

    return len(df)


def read_timeframe_to_dataframe(
    symbol: str, 
    tf: Timeframe, 
    start: pd.Timestamp = None,
    end: pd.Timestamp = None
) -> pd.DataFrame:
    table_name = get_table_name(tf)
    engine = get_engine()

    query = f"""
        SELECT time, symbol, open, high, low, close, volume
        FROM {table_name}
        WHERE symbol = :symbol
    """
    params = {"symbol": symbol}

    if start is not None:
        query += " AND time >= :start"
        params["start"] = start
    if end is not None:
        query += " AND time <= :end"
        params["end"] = end

    query += " ORDER BY time ASC"

    df = pd.read_sql(query, engine, params=params, parse_dates=["time"])

    if not df.empty:
        df.set_index("time", inplace=True)

    return df


def get_distinct_symbols(tf: Timeframe) -> List[str]:
    table_name = get_table_name(tf)
    engine = get_engine()

    query = f"SELECT DISTINCT symbol FROM {table_name} ORDER BY symbol"
    df = pd.read_sql(query, engine)
    return df["symbol"].tolist() if not df.empty else []
