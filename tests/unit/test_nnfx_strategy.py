# tests/unit/test_nnfx_strategy.py
import pytest
import pandas as pd
from src.strategy.nnfx_strategy import NNFXStrategy

@pytest.fixture
def strategy():
    return NNFXStrategy()

def test_hull_ma(strategy):
    data = pd.Series(range(100))
    hma = strategy.hull_moving_average(data, 10)
    assert len(hma) == len(data)

def test_generate_signal(strategy):
    df = pd.DataFrame({'close': range(100)})
    signal = strategy.generate_signal(df)
    assert signal in [-1, 0, 1]