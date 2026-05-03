"""
Dynamic CSV scanning, parsing, and normalization.
CSV = SOURCE OF TRUTH for M5+ timeframes.
"""
import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

import pandas as pd

from data_pipeline.config.settings import get_config
from data_pipeline.config.timeframes import Timeframe, parse_timeframe
from data_pipeline.core.exceptions import IngestionError
from data_pipeline.core.logger import get_logger

logger = get_logger("ingestion.csv")


class CSVFileInfo(NamedTuple):
    path: Path
    symbol: str
    timeframe: Timeframe
    raw_filename: str


def parse_filename(filename: str) -> Tuple[str, Timeframe]:
    name = Path(filename).stem
    parts = name.split("_")
    if len(parts) < 2:
        raise ValueError(f"Invalid filename format: {filename}")

    tf_token = parts[-1]
    timeframe = parse_timeframe(tf_token)
    symbol = " ".join(parts[:-1])

    return symbol, timeframe


def scan_csv_directory(directory: Optional[Path] = None) -> List[CSVFileInfo]:
    config = get_config()
    directory = directory or config.csv_input_dir

    if not directory.exists():
        raise FileNotFoundError(f"CSV directory not found: {directory}")

    csv_files = []
    pattern = re.compile(r".*\.csv$", re.IGNORECASE)

    for file_path in directory.iterdir():
        if not file_path.is_file() or not pattern.match(file_path.name):
            continue

        try:
            symbol, timeframe = parse_filename(file_path.name)
            csv_files.append(CSVFileInfo(
                path=file_path,
                symbol=symbol,
                timeframe=timeframe,
                raw_filename=file_path.name
            ))
            logger.debug(f"Scanned: {file_path.name} → {symbol} {timeframe.value}")
        except ValueError as e:
            logger.warning(f"Skipping unparseable file: {file_path.name} | {e}")

    logger.info(f"Scanned {len(csv_files)} valid CSV files from {directory}")
    return csv_files


def normalize_csv_columns(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    df.columns = [c.lower().strip() for c in df.columns]

    column_map = {
        "open": ["open", "o", "open_price"],
        "high": ["high", "h", "high_price"],
        "low": ["low", "l", "low_price"],
        "close": ["close", "c", "close_price"],
        "volume": ["volume", "vol", "v", "tick_volume", "real_volume"],
        "time": ["time", "date", "datetime", "timestamp", "date_time"],
    }

    actual_to_standard = {}
    for standard, variants in column_map.items():
        for col in df.columns:
            if col in variants:
                actual_to_standard[col] = standard
                break

    required = {"time", "open", "high", "low", "close", "volume"}
    missing = required - set(actual_to_standard.values())
    if missing:
        if len(df.columns) >= 6 and len(missing) == len(required):
            logger.warning(f"{filename}: No recognizable headers, inferring by position")
            df.columns = ["time", "open", "high", "low", "close", "volume"] + list(df.columns[6:])
        else:
            raise ValueError(f"{filename}: Missing required columns: {missing}. Found: {list(df.columns)}")
    else:
        df = df.rename(columns=actual_to_standard)

    return df[["time", "open", "high", "low", "close", "volume"]]


def parse_mt5_timestamp(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, format="mixed", errors="coerce")
    parsed = parsed.dt.tz_localize("Etc/GMT-1")
    return parsed


def load_csv_file(info: CSVFileInfo) -> pd.DataFrame:
    logger.info(f"Loading: {info.raw_filename} ({info.symbol} {info.timeframe.value})")

    try:
        with open(info.path, "r", encoding="utf-8") as f:
            first_line = f.readline()
            delimiter = ";" if ";" in first_line else ","

        df = pd.read_csv(
            info.path, 
            delimiter=delimiter,
            low_memory=False,
            skipinitialspace=True
        )
    except Exception as e:
        raise IngestionError(f"Failed to read {info.raw_filename}: {e}")

    df = normalize_csv_columns(df, info.raw_filename)
    df["time"] = parse_mt5_timestamp(df["time"])

    invalid_time = df["time"].isna()
    if invalid_time.any():
        n_invalid = invalid_time.sum()
        logger.warning(f"{info.raw_filename}: Dropping {n_invalid} rows with invalid timestamps")
        df = df[~invalid_time].copy()

    df["symbol"] = info.symbol

    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    invalid_numeric = df[numeric_cols].isna().any(axis=1)
    if invalid_numeric.any():
        n_invalid = invalid_numeric.sum()
        logger.warning(f"{info.raw_filename}: Dropping {n_invalid} rows with invalid numeric data")
        df = df[~invalid_numeric].copy()

    df = df.sort_values("time").reset_index(drop=True)

    invalid_ohlc = (
        (df["high"] < df["low"]) | 
        (df["high"] < df[["open", "close"]].min(axis=1)) |
        (df["low"] > df[["open", "close"]].max(axis=1))
    )
    if invalid_ohlc.any():
        n_invalid = invalid_ohlc.sum()
        logger.warning(f"{info.raw_filename}: Found {n_invalid} rows with invalid OHLC relationships")

    logger.info(f"Loaded {len(df)} rows from {info.raw_filename}")
    return df


def load_all_csv_files(
    directory: Optional[Path] = None,
    timeframe_filter: Optional[List[Timeframe]] = None
) -> Dict[Tuple[str, Timeframe], pd.DataFrame]:
    files = scan_csv_directory(directory)

    if timeframe_filter:
        files = [f for f in files if f.timeframe in timeframe_filter]

    results = {}
    for info in files:
        try:
            df = load_csv_file(info)
            key = (info.symbol, info.timeframe)
            if key in results:
                logger.warning(f"Duplicate symbol/timeframe detected: {key}, appending data")
                results[key] = pd.concat([results[key], df]).sort_values("time").reset_index(drop=True)
            else:
                results[key] = df
        except Exception as e:
            logger.error(f"Failed to load {info.raw_filename}: {e}")
            continue

    logger.info(f"Successfully loaded {len(results)} symbol/timeframe combinations")
    return results
