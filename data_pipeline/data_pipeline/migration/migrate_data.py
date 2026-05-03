"""
Migration validation script.
Runs new pipeline alongside old, compares outputs.
"""
import pandas as pd

from data_pipeline.core.database import get_engine
from data_pipeline.core.logger import get_logger
from data_pipeline.pipeline import Phase1Pipeline

logger = get_logger("migration")


class MigrationValidator:
    def __init__(self):
        self.pipeline = Phase1Pipeline()

    def compare_symbol(self, symbol: str, timeframe: str = "M1"):
        engine = get_engine()

        old_query = """
            SELECT time, open, high, low, close, volume
            FROM ohlcv_data
            WHERE symbol = %s
            ORDER BY time
        """
        old_df = pd.read_sql(old_query, engine, params=(symbol,))

        from data_pipeline.config.timeframes import Timeframe, get_table_name
        table = get_table_name(Timeframe(timeframe))
        new_query = f"""
            SELECT time, open, high, low, close, volume
            FROM {table}
            WHERE symbol = %s
            ORDER BY time
        """
        new_df = pd.read_sql(new_query, engine, params=(symbol,))

        comparison = {
            "symbol": symbol,
            "timeframe": timeframe,
            "old_rows": len(old_df),
            "new_rows": len(new_df),
            "row_diff": len(new_df) - len(old_df),
            "old_start": old_df["time"].min() if not old_df.empty else None,
            "new_start": new_df["time"].min() if not new_df.empty else None,
            "old_end": old_df["time"].max() if not old_df.empty else None,
            "new_end": new_df["time"].max() if not new_df.empty else None,
        }

        logger.info(f"Migration comparison for {symbol} {timeframe}: {comparison}")
        return comparison

    def run_parallel_pipeline(self, symbols: list):
        logger.info("Running parallel pipeline validation...")

        report = self.pipeline.run_full_pipeline(
            symbols=symbols,
            skip_ingestion=False,
            skip_validation=False,
            skip_export=True
        )

        for symbol in symbols[:3]:
            for tf in ["M1", "H1", "D1"]:
                try:
                    self.compare_symbol(symbol, tf)
                except Exception as e:
                    logger.error(f"Comparison failed for {symbol} {tf}: {e}")

        logger.info("Parallel validation complete. Review logs before switching.")


if __name__ == "__main__":
    validator = MigrationValidator()
    validator.run_parallel_pipeline(["GainX 600", "PainX 1200"])
