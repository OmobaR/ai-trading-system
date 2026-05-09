"""
Filter Agent (Phase 4) – per‑symbol, file‑based.
Explicitly sits AFTER regime.
Applies hard filters based on regime classification and confidence.
- No signal generation here.
- Only: should this bar be considered for strategy evaluation?
"""
from __future__ import annotations

import logging
from pathlib import Path
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
        self.output_dir = Path("data/processed/filter")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[FilterAgent] Applying eligibility filters...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="FilterAgent requires regime artifact")

            regime_artifact = self.store.load(input_artifact_id)
            file_paths = regime_artifact.data.get("file_paths", [])
            if not file_paths:
                return AgentResult(success=False, message="No regime files found")

            filtered_files = []
            total_rows_before = 0
            total_rows_after = 0
            regime_counts_before = {}
            regime_counts_after = {}

            for file_path in file_paths:
                symbol = Path(file_path).stem.replace("_regime", "")
                logger.info(f"  Filtering {symbol}...")
                df = pd.read_parquet(file_path)
                before = len(df)
                total_rows_before += before

                # Count regimes before filtering
                if "regime" in df.columns:
                    for reg, cnt in df["regime"].value_counts().items():
                        regime_counts_before[reg] = regime_counts_before.get(reg, 0) + cnt

                filtered_df, mask, diag = self._apply_filters(df)
                after = len(filtered_df)
                total_rows_after += after

                # Count regimes after filtering
                if "regime" in filtered_df.columns:
                    for reg, cnt in filtered_df["regime"].value_counts().items():
                        regime_counts_after[reg] = regime_counts_after.get(reg, 0) + cnt

                out_path = self.output_dir / f"{symbol}_filtered.parquet"
                filtered_df.to_parquet(out_path, index=False)
                filtered_files.append(str(out_path))

            diagnostics = {
                "original_rows": total_rows_before,
                "filtered_rows": total_rows_after,
                "retained_pct": round(total_rows_after / total_rows_before, 3) if total_rows_before else 0.0,
                "regime_counts_before": regime_counts_before,
                "regime_counts_after": regime_counts_after,
                "min_confidence": self.min_confidence,
                "filter_transitions": self.filter_transitions,
                "filter_range": self.filter_range,
            }

            artifact_id = self._produce_artifact(
                name="filtered_data",
                data={
                    "file_paths": filtered_files,
                    "original_rows": total_rows_before,
                    "filtered_rows": total_rows_after,
                },
                phase="filter",
                parent_artifact=input_artifact_id,
                tags=["filtered", "eligible"],
                notes=f"Filtered from {total_rows_before} to {total_rows_after} rows",
            )

            return AgentResult(
                success=True,
                artifact_id=artifact_id,
                message=f"Filter applied: {total_rows_after}/{total_rows_before} rows eligible",
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
        return filtered, mask, {}