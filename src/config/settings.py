"""
Configuration loader for AI Trading System.
Loads from .env file and optional YAML overrides.
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional, List
from dotenv import load_dotenv
import yaml

load_dotenv()

class TradingConfig:
    def __init__(self, yaml_path: Optional[Path] = None):
        self._yaml_config = {}
        if yaml_path and yaml_path.exists():
            with open(yaml_path, 'r') as f:
                self._yaml_config = yaml.safe_load(f) or {}
        
        # Mode
        self.MODE = self._get_str("MODE", "simulate")
        self.SYMBOLS = self._get_list("SYMBOLS", [
            "GainX 400", "GainX 600", "GainX 800", "GainX 999", "GainX 1200",
            "PainX 400", "PainX 600", "PainX 800", "PainX 999", "PainX 1200",
            "FlipX 1", "FlipX 2", "FlipX 3", "FlipX 4", "FlipX 5",
            "FX Vol 20", "FX Vol 40", "FX Vol 60", "FX Vol 80", "FX Vol 99",
            "SFX Vol 20", "SFX Vol 40", "SFX Vol 60", "SFX Vol 80", "SFX Vol 99",
            "TrendX 600", "TrendX 1200", "TrendX 1800",
            "SwitchX 600", "SwitchX 1200", "SwitchX 1800",
            "BreakX 600", "BreakX 1200", "BreakX 1800"
        ])
        
        # MT5
        self.MT5_LOGIN = self._get_int("MT5_LOGIN", 19345714)
        self.MT5_PASSWORD = self._get_str("MT5_PASSWORD", "bL$3Vs5)")
        self.MT5_SERVER = self._get_str("MT5_SERVER", "Weltrade-Demo")
        
        # Risk
        self.RISK_CAPITAL = self._get_float("RISK_CAPITAL", 10000.0)
        self.MAX_DRAWDOWN = self._get_float("MAX_DRAWDOWN", 0.15)
        
        # Database
        self.DB_HOST = self._get_str("DB_HOST", "localhost")
        self.DB_PORT = self._get_int("DB_PORT", 5432)
        self.DB_NAME = self._get_str("DB_NAME", "ai_trading_db")
        self.DB_USER = self._get_str("DB_USER", "postgres")
        self.DB_PASSWORD = self._get_str("DB_PASSWORD", "password")
        
        # Redis
        self.REDIS_HOST = self._get_str("REDIS_HOST", "localhost")
        self.REDIS_PORT = self._get_int("REDIS_PORT", 6379)
        self.REDIS_DB = self._get_int("REDIS_DB", 0)
        
        # Logging
        self.LOG_LEVEL = self._get_str("LOG_LEVEL", "INFO")
    
    def _get_str(self, key: str, default: str) -> str:
        return self._yaml_config.get(key, os.getenv(key, default))
    
    def _get_int(self, key: str, default: int) -> int:
        val = self._yaml_config.get(key, os.getenv(key))
        return int(val) if val is not None else default
    
    def _get_float(self, key: str, default: float) -> float:
        val = self._yaml_config.get(key, os.getenv(key))
        return float(val) if val is not None else default
    
    def _get_list(self, key: str, default: List[str]) -> List[str]:
        val = self._yaml_config.get(key, os.getenv(key))
        if val is None:
            return default
        if isinstance(val, str):
            return [x.strip() for x in val.split(',')]
        return val

config = TradingConfig()