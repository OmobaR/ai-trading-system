"""
Optimized Parquet export for backtesting.
"""
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.config.settings import get_config
from data_pipeline.core.logger import get_logger

logger = get_logger("export.parquet")


class ParquetWriter:
    PRICE_SCHEMA = pa.schema([
        ("time", pa.timestamp("ns", "UTC")),
        ("symbol", pa.string()),
        ("open", pa.float32()),
        ("high", pa.float32()),
        ("low", pa.float32()),
        ("close", pa.float32()),
        ("volume", pa.float32()),
    ])

    def __init__(self):
        self.config = get_config()

    def write_timeframe(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        output_dir: Optional[Path] = None
    ) -> Path:
        out_dir = output_dir or self.config.parquet_output_dir
        symbol_dir = out_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)

        filepath = symbol_dir / f"{timeframe}.parquet"

        write_df = self._prepare_dataframe(df)

        table = pa.Table.from_pandas(write_df, schema=self.PRICE_SCHEMA, preserve_index=False)

        pq.write_table(
            table,
            filepath,
            compression=self.config.parquet_compression,
            use_dictionary=["symbol"],
            write_statistics=True,
            row_group_size=100000,
            use_deprecated_int96_timestamps=False
        )

        logger.info(f"Wrote {len(write_df)} rows to {filepath}")
        return filepath

    def write_aligned(
        self,
        df: pd.DataFrame,
        symbol: str,
        output_dir: Optional[Path] = None
    ) -> Path:
        out_dir = output_dir or self.config.parquet_aligned_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        filepath = out_dir / f"{symbol}_multi_tf.parquet"

        write_df = df.copy().reset_index()
        if "time" not in write_df.columns:
            write_df = write_df.reset_index()

        write_df = write_df.sort_values("time")

        price_cols = [c for c in write_df.columns 
                     if any(x in c for x in ["open", "high", "low", "close", "volume"])]
        for col in price_cols:
            write_df[col] = write_df[col].astype("float32")

        table = pa.Table.from_pandas(write_df, preserve_index=False)
        pq.write_table(
            table,
            filepath,
            compression=self.config.parquet_compression,
            write_statistics=True,
            row_group_size=100000
        )

        logger.info(
            f"Wrote aligned dataset: {len(write_df)} rows, "
            f"{len(write_df.columns)} columns to {filepath}"
        )
        return filepath

    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy().reset_index()

        if "time" not in out.columns:
            if out.index.name == "time":
                out = out.reset_index()
            else:
                raise ValueError("DataFrame must have 'time' column or time index")

        cols = ["time", "symbol", "open", "high", "low", "close", "volume"]
        out = out[[c for c in cols if c in out.columns]]

        if "symbol" not in out.columns:
            out["symbol"] = "UNKNOWN"

        for col in ["open", "high", "low", "close", "volume"]:
            if col in out.columns:
                out[col] = out[col].astype("float32")

        out = out.sort_values("time").reset_index(drop=True)
        return out

    def read_timeframe(self, symbol: str, timeframe: str) -> pd.DataFrame:
        filepath = self.config.parquet_output_dir / symbol / f"{timeframe}.parquet"
        if not filepath.exists():
            raise FileNotFoundError(f"Parquet file not found: {filepath}")
        return pd.read_parquet(filepath, engine=self.config.parquet_engine)

    def read_aligned(self, symbol: str) -> pd.DataFrame:
        filepath = self.config.parquet_aligned_dir / f"{symbol}_multi_tf.parquet"
        if not filepath.exists():
            raise FileNotFoundError(f"Aligned Parquet not found: {filepath}")
        return pd.read_parquet(filepath, engine=self.config.parquet_engine)
