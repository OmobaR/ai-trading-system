"""
Main pipeline orchestrator.
Executes: INGEST → CLEAN → VALIDATE → ALIGN → EXPORT
"""
from typing import Dict, List, Optional

import pandas as pd

from data_pipeline.alignment.engine import AlignmentEngine
from data_pipeline.alignment.loader import MultiTimeframeLoader
from data_pipeline.cleaning.validator import DataValidator
from data_pipeline.config.settings import get_config
from data_pipeline.config.timeframes import (
    CSV_SOURCE_TRUTH_TFS, DB_SOURCE_TFS, Timeframe
)
from data_pipeline.core.database import (
    bulk_insert_dataframe, create_all_hypertables, get_distinct_symbols
)
from data_pipeline.core.logger import get_logger
from data_pipeline.export.parquet_writer import ParquetWriter
from data_pipeline.ingestion.csv_loader import load_all_csv_files
from data_pipeline.ingestion.db_extractor import extract_m1m2_with_fallback
from data_pipeline.validation.reporter import ValidationReporter
from data_pipeline.validation.schemas import (
    PipelineValidationReport, SymbolValidationSummary
)

logger = get_logger("pipeline")


class Phase1Pipeline:
    def __init__(self):
        self.config = get_config()
        self.validator = DataValidator()
        self.reporter = ValidationReporter()
        self.parquet_writer = ParquetWriter()
        self.alignment_engine = AlignmentEngine()

    def run_full_pipeline(
        self,
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[Timeframe]] = None,
        skip_ingestion: bool = False,
        skip_validation: bool = False,
        skip_export: bool = False
    ) -> PipelineValidationReport:
        logger.info("=" * 60)
        logger.info("PHASE 1 DATA PIPELINE STARTED")
        logger.info("=" * 60)

        logger.info("STEP 0: Creating hypertables...")
        create_all_hypertables()

        if not skip_ingestion:
            logger.info("STEP 1: Ingesting data...")
            self._run_ingestion(symbols, timeframes)

        validation_report = None
        if not skip_validation:
            logger.info("STEP 2: Validating data...")
            validation_report = self._run_validation(symbols, timeframes)

        if not skip_export:
            logger.info("STEP 3: Exporting timeframe Parquets...")
            self._run_export_timeframes(symbols, timeframes)

        if not skip_export:
            logger.info("STEP 4: Aligning and exporting multi-TF Parquets...")
            self._run_export_aligned(symbols)

        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 60)

        return validation_report or PipelineValidationReport(symbols={})

    def _run_ingestion(
        self,
        symbols: Optional[List[str]],
        timeframes: Optional[List[Timeframe]]
    ):
        csv_data = load_all_csv_files(timeframe_filter=timeframes)

        if symbols:
            csv_data = {k: v for k, v in csv_data.items() if k[0] in symbols}

        for (symbol, tf), df in csv_data.items():
            logger.info(f"Inserting {symbol} {tf.value} ({len(df)} rows) from CSV")
            bulk_insert_dataframe(df, tf)

        if timeframes is None or any(tf in timeframes for tf in DB_SOURCE_TFS):
            needed_symbols = symbols or self._infer_symbols_from_csv(csv_data)

            for symbol in needed_symbols:
                for tf in DB_SOURCE_TFS:
                    if timeframes and tf not in timeframes:
                        continue

                    try:
                        df = extract_m1m2_with_fallback(symbol, prefer_csv=True)
                        if df is not None and not df.empty:
                            logger.info(f"Inserting {symbol} {tf.value} ({len(df)} rows)")
                            bulk_insert_dataframe(df, tf)
                    except Exception as e:
                        logger.error(f"Failed to ingest {symbol} {tf.value}: {e}")

    def _run_validation(
        self,
        symbols: Optional[List[str]],
        timeframes: Optional[List[Timeframe]]
    ) -> PipelineValidationReport:
        all_symbols = symbols or []
        if not all_symbols:
            for tf in Timeframe:
                all_symbols.extend(get_distinct_symbols(tf))
            all_symbols = sorted(set(all_symbols))

        all_timeframes = timeframes or list(Timeframe)
        report = PipelineValidationReport(symbols={})

        for symbol in all_symbols:
            tf_reports = {}
            symbol_passed = True

            for tf in all_timeframes:
                from data_pipeline.core.database import read_timeframe_to_dataframe
                df = read_timeframe_to_dataframe(symbol, tf)

                if df.empty:
                    continue

                tf_report = self.validator.validate(df, symbol, tf)
                tf_reports[tf.value] = tf_report

                if not tf_report.passed:
                    symbol_passed = False

            if tf_reports:
                summary = SymbolValidationSummary(
                    symbol=symbol,
                    timeframes=tf_reports,
                    overall_integrity_score=sum(r.integrity_score for r in tf_reports.values()) / len(tf_reports),
                    overall_passed=symbol_passed
                )
                report.symbols[symbol] = summary

                if symbol_passed:
                    report.passed_symbols += 1
                else:
                    report.failed_symbols += 1

        report.total_symbols = len(report.symbols)
        report.total_timeframes = sum(len(s.timeframes) for s in report.symbols.values())

        self.reporter.save_json(report)
        self.reporter.save_to_database(report)

        logger.info(f"Validation complete: {report.passed_symbols} passed, {report.failed_symbols} failed")
        return report

    def _run_export_timeframes(
        self,
        symbols: Optional[List[str]],
        timeframes: Optional[List[Timeframe]]
    ):
        all_symbols = symbols or []
        if not all_symbols:
            for tf in Timeframe:
                all_symbols.extend(get_distinct_symbols(tf))
            all_symbols = sorted(set(all_symbols))

        all_timeframes = timeframes or list(Timeframe)

        for symbol in all_symbols:
            for tf in all_timeframes:
                from data_pipeline.core.database import read_timeframe_to_dataframe
                df = read_timeframe_to_dataframe(symbol, tf)

                if df.empty:
                    continue

                self.parquet_writer.write_timeframe(df, symbol, tf.value)

    def _run_export_aligned(self, symbols: Optional[List[str]]):
        loader = MultiTimeframeLoader()
        all_symbols = symbols or loader.get_available_symbols()

        for symbol in all_symbols:
            try:
                aligned = loader.load_aligned(symbol, cache=False)
                self.parquet_writer.write_aligned(aligned, symbol)
            except Exception as e:
                logger.error(f"Failed to align {symbol}: {e}")

    def _infer_symbols_from_csv(
        self, 
        csv_data: Dict[tuple, pd.DataFrame]
    ) -> List[str]:
        return sorted(set(sym for sym, _ in csv_data.keys()))


def run_pipeline(**kwargs) -> PipelineValidationReport:
    pipeline = Phase1Pipeline()
    return pipeline.run_full_pipeline(**kwargs)
