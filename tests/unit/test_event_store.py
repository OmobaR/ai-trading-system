# tests/unit/test_event_store.py
import pytest
from src.events.event_store import EventStore
import uuid

@pytest.fixture
def store():
    db_config = {'dbname': 'trading_system', 'user': 'user', 'password': 'password', 'host': 'localhost', 'port': 5432}
    s = EventStore(db_config)
    yield s
    s.close()

def test_create_schema(store):
    store.create_schema()  # Should succeed without error

def test_append_and_get(store):
    agg_id = uuid.uuid4()
    store.append_event('test_event', agg_id, {'key': 'value'}, version=1)
    events = store.get_events(aggregate_id=agg_id)
    assert len(events) == 1
    assert events[0][1] == 'test_event'

def test_reconstruct_state(store):
    agg_id = uuid.uuid4()
    store.append_event('signal_generated', agg_id, {'signal': 'buy'}, version=1)
    state = store.reconstruct_state(agg_id)
    assert state['signal'] == {'signal': 'buy'}

# Add more tests for performance (e.g., time 1000 appends) and integration