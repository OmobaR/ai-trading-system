# tests/unit/test_risk_manager.py
import pytest
from src.risk.risk_manager import RiskManagerAgent

@pytest.fixture
def rma():
    return RiskManagerAgent({'host': 'localhost', 'port': 6379, 'db': 0})

def test_position_size(rma):
    size = rma.calculate_position_size('TEST', k=2.0)
    assert size > 0

def test_circuit_breakers(rma):
    rma.current_dd = 0.06
    size = rma.check_circuit_breakers(1.0)
    assert size == 0.75