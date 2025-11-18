# tests/unit/test_redis_feature_store.py
import pytest
from src.database.redis_feature_store import FeatureStore

@pytest.fixture
def store():
    redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
    s = FeatureStore(redis_config)
    yield s
    s.client.flushdb()  # Clean up

def test_set_get_feature(store):
    store.set_feature('TEST', 'ATR', 1.23)
    value = store.get_feature('TEST', 'ATR')
    assert value == 1.23

def test_get_all_features(store):
    store.set_feature('TEST', 'ATR', 1.23)
    store.set_feature('TEST', 'HMM', {'prob': 0.8})
    features = store.get_all_features('TEST')
    assert features['ATR'] == 1.23
    assert features['HMM'] == {'prob': 0.8}