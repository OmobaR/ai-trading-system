"""
Structured logging with separate streams for ingestion, anomalies, and validation.
"""
import logging
import sys
from pathlib import Path
from typing import Optional

from data_pipeline.config.settings import get_config


class PipelineLogger:
    """Centralized logger with file handlers per concern."""

    _instance: Optional["PipelineLogger"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        config = get_config()
        self.log_dir = config.log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("data_pipeline")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []

        detailed = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        simple = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(simple)
        self.logger.addHandler(console)

        self._add_file_handler("ingestion", detailed)
        self._add_file_handler("anomalies", detailed)
        self._add_file_handler("validation", detailed)
        self._add_file_handler("pipeline", detailed)

        self._initialized = True

    def _add_file_handler(self, name: str, formatter: logging.Formatter):
        handler = logging.FileHandler(self.log_dir / f"{name}.log")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        handler.set_name(name)
        self.logger.addHandler(handler)

    def get_logger(self, name: str = "pipeline") -> logging.Logger:
        return self.logger.getChild(name)

    def log_anomaly(self, symbol: str, timeframe: str, issue: str, details: dict):
        anomaly_logger = self.logger.getChild("anomalies")
        anomaly_logger.warning(
            f"[ANOMALY] {symbol} {timeframe}: {issue} | {details}"
        )

    def log_validation(self, symbol: str, timeframe: str, result: dict):
        val_logger = self.logger.getChild("validation")
        val_logger.info(f"[VALIDATION] {symbol} {timeframe}: {result}")


def get_logger(name: str = "pipeline") -> logging.Logger:
    return PipelineLogger().get_logger(name)
