"""
M1/M2 extraction from existing TimescaleDB with validation.
RECOMMENDATION: Re-ingest M1/M2 from MT5 CSV for maximum reliability.
"""
from typing import Optional

import pandas as pd

from data_pipeline.config.settings import get_config
from data_pipeline.config.timeframes import Timeframe
from data_pipeline.core.database import read_timeframe_to_dataframe
from data_pipeline.core.exceptions import DataContaminationError
from data_pipeline.core.logger import get_logger

logger = get_logger("ingestion.db")


class M1M2Extractor:
    def __init__(self):
        self.config = get_config()

    def extract_from_mixed_table(
        self, 
        symbol: str,
        expected_tf: Timeframe = Timeframe.M1
    ) -> pd.DataFrame:
        from data_pipeline.core.database import get_engine
        engine = get_engine()

        logger.warning(
            f"Extracting {expected_tf.value} for {symbol} from mixed table. "
            "This is UNRELIABLE. Recommend re-ingestion from MT5 CSV."
        )

        query = """
            SELECT time, symbol, open, high, low, close, volume
            FROM ohlcv_data
            WHERE symbol = :symbol
            ORDER BY time ASC
        """

        df = pd.read_sql(query, engine, params={"symbol": symbol}, parse_dates=["time"])

        if df.empty:
            logger.error(f"No data found for {symbol} in ohlcv_data")
            return df

        df.set_index("time", inplace=True)

        intervals = df.index.to_series().diff().dt.total_seconds().div(60).dropna()
        median_interval = intervals.median()

        expected_minutes = {
            Timeframe.M1: 1,
            Timeframe.M2: 2
        }.get(expected_tf, 1)

        if abs(median_interval - expected_minutes) < 0.5:
            logger.info(f"{symbol}: Detected consistent {median_interval:.1f}min intervals")

            wrong_intervals = intervals[
                (intervals < expected_minutes * 0.5) | 
                (intervals > expected_minutes * 2)
            ]
            if len(wrong_intervals) > len(intervals) * 0.05:
                logger.error(
                    f"{symbol}: Table appears contaminated with mixed timeframes. "
                    f"Found {len(wrong_intervals)} anomalous intervals. "
                    "MUST re-ingest from MT5 CSV."
                )
                raise DataContaminationError(
                    f"Mixed timeframe contamination detected for {symbol}"
                )
        else:
            logger.error(
                f"{symbol}: Median interval is {median_interval:.1f}min, "
                f"expected {expected_minutes}min. Table contains wrong timeframe data."
            )
            raise DataContaminationError(
                f"Expected {expected_tf.value} but found {median_interval:.1f}min intervals"
            )

        return df

    def recommend_reingestion(self, symbol: str) -> str:
        msg = f"""
        RECOMMENDATION FOR {symbol} M1/M2:

        The existing ohlcv_data table mixes multiple timeframes without 
        a timeframe discriminator column. This is a FUNDAMENTAL design flaw 
        that makes reliable extraction impossible.

        ACTION REQUIRED:
        1. Export M1/M2 data directly from MT5 as CSV
        2. Place in: {self.config.csv_input_dir}
        3. Use naming convention: {{Symbol}}_M1.csv or {{Symbol}}_M2.csv
        4. Run CSV ingestion pipeline instead

        DO NOT use gap-based SQL extraction for production backtesting.
        Any resampling or gap-detection on mixed data produces 
        unreliable results and invalidates strategy correctness.
        """
        logger.info(msg)
        return msg


def extract_m1m2_with_fallback(
    symbol: str,
    prefer_csv: bool = True
) -> Optional[pd.DataFrame]:
    from data_pipeline.ingestion.csv_loader import scan_csv_directory, load_csv_file

    csv_files = scan_csv_directory()
    for info in csv_files:
        if info.symbol == symbol and info.timeframe in (Timeframe.M1, Timeframe.M2):
            logger.info(f"Found CSV for {symbol} {info.timeframe.value}, using as source of truth")
            return load_csv_file(info)

    if prefer_csv:
        logger.warning(f"No CSV found for {symbol} M1/M2. Attempting DB fallback (UNRELIABLE).")

    extractor = M1M2Extractor()
    try:
        return extractor.extract_from_mixed_table(symbol, Timeframe.M1)
    except DataContaminationError:
        extractor.recommend_reingestion(symbol)
        raise
