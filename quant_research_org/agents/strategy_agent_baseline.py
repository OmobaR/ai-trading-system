"""
Strategy Agent – uses continuous trend strength and volatility filter.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

import pandas as pd
import numpy as np

from core.base_agent import BaseAgent, AgentResult
from core.state_store import StateStore
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)

@dataclass
class Signal:
    direction: int
    confidence: float
    regime: str
    symbol: str
    timestamp: str
    rationale: str

class StrategyAgent(BaseAgent):
    def __init__(self, state_store: StateStore, message_bus: MessageBus):
        super().__init__("strategy_agent", state_store, message_bus)
        self.output_dir = Path("data/processed/strategy_continuous")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[StrategyAgent] Generating signals (continuous trend)...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="StrategyAgent requires regime artifact")

            regime_artifact = self.store.load(input_artifact_id)
            file_paths = regime_artifact.data.get("file_paths", [])
            if not file_paths:
                return AgentResult(success=False, message="No regime files found")

            signal_files = []
            for file_path in file_paths:
                symbol = Path(file_path).stem.replace("_regime", "")
                logger.info(f"  Generating signals for {symbol}...")
                df = pd.read_parquet(file_path)
                signals = self._generate_signals(df)
                if signals.empty:
                    continue
                out_path = self.output_dir / f"{symbol}_signals.parquet"
                signals.to_parquet(out_path, index=False)
                signal_files.append(str(out_path))

            artifact_id = self._produce_artifact(
                name="strategy_signals",
                data={"file_paths": signal_files},
                phase="strategy",
                parent_artifact=input_artifact_id,
                tags=["signals"],
                notes=f"Generated {len(signal_files)} files",
            )
            return AgentResult(success=True, artifact_id=artifact_id, message="Signals generated")

        except Exception as e:
            logger.exception("[StrategyAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # Use trend_strength (if present) else compute from ema_7_21_ratio
        if "trend_strength" in df.columns:
            trend = df["trend_strength"]
            base_conf = df["trend_confidence"]
        else:
            ratio = df.get("ema_7_21_ratio", 1.0)
            trend = (ratio - 1.0) / 0.05
            trend = trend.clip(-1, 1)
            base_conf = trend.abs() * 0.8 + 0.2

        # Volatility filter: only trade when ATR not abnormally high
        atr = df.get("atr_14", 0.01)
        median_atr = atr.rolling(100, min_periods=10).median()
        vol_ok = atr < (median_atr * 1.5)
        vol_ok = vol_ok.fillna(True)

        # Direction from trend strength: positive -> long, negative -> short
        direction = np.sign(trend)
        # Confidence from trend strength magnitude * base confidence
        confidence = base_conf * trend.abs()
        confidence = confidence.clip(0.05, 0.95)

        # Optional: Mean-reversion signals in weak trend (abs(trend) < 0.2)
        weak_mask = (trend.abs() < 0.2) & (df["position_in_yearly_range"] < 0.3) & (df["rsi_14"] < 40)
        direction[weak_mask] = 1
        confidence[weak_mask] = 0.5

        weak_mask_sell = (trend.abs() < 0.2) & (df["position_in_yearly_range"] > 0.7) & (df["rsi_14"] > 60)
        direction[weak_mask_sell] = -1
        confidence[weak_mask_sell] = 0.5

        # Apply volatility filter: set direction to 0 where vol too high
        direction[~vol_ok] = 0
        confidence[~vol_ok] = 0.0

        df["direction"] = direction.astype(int)
        df["confidence"] = confidence.round(3)
        # Keep only rows with non-zero direction
        result = df[df["direction"] != 0].copy()
        # Ensure required columns for risk agent
        keep = ["time", "symbol", "open", "high", "low", "close", "volume",
                "direction", "confidence", "atr_14", "regime", "regime_confidence"]
        keep = [c for c in keep if c in result.columns]
        return result[keep]