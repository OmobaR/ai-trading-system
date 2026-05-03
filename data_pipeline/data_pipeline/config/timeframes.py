"""
Timeframe definitions with minute intervals for validation.
"""
from enum import Enum
from typing import Dict


class Timeframe(Enum):
    M1 = "M1"
    M2 = "M2"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


TIMEFRAME_INTERVALS: Dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M2: 2,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
    Timeframe.D1: 1440,
    Timeframe.W1: 10080,
    Timeframe.MN1: 43200,
}

TIMEFRAME_TABLES: Dict[Timeframe, str] = {
    Timeframe.M1: "ohlcv_m1",
    Timeframe.M2: "ohlcv_m2",
    Timeframe.M5: "ohlcv_m5",
    Timeframe.M15: "ohlcv_m15",
    Timeframe.H1: "ohlcv_h1",
    Timeframe.H4: "ohlcv_h4",
    Timeframe.D1: "ohlcv_d1",
    Timeframe.W1: "ohlcv_w1",
    Timeframe.MN1: "ohlcv_mn1",
}

CSV_SOURCE_TRUTH_TFS = [
    Timeframe.M5, Timeframe.M15, Timeframe.H1, 
    Timeframe.H4, Timeframe.D1, Timeframe.W1, Timeframe.MN1
]

DB_SOURCE_TFS = [Timeframe.M1, Timeframe.M2]


def get_interval_minutes(tf: Timeframe) -> int:
    return TIMEFRAME_INTERVALS[tf]


def get_table_name(tf: Timeframe) -> str:
    return TIMEFRAME_TABLES[tf]


def parse_timeframe(token: str) -> Timeframe:
    token = token.upper().strip()
    mapping = {
        "M1": Timeframe.M1, "M2": Timeframe.M2, "M5": Timeframe.M5,
        "M15": Timeframe.M15, "H1": Timeframe.H1, "H4": Timeframe.H4,
        "D1": Timeframe.D1, "D": Timeframe.D1,
        "W1": Timeframe.W1, "W": Timeframe.W1,
        "MN1": Timeframe.MN1, "MN": Timeframe.MN1, "MONTHLY": Timeframe.MN1,
    }
    if token not in mapping:
        raise ValueError(f"Unknown timeframe token: {token}")
    return mapping[token]
