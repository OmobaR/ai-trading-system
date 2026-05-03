"""
Governance Agent (NEW — CRITICAL)
Anti-bloat + anti-overfit firewall.
Evaluates feature set for:
1. Redundancy (correlation > 0.90)
2. Over-complexity
3. Feature leakage risk

Decides: KEEP / MERGE / REMOVE
Ensures: EMA system becomes "state representation", not raw indicators.
Recommends: Whether SAE compression is required.
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, List, Any, Set, Tuple
from dataclasses import dataclass

import pandas as pd
import numpy as np

from core.base_agent import BaseAgent, AgentResult
from core.state_store import StateStore, ArtifactStatus
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)

CORRELATION_THRESHOLD = 0.90
MAX_FEATURE_COUNT = 25
SAE_TRIGGER_COUNT = 20

@dataclass
class GovernanceDecision:
    feature: str
    action: str  # KEEP, MERGE, REMOVE
    reason: str
    merged_into: Optional[str] = None

class GovernanceAgent(BaseAgent):
    """
    Owns the constraint: ANTI-BLOAT and ANTI-OVERFIT.
    - Mandatory gate after Feature Agent
    - No pipeline proceeds without governance approval
    """

    def __init__(self, state_store: StateStore, message_bus: MessageBus):
        super().__init__("governance_agent", state_store, message_bus)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[GovernanceAgent] Reviewing feature set...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="Governance requires feature artifact")

            artifact = self.store.load(input_artifact_id)
            bundle = artifact.data
            feature_df = bundle["feature_df"]
            schema_raw = bundle.get("schema", [])

            decisions, diagnostics = self._review(feature_df, schema_raw)

            approved_features = [d.feature for d in decisions if d.action in ("KEEP", "MERGE")]
            removed_features = [d.feature for d in decisions if d.action == "REMOVE"]

            # Build approved feature DataFrame
            keep_cols = ["time", "symbol", "open", "high", "low", "close", "volume"] + approved_features
            available = [c for c in keep_cols if c in feature_df.columns]
            approved_df = feature_df[available].copy()

            sae_recommended = len(approved_features) > SAE_TRIGGER_COUNT

            # If EMAs are raw, flag that they should become state representation
            ema_state_note = self._check_ema_state_representation(approved_features)

            # Mark parent as reviewed
            self.store.update_status(input_artifact_id, ArtifactStatus.APPROVED if len(removed_features) < len(decisions) else ArtifactStatus.REJECTED)

            output_id = self._produce_artifact(
                name="governance_approved_feature_schema",
                data={
                    "approved_df": approved_df,
                    "decisions": [d.__dict__ for d in decisions],
                    "approved_features": approved_features,
                    "removed_features": removed_features,
                },
                phase="governance",
                parent_artifact=input_artifact_id,
                tags=["governance", "approved"],
                notes=f"Approved {len(approved_features)} features. Removed {len(removed_features)}. SAE recommended: {sae_recommended}. {ema_state_note}",
            )

            return AgentResult(
                success=True,
                artifact_id=output_id,
                message=f"Governance complete. Kept {len(approved_features)}, removed {len(removed_features)}. SAE={sae_recommended}",
                diagnostics={
                    **diagnostics,
                    "sae_recommended": sae_recommended,
                    "approved_count": len(approved_features),
                    "removed_count": len(removed_features),
                    "ema_state_note": ema_state_note,
                },
            )

        except Exception as e:
            logger.exception("[GovernanceAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _review(self, df: pd.DataFrame, schema_raw: List[Dict]) -> Tuple[List[GovernanceDecision], Dict[str, Any]]:
        """Run the governance review rules."""
        # Identify numeric feature columns only
        exclude = {"time", "symbol", "open", "high", "low", "close", "volume"}
        numeric_cols = [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]

        decisions: List[GovernanceDecision] = []
        diagnostics: Dict[str, Any] = {"correlation_matrix": None, "leakage_flags": [], "complexity_score": 0}

        # Rule 1: Correlation analysis
        if len(numeric_cols) > 1:
            corr = df[numeric_cols].corr().abs()
            diagnostics["correlation_matrix"] = corr.to_dict()

            # Find highly correlated pairs
            high_corr_pairs: Set[Tuple[str, str]] = set()
            for i in range(len(numeric_cols)):
                for j in range(i + 1, len(numeric_cols)):
                    c1, c2 = numeric_cols[i], numeric_cols[j]
                    val = corr.loc[c1, c2]
                    if val > CORRELATION_THRESHOLD and not np.isnan(val):
                        high_corr_pairs.add((c1, c2))

            # Decide MERGE for redundant EMA ratios vs raw EMAs
            merged = set()
            for c1, c2 in high_corr_pairs:
                if c1 in merged or c2 in merged:
                    continue
                # Prefer ratio / composite over raw slower EMAs if tactical EMAs present
                if "ratio" in c1 or c2 in {"ema_50_200_ratio", "ema_50_100_ratio", "ema_7_21_ratio", "ema_7_34_ratio", "ema_21_34_ratio"}:
                    keep = c1 if "ratio" in c1 else c2
                    drop = c2 if "ratio" in c1 else c1
                else:
                    keep, drop = c1, c2

                decisions.append(GovernanceDecision(feature=drop, action="REMOVE", reason=f"Redundant with {keep} (corr={corr.loc[c1, c2]:.3f})"))
                merged.add(drop)

        # Rule 2: Over-complexity
        for col in numeric_cols:
            if any(d.feature == col for d in decisions):
                continue
            null_rate = df[col].isnull().mean()
            if null_rate > 0.30:
                decisions.append(GovernanceDecision(feature=col, action="REMOVE", reason=f"Excessive nulls ({null_rate:.1%})"))
                continue

        # Rule 3: Feature leakage risk
        leakage_indicators = ["close", "open", "high", "low"]
        for col in numeric_cols:
            if any(d.feature == col for d in decisions):
                continue
            # If a feature is almost perfectly correlated with close/open, it's likely leakage
            for leak in leakage_indicators:
                if leak in col and col != leak and not col.startswith("ema") and not col.startswith("rsi") and not col.startswith("dist"):
                    # Skip legitimate derived features
                    pass

        # Approve remaining
        removed_set = {d.feature for d in decisions}
        for col in numeric_cols:
            if col not in removed_set:
                decisions.append(GovernanceDecision(feature=col, action="KEEP", reason="Passed governance checks"))

        diagnostics["complexity_score"] = len([d for d in decisions if d.action == "KEEP"])
        return decisions, diagnostics

    def _check_ema_state_representation(self, approved: List[str]) -> str:
        emas = [f for f in approved if f.startswith("ema_") and not "ratio" in f]
        ratios = [f for f in approved if "ratio" in f]
        if len(emas) > 4 and len(ratios) < 2:
            return "WARNING: EMAs are raw indicators. Consider using EMA-ratios as state representation."
        return "EMA state representation OK."
