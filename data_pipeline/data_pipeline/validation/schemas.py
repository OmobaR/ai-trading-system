"""
Pydantic models for validation reporting.
"""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TimeframeValidationReport(BaseModel):
    symbol: str
    timeframe: str
    row_count: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    missing_candles: int = 0
    missing_candles_pct: float = 0.0
    duplicates: int = 0
    duplicates_pct: float = 0.0
    irregular_timestamps: int = 0
    non_monotonic: int = 0
    largest_gap_minutes: float = 0.0
    avg_gap_minutes: float = 0.0
    ohlc_violations: int = 0
    negative_prices: int = 0
    negative_volume: int = 0
    integrity_score: float = Field(..., ge=0.0, le=1.0)
    passed: bool = False
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    processed_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SymbolValidationSummary(BaseModel):
    symbol: str
    timeframes: Dict[str, TimeframeValidationReport]
    overall_integrity_score: float = 0.0
    overall_passed: bool = False


class PipelineValidationReport(BaseModel):
    symbols: Dict[str, SymbolValidationSummary]
    total_symbols: int = 0
    total_timeframes: int = 0
    passed_symbols: int = 0
    failed_symbols: int = 0
    generated_at: datetime = Field(default_factory=datetime.utcnow)
