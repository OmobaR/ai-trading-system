"""
Validation report persistence to JSON and database.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from data_pipeline.config.settings import get_config
from data_pipeline.core.database import get_engine
from data_pipeline.core.logger import get_logger
from data_pipeline.validation.schemas import (
    PipelineValidationReport, SymbolValidationSummary, TimeframeValidationReport
)

logger = get_logger("validation.reporter")


class ValidationReporter:
    def __init__(self):
        self.config = get_config()
        self.report_dir = self.config.report_dir

    def save_json(self, report: PipelineValidationReport, filename: Optional[str] = None):
        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"validation_report_{timestamp}.json"

        path = self.report_dir / filename
        with open(path, "w") as f:
            json.dump(report.model_dump(), f, indent=2, default=str)

        logger.info(f"Validation report saved to {path}")
        return path

    def save_to_database(self, report: PipelineValidationReport):
        engine = get_engine()

        create_table_sql = """
        CREATE TABLE IF NOT EXISTS data_validation_reports (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(50) NOT NULL,
            timeframe VARCHAR(10) NOT NULL,
            row_count INTEGER,
            start_date TIMESTAMPTZ,
            end_date TIMESTAMPTZ,
            missing_candles INTEGER,
            missing_candles_pct FLOAT,
            duplicates INTEGER,
            duplicates_pct FLOAT,
            irregular_timestamps INTEGER,
            non_monotonic INTEGER,
            largest_gap_minutes FLOAT,
            avg_gap_minutes FLOAT,
            ohlc_violations INTEGER,
            negative_prices INTEGER,
            negative_volume INTEGER,
            integrity_score FLOAT,
            passed BOOLEAN,
            warnings TEXT[],
            errors TEXT[],
            processed_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(symbol, timeframe, processed_at)
        );
        """

        with engine.connect() as conn:
            conn.execute(text(create_table_sql))

            records = []
            for sym_summary in report.symbols.values():
                for tf_report in sym_summary.timeframes.values():
                    records.append({
                        "symbol": tf_report.symbol,
                        "timeframe": tf_report.timeframe,
                        "row_count": tf_report.row_count,
                        "start_date": tf_report.start_date,
                        "end_date": tf_report.end_date,
                        "missing_candles": tf_report.missing_candles,
                        "missing_candles_pct": tf_report.missing_candles_pct,
                        "duplicates": tf_report.duplicates,
                        "duplicates_pct": tf_report.duplicates_pct,
                        "irregular_timestamps": tf_report.irregular_timestamps,
                        "non_monotonic": tf_report.non_monotonic,
                        "largest_gap_minutes": tf_report.largest_gap_minutes,
                        "avg_gap_minutes": tf_report.avg_gap_minutes,
                        "ohlc_violations": tf_report.ohlc_violations,
                        "negative_prices": tf_report.negative_prices,
                        "negative_volume": tf_report.negative_volume,
                        "integrity_score": tf_report.integrity_score,
                        "passed": tf_report.passed,
                        "warnings": tf_report.warnings,
                        "errors": tf_report.errors,
                        "processed_at": tf_report.processed_at
                    })

            if records:
                df = pd.DataFrame(records)
                df.to_sql("data_validation_reports", engine, 
                         if_exists="append", index=False, method="multi")
                logger.info(f"Saved {len(records)} validation records to database")

    def load_latest_report(self, symbol: str, timeframe: str) -> Optional[TimeframeValidationReport]:
        engine = get_engine()
        query = """
            SELECT * FROM data_validation_reports
            WHERE symbol = %s AND timeframe = %s
            ORDER BY processed_at DESC
            LIMIT 1
        """
        df = pd.read_sql(query, engine, params=(symbol, timeframe))

        if df.empty:
            return None

        row = df.iloc[0]
        return TimeframeValidationReport(**row.to_dict())
