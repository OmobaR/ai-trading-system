# tests/unit/test_market_data_agent.py
import pytest
from src.market_data.market_data_agent import MarketDataAgent
from datetime import datetime

@pytest.fixture
def agent():
    db_config = {'dbname': 'trading_system', 'user': 'user', 'password': 'password', 'host': 'localhost', 'port': 5432}
    redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
    a = MarketDataAgent(db_config, redis_config)
    yield a
    a.stop()

def test_validate_data(agent):
    valid_data = {'time': datetime.utcnow(), 'symbol': 'TEST', 'bid': 100, 'ask': 101}
    assert agent.validate_data(valid_data)
    
    invalid_data = {'time': datetime.utcnow(), 'symbol': 'TEST', 'bid': 101, 'ask': 100}
    with pytest.raises(ValueError):
        agent.validate_data(invalid_data)

def test_ingest_data(agent):
    data = {'time': datetime.utcnow(), 'symbol': 'TEST', 'bid': 100, 'ask': 101}
    agent.ingest_data(data)
    # Verify in DB (query manually or extend test)
    # Verify feature in Redis
    atr = agent.feature_store.get_feature('TEST', 'ATR')
    assert atr is not None