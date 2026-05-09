"""
Data Agent (Phase 1)
Loads real OHLCV data from TimescaleDB.
Standardizes and validates DataFrame.
"""
from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

import pandas as pd
import numpy as np
from sqlalchemy import create_engine

from core.base_agent import BaseAgent, AgentResult
from core.state_store import StateStore
from core.message_bus import MessageBus
from src.config.settings import config

logger = logging.getLogger(__name__)

# Default symbols – you can import from config.SYMBOLS if preferred
DEFAULT_SYMBOLS = [
    "GainX 400", "GainX 600", "GainX 800", "GainX 999", "GainX 1200",
    "PainX 400", "PainX 600", "PainX 800", "PainX 999", "PainX 1200",
    "FlipX 1", "FlipX 2", "FlipX 3", "FlipX 4", "FlipX 5",
    "FX Vol 20", "FX Vol 40", "FX Vol 60", "FX Vol 80", "FX Vol 99",
    "SFX Vol 20", "SFX Vol 40", "SFX Vol 60", "SFX Vol 80", "SFX Vol 99",
    "TrendX 600", "TrendX 1200", "TrendX 1800",
    "SwitchX 600", "SwitchX 1200", "SwitchX 1800",
    "BreakX 600", "BreakX 1200", "BreakX 1800",
    "PlusX 1", "QuadX", "FiboX" # <-- newly added
]

class DataAgent(BaseAgent):
    """
    Owns the constraint: DATA INTEGRITY and STANDARDIZATION.
    - Loads real data from TimescaleDB
    - Validates OHLCV schema
    - Enforces chronological ordering
    - Drops duplicates / invalid rows
    - Outputs clean DataFrame with consistent dtypes
    """

    def __init__(self, state_store: StateStore, message_bus: MessageBus):
        super().__init__("data_agent", state_store, message_bus)
        self.required_columns = ["time", "symbol", "open", "high", "low", "close", "volume"]

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        """
        Load data from TimescaleDB. Parameters:
        - symbols: list of str
        - timeframe: str, e.g. 'M5', 'H1' (default 'M5')
        - days: int, how many past days to load (default 500)
        """
        logger.info("[DataAgent] Starting data preparation from local TimescaleDB...")

        try:
            symbols = kwargs.get("symbols", DEFAULT_SYMBOLS)
            timeframe = kwargs.get("timeframe", "M5")
            days = kwargs.get("days", 500)

            df = self._load_from_db(symbols, timeframe, days)
            if df.empty:
                raise ValueError(f"No data found for symbols {symbols} in {timeframe}")

            # Standardize
            clean_df = self._standardize(df)

            # Validate
            validation = self._validate(clean_df)
            if not validation["passed"]:
                return AgentResult(
                    success=False,
                    message=f"Data validation failed: {validation['errors']}",
                    diagnostics=validation,
                    halt_pipeline=True,
                )

            artifact_id = self._produce_artifact(
                name="clean_ohlcv_dataset",
                data=clean_df,
                phase="data",
                tags=["ohlcv", "clean", timeframe],
                notes=f"Symbols: {clean_df['symbol'].nunique()}, Rows: {len(clean_df)}, Timeframe: {timeframe}, Days: {days}",
            )

            return AgentResult(
                success=True,
                artifact_id=artifact_id,
                message=f"Loaded {len(clean_df)} rows from {timeframe}",
                diagnostics=validation,
            )

        except Exception as e:
            logger.exception("[DataAgent] Fatal error during execution")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _load_from_db(self, symbols, timeframe='M5', days=500):
        from sqlalchemy import create_engine
        from src.config.settings import config
        db_uri = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        engine = create_engine(db_uri)
        table = f"ohlcv_{timeframe.lower()}"
        query = f"""
            SELECT time, symbol, open, high, low, close, volume 
            FROM {table} 
            WHERE symbol = ANY(%s) 
            AND time > NOW() - INTERVAL '%s days'
            AND open > 0 AND high > 0 AND low > 0 AND close > 0
            ORDER BY time
        """
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params=(symbols, days), parse_dates=['time'])
        return df

    def _standardize(self, data: Any) -> pd.DataFrame:
        """Convert various input formats to strict DataFrame schema."""
        if isinstance(data, pd.DataFrame):
            df = data.copy()
        elif isinstance(data, dict):
            df = pd.DataFrame(data)
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")

        # Column name normalization
        col_map = {}
        for req in self.required_columns:
            matches = [c for c in df.columns if c.lower().replace(" ", "_") == req]
            if matches:
                col_map[matches[0]] = req
        df = df.rename(columns=col_map)

        # Ensure all required columns exist
        missing = [c for c in self.required_columns if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Dtypes
        df["time"] = pd.to_datetime(df["time"])
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        df["symbol"] = df["symbol"].astype(str)

        # Sort
        df = df.sort_values(["symbol", "time"]).reset_index(drop=True)

        # Drop rows with null prices
        price_nulls = df[["open", "high", "low", "close"]].isnull().any(axis=1)
        if price_nulls.sum() > 0:
            logger.warning(f"[DataAgent] Dropping {price_nulls.sum()} rows with null prices")
            df = df[~price_nulls].reset_index(drop=True)

        # Enforce high >= low
        invalid_hl = df["high"] < df["low"]
        if invalid_hl.sum() > 0:
            logger.warning(f"[DataAgent] Fixing {invalid_hl.sum()} rows where high < low")
            df.loc[invalid_hl, ["high", "low"]] = df.loc[invalid_hl, ["low", "high"]].values

        return df

    def _validate(self, df: pd.DataFrame) -> Dict[str, Any]:
        errors = []
        checks = {}

        # Check 1: No duplicate (symbol, time)
        dups = df.duplicated(subset=["symbol", "time"]).sum()
        checks["duplicates"] = int(dups)
        if dups > 0:
            errors.append(f"{dups} duplicate (symbol, time) rows")

        # Check 2: Prices positive
        neg_prices = (df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum()
        checks["non_positive_prices"] = int(neg_prices)
        if neg_prices > 0:
            errors.append(f"{neg_prices} rows with non-positive prices")

        # Check 3: Volume non-negative
        neg_vol = (df["volume"] < 0).sum()
        checks["negative_volume"] = int(neg_vol)
        if neg_vol > 0:
            errors.append(f"{neg_vol} rows with negative volume")

        # Check 4: High >= Low (post-fix)
        hl_fail = (df["high"] < df["low"]).sum()
        checks["high_lt_low"] = int(hl_fail)
        if hl_fail > 0:
            errors.append(f"{hl_fail} rows where high < low")

        # Check 5: Chronological per symbol
        time_issues = 0
        for sym, grp in df.groupby("symbol"):
            if not grp["time"].is_monotonic_increasing:
                time_issues += 1
        checks["non_chronological_symbols"] = time_issues
        if time_issues > 0:
            errors.append(f"{time_issues} symbols with non-chronological data")

        checks["total_rows"] = len(df)
        return {"passed": len(errors) == 0, "errors": errors, "checks": checks}