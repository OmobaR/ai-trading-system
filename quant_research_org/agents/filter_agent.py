"""
Filter Agent (Phase 4)
Explicitly sits AFTER regime.
Applies hard filters based on regime classification and confidence.
- No signal generation here.
- Only: should this bar be considered for strategy evaluation?
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, Any

import pandas as pd

from core.base_agent import BaseAgent, AgentResult
from core.state_store import StateStore
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)

class FilterAgent(BaseAgent):
    """
    Owns the constraint: BAR ELIGIBILITY.
    - Regime confidence must exceed threshold
    - Transition bars are filtered out by default
    - Range regimes may be filtered depending on configuration
    """

    def __init__(self, state_store: StateStore, message_bus: MessageBus,
                 min_confidence: float = 0.55,
                 filter_transitions: bool = True,
                 filter_range: bool = False):
        super().__init__("filter_agent", state_store, message_bus)
        self.min_confidence = min_confidence
        self.filter_transitions = filter_transitions
        self.filter_range = filter_range

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[FilterAgent] Applying eligibility filters...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="FilterAgent requires regime artifact")

            artifact = self.store.load(input_artifact_id)
            bundle = artifact.data
            df = bundle.get("regime_df") if isinstance(bundle, dict) else bundle
            if not isinstance(df, pd.DataFrame):
                return AgentResult(success=False, message="FilterAgent expects DataFrame")

            filtered_df, mask, diagnostics = self._apply_filters(df)

            artifact_id = self._produce_artifact(
                name="filtered_data",
                data={
                    "filtered_df": filtered_df,
                    "mask": mask,
                    "original_rows": len(df),
                    "filtered_rows": len(filtered_df),
                },
                phase="filter",
                parent_artifact=input_artifact_id,
                tags=["filtered", "eligible"],
                notes=f"Filtered from {len(df)} to {len(filtered_df)} rows",
            )

            return AgentResult(
                success=True,
                artifact_id=artifact_id,
                message=f"Filter applied: {len(filtered_df)}/{len(df)} rows eligible",
                diagnostics=diagnostics,
            )

        except Exception as e:
            logger.exception("[FilterAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _apply_filters(self, df: pd.DataFrame):
        mask = pd.Series(True, index=df.index)

        # Filter 1: Confidence threshold
        if "regime_confidence" in df.columns:
            mask &= df["regime_confidence"] >= self.min_confidence

        # Filter 2: Transition bars
        if self.filter_transitions and "transition_flag" in df.columns:
            mask &= ~df["transition_flag"]

        # Filter 3: Range regimes (optional)
        if self.filter_range and "regime" in df.columns:
            mask &= df["regime"] != "range"

        filtered = df[mask].copy()

        diagnostics = {
            "min_confidence": self.min_confidence,
            "filter_transitions": self.filter_transitions,
            "filter_range": self.filter_range,
            "retained_pct": round(len(filtered) / len(df), 3) if len(df) else 0.0,
            "by_regime": filtered["regime"].value_counts().to_dict() if "regime" in filtered.columns else {},
        }
        return filtered, mask, diagnostics
