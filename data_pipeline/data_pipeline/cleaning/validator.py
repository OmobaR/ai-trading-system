"""
Data quality validation engine.
Detects but does NOT silently fix anomalies.
"""
from typing import List, Tuple

import pandas as pd

from data_pipeline.config.settings import get_config
from data_pipeline.config.timeframes import Timeframe, get_interval_minutes
from data_pipeline.core.logger import get_logger
from data_pipeline.validation.schemas import TimeframeValidationReport

logger = get_logger("cleaning.validator")


class DataValidator:
    def __init__(self):
        self.config = get_config()

    def validate(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: Timeframe
    ) -> TimeframeValidationReport:
        if df.empty:
            return TimeframeValidationReport(
                symbol=symbol,
                timeframe=timeframe.value,
                row_count=0,
                integrity_score=0.0,
                passed=False,
                errors=["Empty dataset"]
            )

        df = df.copy()
        if "time" in df.columns:
            df.set_index("time", inplace=True)

        report = TimeframeValidationReport(
            symbol=symbol,
            timeframe=timeframe.value,
            row_count=len(df),
            start_date=df.index.min(),
            end_date=df.index.max()
        )

        report.non_monotonic = self._check_monotonic(df)
        report.duplicates = self._check_duplicates(df)
        report.duplicates_pct = report.duplicates / len(df) if len(df) > 0 else 0
        report.irregular_timestamps = self._check_irregular_intervals(df, timeframe)
        report.missing_candles, report.largest_gap_minutes, report.avg_gap_minutes =             self._check_missing_candles(df, timeframe)
        report.missing_candles_pct = report.missing_candles / len(df) if len(df) > 0 else 0
        report.ohlc_violations = self._check_ohlc_logic(df)
        report.negative_prices, report.negative_volume = self._check_negative_values(df)

        self._build_messages(report)
        report.integrity_score = self._calculate_integrity_score(report)
        report.passed = self._determine_pass(report)

        if not report.passed:
            logger.log_anomaly(symbol, timeframe.value, "VALIDATION_FAILED", {
                "integrity_score": report.integrity_score,
                "errors": report.errors
            })

        return report

    def _check_monotonic(self, df: pd.DataFrame) -> int:
        if df.index.is_monotonic_increasing:
            return 0
        diffs = df.index.to_series().diff().dt.total_seconds()
        return int((diffs < 0).sum())

    def _check_duplicates(self, df: pd.DataFrame) -> int:
        return int(df.index.duplicated().sum())

    def _check_irregular_intervals(self, df: pd.DataFrame, tf: Timeframe) -> int:
        expected_min = get_interval_minutes(tf)

        if expected_min >= 60:
            minutes = df.index.minute
            hours = df.index.hour

            if tf == Timeframe.H1:
                return int((minutes != 0).sum())
            elif tf == Timeframe.H4:
                return int(((minutes != 0) | (hours % 4 != 0)).sum())
            elif tf == Timeframe.D1:
                return int(((minutes != 0) | (df.index.hour != 0)).sum())
            return 0

        diffs = df.index.to_series().diff().dt.total_seconds().div(60).dropna()
        tolerance = 0.1
        expected = get_interval_minutes(tf)
        return int(((diffs < expected - tolerance) & (diffs > 0)).sum())

    def _check_missing_candles(
        self, 
        df: pd.DataFrame, 
        tf: Timeframe
    ) -> Tuple[int, float, float]:
        if len(df) < 2:
            return 0, 0.0, 0.0

        expected_interval = get_interval_minutes(tf)
        total_minutes = (df.index.max() - df.index.min()).total_seconds() / 60
        expected_count = int(total_minutes / expected_interval) + 1
        missing = max(0, expected_count - len(df))

        diffs = df.index.to_series().diff().dt.total_seconds().div(60).dropna()
        gaps = diffs[diffs > expected_interval * 1.5]

        largest_gap = float(gaps.max()) if len(gaps) > 0 else 0.0
        avg_gap = float(gaps.mean()) if len(gaps) > 0 else 0.0

        return missing, largest_gap, avg_gap

    def _check_ohlc_logic(self, df: pd.DataFrame) -> int:
        violations = 0
        violations += (df["high"] < df["low"]).sum()
        violations += (df["high"] < df[["open", "close"]].max(axis=1)).sum()
        violations += (df["low"] > df[["open", "close"]].min(axis=1)).sum()
        return int(violations)

    def _check_negative_values(self, df: pd.DataFrame) -> Tuple[int, int]:
        price_cols = ["open", "high", "low", "close"]
        neg_prices = (df[price_cols] < 0).any(axis=1).sum()
        neg_volume = (df["volume"] < 0).sum()
        return int(neg_prices), int(neg_volume)

    def _build_messages(self, report: TimeframeValidationReport):
        cfg = self.config

        if report.duplicates_pct > cfg.max_duplicate_pct:
            report.errors.append(
                f"Duplicate rate {report.duplicates_pct:.2%} exceeds threshold {cfg.max_duplicate_pct:.2%}"
            )
        elif report.duplicates > 0:
            report.warnings.append(f"Found {report.duplicates} duplicate rows")

        if report.missing_candles_pct > cfg.max_missing_pct:
            report.errors.append(
                f"Missing candle rate {report.missing_candles_pct:.2%} exceeds threshold {cfg.max_missing_pct:.2%}"
            )
        elif report.missing_candles > 0:
            report.warnings.append(
                f"Found {report.missing_candles} missing candles (largest gap: {report.largest_gap_minutes:.1f}min)"
            )

        if report.non_monotonic > 0:
            report.errors.append(f"Non-monotonic ordering: {report.non_monotonic} violations")

        if report.irregular_timestamps > 0:
            report.warnings.append(f"Found {report.irregular_timestamps} irregular timestamps")

        if report.ohlc_violations > 0:
            report.errors.append(f"OHLC logic violations: {report.ohlc_violations}")

        if report.negative_prices > 0:
            report.errors.append(f"Negative prices detected: {report.negative_prices}")

        if report.negative_volume > 0:
            report.warnings.append(f"Negative volume detected: {report.negative_volume}")

    def _calculate_integrity_score(self, report: TimeframeValidationReport) -> float:
        if report.row_count == 0:
            return 0.0

        dup_score = max(0, 1 - report.duplicates_pct * 100)
        miss_score = max(0, 1 - report.missing_candles_pct * 50)
        order_score = 1.0 if report.non_monotonic == 0 else max(0, 1 - report.non_monotonic / report.row_count)
        ohlc_score = 1.0 if report.ohlc_violations == 0 else max(0, 1 - report.ohlc_violations / report.row_count)

        return round(dup_score * 0.2 + miss_score * 0.3 + order_score * 0.2 + ohlc_score * 0.3, 4)

    def _determine_pass(self, report: TimeframeValidationReport) -> bool:
        cfg = self.config
        return (
            report.integrity_score >= 0.95 and
            report.duplicates_pct <= cfg.max_duplicate_pct and
            report.missing_candles_pct <= cfg.max_missing_pct and
            report.non_monotonic == 0 and
            report.ohlc_violations == 0 and
            report.negative_prices == 0
        )
