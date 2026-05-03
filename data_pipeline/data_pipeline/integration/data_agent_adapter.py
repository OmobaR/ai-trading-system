"""
Drop-in replacement adapter for existing DataAgent.
Maintains backward compatibility while using new pipeline.
"""
from typing import Dict, List, Optional

import pandas as pd

from data_pipeline.alignment.loader import MultiTimeframeLoader
from data_pipeline.config.settings import get_config
from data_pipeline.config.timeframes import Timeframe
from data_pipeline.core.logger import get_logger

logger = get_logger("integration.data_agent")


class DataAgentAdapter:
    def __init__(self):
        self.loader = MultiTimeframeLoader()
        self.config = get_config()

    def load_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> pd.DataFrame:
        tf = Timeframe(timeframe.upper())
        start_ts = pd.Timestamp(start) if start else None
        end_ts = pd.Timestamp(end) if end else None

        data = self.loader.load_symbol(
            symbol, 
            timeframes=[tf],
            start=start_ts,
            end=end_ts,
            use_parquet=True
        )

        return data.get(tf, pd.DataFrame())

    def load_multi_timeframe(
        self,
        symbol: str,
        timeframes: List[str],
        align: bool = True
    ) -> pd.DataFrame:
        tfs = [Timeframe(tf.upper()) for tf in timeframes]

        if align:
            return self.loader.load_aligned(symbol, timeframes=tfs)
        else:
            return self.loader.load_symbol(symbol, timeframes=tfs)

    def get_available_data(self) -> Dict[str, List[str]]:
        symbols = self.loader.get_available_symbols()
        result = {}

        for sym in symbols:
            tfs = []
            for tf in Timeframe:
                try:
                    df = self.loader._load_single_timeframe(sym, tf, None, None, True)
                    if not df.empty:
                        tfs.append(tf.value)
                except Exception:
                    continue
            if tfs:
                result[sym] = tfs

        return result


_adapter: Optional[DataAgentAdapter] = None


def get_adapter() -> DataAgentAdapter:
    global _adapter
    if _adapter is None:
        _adapter = DataAgentAdapter()
    return _adapter
