# src/execution/mt5_global_reader.py
"""
Robust MT5 Global Variable Reader for SAE Suite
Uses MetaTrader5 package to read SAE_* globals directly.
No DLL changes required.
"""

import MetaTrader5 as mt5
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

class MT5GlobalReader:
    """Reads SAE_* global variables from running MT5 terminal."""

    def __init__(self):
        self.connected = False
        self._ensure_connection()

    def _ensure_connection(self) -> bool:
        """Ensure MT5 is connected (reconnects automatically if needed)."""
        if mt5.terminal_info() is not None:
            self.connected = True
            return True

        logger.info("Attempting to initialize MT5 terminal...")
        if mt5.initialize():
            logger.info("✅ MT5 terminal initialized")
            self.connected = True
            return True

        logger.error("❌ Failed to initialize MT5 terminal")
        self.connected = False
        return False

    def get_global(self, name: str, default: Any = None) -> Any:
        """Get value of an MT5 global variable."""
        if not self.connected and not self._ensure_connection():
            return default

        try:
            value = mt5.global_variable_get(name)
            return value if value is not None else default
        except Exception as e:
            logger.debug(f"Failed to read global {name}: {e}")
            self.connected = False  # Force reconnection on next call
            return default