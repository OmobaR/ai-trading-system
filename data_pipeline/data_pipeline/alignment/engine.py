"""
Multi-timeframe alignment engine.
NO RESAMPLING. NO LOOKAHEAD BIAS.
"""
from typing import Dict, List, Optional, Tuple

import pandas as pd

from data_pipeline.config.settings import get_config
from data_pipeline.config.timeframes import Timeframe, get_interval_minutes
from data_pipeline.core.exceptions import AlignmentError
from data_pipeline.core.logger import get_logger

logger = get_logger("alignment.engine")


class AlignmentEngine:
    """
    Aligns multiple timeframes to a base timeframe index using safe forward-fill.

    CRITICAL PRINCIPLE: Higher timeframe data is ONLY valid AFTER the candle closes.
    Therefore, at base-timeframe timestamp T, the available higher-TF data is the 
    most recently COMPLETED higher-TF candle.
    """

    def __init__(self, base_tf: Optional[Timeframe] = None):
        self.config = get_config()
        self.base_tf = base_tf or Timeframe(self.config.base_timeframe)
        self.base_interval_min = get_interval_minutes(self.base_tf)

    def align_timeframes(
        self,
        base_df: pd.DataFrame,
        higher_dfs: Dict[Timeframe, pd.DataFrame],
        symbol: str
    ) -> pd.DataFrame:
        if base_df.empty:
            raise AlignmentError("Base dataframe is empty")

        logger.info(f"Aligning {len(higher_dfs)} timeframes to {self.base_tf.value} for {symbol}")

        base = base_df.copy().sort_index()
        base = base[~base.index.duplicated(keep="first")]

        result = base.copy()
        result.columns = [f"base_{c}" for c in result.columns]

        for tf, df in higher_dfs.items():
            if df.empty:
                logger.warning(f"{symbol}: Empty dataframe for {tf.value}, skipping")
                continue

            aligned = self._align_single_timeframe(base.index, df, tf, symbol)
            aligned.columns = [f"{tf.value.lower()}_{c}" for c in aligned.columns]
            result = result.join(aligned, how="left")

            logger.info(
                f"{symbol}: Aligned {tf.value} - "
                f"{aligned.notna().all(axis=1).sum()} valid rows"
            )

        result = result.ffill()

        total_rows = len(result)
        for col in result.columns:
            if not col.startswith("base_"):
                valid = result[col].notna().sum()
                logger.info(f"{symbol}: {col} coverage = {valid}/{total_rows} ({valid/total_rows:.1%})")

        return result

    def _align_single_timeframe(
        self,
        base_index: pd.DatetimeIndex,
        higher_df: pd.DataFrame,
        tf: Timeframe,
        symbol: str
    ) -> pd.DataFrame:
        higher = higher_df.copy().sort_index()
        higher = higher[~higher.index.duplicated(keep="first")]

        self._validate_alignment(higher.index, tf, symbol)

        aligned = higher.reindex(base_index, method="ffill")
        return aligned

    def _validate_alignment(self, index: pd.DatetimeIndex, tf: Timeframe, symbol: str):
        if tf == Timeframe.H1:
            misaligned = (index.minute != 0).sum()
        elif tf == Timeframe.H4:
            misaligned = ((index.minute != 0) | (index.hour % 4 != 0)).sum()
        elif tf == Timeframe.D1:
            misaligned = ((index.minute != 0) | (index.hour != 0)).sum()
        else:
            misaligned = 0

        if misaligned > 0:
            logger.warning(
                f"{symbol}: {tf.value} has {misaligned} misaligned timestamps. "
                "This may indicate data quality issues."
            )
