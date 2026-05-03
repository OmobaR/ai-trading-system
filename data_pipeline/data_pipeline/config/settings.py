"""
Centralized configuration with environment overrides.
Maintains compatibility with existing src.config.settings.config
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable pipeline configuration."""

    # Database
    db_uri: str = field(default_factory=lambda: os.getenv(
        "DB_URI", 
        "postgresql://postgres:postgres@localhost:5432/trading"
    ))
    db_isolation_level: str = "AUTOCOMMIT"

    # Paths
    csv_input_dir: Path = field(default_factory=lambda: Path(
        os.getenv("MT5_CSV_DIR", r"C:\Users\Olugb\Workspace\MT5_Trading\MT5_Quant_Research\MT5_Historical_Data")
    ))
    parquet_output_dir: Path = field(default_factory=lambda: Path(
        os.getenv("PARQUET_DIR", "data/parquet")
    ))
    parquet_aligned_dir: Path = field(default_factory=lambda: Path(
        os.getenv("PARQUET_ALIGNED_DIR", "data/parquet_aligned")
    ))
    log_dir: Path = field(default_factory=lambda: Path("data_pipeline/logs"))
    report_dir: Path = field(default_factory=lambda: Path("data_pipeline/reports"))

    # Processing
    base_timeframe: str = "M1"
    batch_size: int = 50_000
    max_workers: int = field(default_factory=lambda: min(4, os.cpu_count() or 1))

    # Validation thresholds
    max_missing_pct: float = 0.01
    max_duplicate_pct: float = 0.001

    # Parquet
    parquet_compression: str = "zstd"
    parquet_engine: str = "pyarrow"

    def __post_init__(self):
        for path in [self.parquet_output_dir, self.parquet_aligned_dir, 
                     self.log_dir, self.report_dir]:
            path.mkdir(parents=True, exist_ok=True)


_config: Optional[PipelineConfig] = None


def get_config() -> PipelineConfig:
    global _config
    if _config is None:
        _config = PipelineConfig()
    return _config


def override_config(**kwargs) -> PipelineConfig:
    global _config
    base = get_config()
    _config = PipelineConfig(
        db_uri=kwargs.get("db_uri", base.db_uri),
        db_isolation_level=base.db_isolation_level,
        csv_input_dir=Path(kwargs.get("csv_input_dir", str(base.csv_input_dir))),
        parquet_output_dir=Path(kwargs.get("parquet_output_dir", str(base.parquet_output_dir))),
        parquet_aligned_dir=Path(kwargs.get("parquet_aligned_dir", str(base.parquet_aligned_dir))),
        log_dir=base.log_dir,
        report_dir=base.report_dir,
        base_timeframe=kwargs.get("base_timeframe", base.base_timeframe),
        batch_size=kwargs.get("batch_size", base.batch_size),
        max_workers=kwargs.get("max_workers", base.max_workers),
        max_missing_pct=kwargs.get("max_missing_pct", base.max_missing_pct),
        max_duplicate_pct=kwargs.get("max_duplicate_pct", base.max_duplicate_pct),
        parquet_compression=kwargs.get("parquet_compression", base.parquet_compression),
        parquet_engine=kwargs.get("parquet_engine", base.parquet_engine),
    )
    return _config
