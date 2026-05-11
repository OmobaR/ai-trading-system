"""
Regime Agent – now outputs continuous trend strength.
Memory‑safe, per‑symbol file‑based.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass

import pandas as pd
import numpy as np

from core.base_agent import BaseAgent, AgentResult
from core.state_store import StateStore
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)

@dataclass
class RegimeClassification:
    regime: str
    confidence: float
    transition_flag: bool
    regime_duration: int
    trend_strength: float
    notes: str

class RegimeAgent(BaseAgent):
    def __init__(self, state_store: StateStore, message_bus: MessageBus):
        super().__init__("regime_agent", state_store, message_bus)
        self.output_dir = Path("data/processed/regime_continuous")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[RegimeAgent] Classifying regimes (continuous trend)...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="RegimeAgent requires governance artifact")

            gov_artifact = self.store.load(input_artifact_id)
            gov_data = gov_artifact.data
            approved_features = gov_data.get("approved_features", [])
            original_feature_id = gov_data.get("original_feature_artifact_id")
            if not original_feature_id:
                return AgentResult(success=False, message="Missing original_feature_artifact_id")

            feat_artifact = self.store.load(original_feature_id)
            full_df = feat_artifact.data["feature_df"]

            essential = ["time", "symbol", "open", "high", "low", "close", "volume"]
            keep_cols = essential + approved_features
            available = [c for c in keep_cols if c in full_df.columns]

            symbols = full_df['symbol'].unique()
            file_paths = []
            classifications: Dict[str, List[RegimeClassification]] = {}

            for symbol in symbols:
                logger.info(f"  Processing continuous regime for {symbol}...")
                sym_mask = full_df['symbol'] == symbol
                sym_df = full_df.loc[sym_mask, available].copy()
                classified, cls_list = self._classify(sym_df)
                file_path = self.output_dir / f"{symbol}_regime.parquet"
                classified.to_parquet(file_path, index=False)
                file_paths.append(str(file_path))
                classifications[symbol] = cls_list
                del sym_df

            artifact_id = self._produce_artifact(
                name="regime_labels_continuous",
                data={"file_paths": file_paths, "classifications": {k: [c.__dict__ for c in v] for k,v in classifications.items()}},
                phase="regime",
                parent_artifact=input_artifact_id,
                tags=["regime", "continuous"],
                notes=f"Saved {len(file_paths)} files",
            )
            return AgentResult(success=True, artifact_id=artifact_id, message="Regime classification complete")

        except Exception as e:
            logger.exception("[RegimeAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _classify(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[RegimeClassification]]:
        out = df.copy()
        n = len(out)
        trend_strengths = np.zeros(n)
        confidences = np.zeros(n)
        regimes = ["unknown"] * n
        transition_flags = [False] * n

        for i in range(n):
            row = out.iloc[i]
            trend, conf, regime, transition = self._classify_row(row, out.iloc[:i+1])
            trend_strengths[i] = trend
            confidences[i] = conf
            regimes[i] = regime
            transition_flags[i] = transition

        out["trend_strength"] = trend_strengths
        out["trend_confidence"] = confidences
        out["regime"] = regimes
        out["regime_confidence"] = confidences
        out["transition_flag"] = transition_flags
        out["regime_duration"] = self._compute_regime_durations(regimes)

        classifications = [RegimeClassification(
            regime=regimes[i],
            confidence=confidences[i],
            transition_flag=transition_flags[i],
            regime_duration=out["regime_duration"].iloc[i],
            trend_strength=trend_strengths[i],
            notes="",
        ) for i in range(n)]

        return out, classifications

    def _classify_row(self, row: pd.Series, history: pd.DataFrame) -> Tuple[float, float, str, bool]:
        # Use ema_7_21_ratio to compute continuous trend strength
        ratio = row.get("ema_7_21_ratio", 1.0)
        # Clamp ratio to [0.95, 1.05] and map to [-1, 1]
        ratio_clipped = np.clip(ratio, 0.95, 1.05)
        trend_strength = (ratio_clipped - 1.0) / 0.05   # 0.05 delta gives full scale
        trend_strength = np.clip(trend_strength, -1.0, 1.0)

        # Confidence based on absolute trend strength
        confidence = min(abs(trend_strength) * 0.8 + 0.2, 0.95)

        # For backward compatibility, also assign a discrete regime
        if trend_strength > 0.5:
            regime = "trend_continuation"
        elif trend_strength < -0.5:
            regime = "trend_continuation"
        elif abs(trend_strength) < 0.2:
            regime = "transition"
        else:
            regime = "weak_trend"

        # Transition flag based on change in trend direction (simplistic)
        transition = False
        if len(history) >= 3:
            # If 'trend_strength' already exists in history, use it; else use ratio
            if 'trend_strength' in history.columns:
                prev = history['trend_strength'].iloc[-3:].mean()
            else:
                prev = 0.0
            if trend_strength * prev < 0 and abs(trend_strength) > 0.2:
                transition = True
        return trend_strength, confidence, regime, transition

    def _compute_regime_durations(self, regimes: List[str]) -> List[int]:
        durations = [1] * len(regimes)
        for i in range(1, len(regimes)):
            if regimes[i] == regimes[i-1]:
                durations[i] = durations[i-1] + 1
            else:
                durations[i] = 1
        return durations