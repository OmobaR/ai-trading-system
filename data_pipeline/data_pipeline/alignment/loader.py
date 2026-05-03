"""
Replacement for existing resampling loader.
Pulls directly from timeframe-specific tables, no resampling.
"""
from typing import Dict, List, Optional

import pandas as pd

from data_pipeline.alignment.engine import AlignmentEngine
from data_pipeline.config.settings import get_config
from data_pipeline.config.timeframes import Timeframe
from data_pipeline.core.database import read_timeframe_to_dataframe
from data_pipeline.core.logger import get_logger
from data_pipeline.export.parquet_writer import ParquetWriter

logger = get_logger("alignment.loader")


class MultiTimeframeLoader:
    REGIME_TIMEFRAMES = [Timeframe.MN1, Timeframe.W1, Timeframe.D1, Timeframe.H4]
    FEATURE_TIMEFRAMES = [Timeframe.M1, Timeframe.M2, Timeframe.H1]

    def __init__(self, base_tf: Optional[Timeframe] = None):
        self.config = get_config()
        self.base_tf = base_tf or Timeframe(self.config.base_timeframe)
        self.alignment_engine = AlignmentEngine(self.base_tf)
        self.parquet_writer = ParquetWriter()

    def load_symbol(
        self,
        symbol: str,
        timeframes: Optional[List[Timeframe]] = None,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
        use_parquet: bool = True
    ) -> Dict[Timeframe, pd.DataFrame]:
        if timeframes is None:
            timeframes = list(Timeframe)

        results = {}

        for tf in timeframes:
            df = self._load_single_timeframe(symbol, tf, start, end, use_parquet)
            if not df.empty:
                results[tf] = df
            else:
                logger.warning(f"No data found for {symbol} {tf.value}")

        return results

    def _load_single_timeframe(
        self,
        symbol: str,
        tf: Timeframe,
        start: Optional[pd.Timestamp],
        end: Optional[pd.Timestamp],
        use_parquet: bool
    ) -> pd.DataFrame:
        if use_parquet:
            try:
                df = self.parquet_writer.read_timeframe(symbol, tf.value)

                if start is not None:
                    df = df[df.index >= start]
                if end is not None:
                    df = df[df.index <= end]

                logger.debug(f"Loaded {symbol} {tf.value} from Parquet: {len(df)} rows")
                return df
            except FileNotFoundError:
                logger.debug(f"Parquet not found for {symbol} {tf.value}, falling back to DB")

        df = read_timeframe_to_dataframe(symbol, tf, start, end)
        logger.info(f"Loaded {symbol} {tf.value} from DB: {len(df)} rows")
        return df

    def load_aligned(
        self,
        symbol: str,
        timeframes: Optional[List[Timeframe]] = None,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
        cache: bool = True
    ) -> pd.DataFrame:
        if cache:
            try:
                aligned = self.parquet_writer.read_aligned(symbol)

                if start is not None:
                    aligned = aligned[aligned.index >= start]
                if end is not None:
                    aligned = aligned[aligned.index <= end]

                logger.info(f"Loaded aligned dataset from cache for {symbol}: {len(aligned)} rows")
                return aligned
            except FileNotFoundError:
                pass

        all_data = self.load_symbol(symbol, timeframes, start, end, use_parquet=True)

        if self.base_tf not in all_data:
            raise ValueError(f"Base timeframe {self.base_tf.value} not available for {symbol}")

        base_df = all_data.pop(self.base_tf)
        higher_dfs = {tf: df for tf, df in all_data.items() if tf != self.base_tf}

        aligned = self.alignment_engine.align_timeframes(base_df, higher_dfs, symbol)

        if cache:
            self.parquet_writer.write_aligned(aligned, symbol)

        return aligned

    def get_available_symbols(self) -> List[str]:
        from data_pipeline.core.database import get_distinct_symbols
        return get_distinct_symbols(self.base_tf)
