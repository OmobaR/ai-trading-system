"""
Governance Agent (NEW — CRITICAL)
Anti-bloat + anti-overfit firewall – processes each symbol independently.
Memory‑safe: does not duplicate the full feature DataFrame.
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
    def __init__(self, state_store: StateStore, message_bus: MessageBus):
        super().__init__("governance_agent", state_store, message_bus)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[GovernanceAgent] Reviewing feature set (per symbol, memory safe)...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="Governance requires feature artifact")

            artifact = self.store.load(input_artifact_id)
            bundle = artifact.data
            feature_df = bundle["feature_df"]
            schema_raw = bundle.get("schema", [])

            # Process each symbol separately
            symbols = feature_df['symbol'].unique()
            all_decisions: List[GovernanceDecision] = []
            approved_features_per_symbol: Dict[str, List[str]] = {}
            feature_union_keep = set()
            feature_union_remove = set()

            for sym in symbols:
                logger.info(f"  Running governance on {sym}...")
                sym_df = feature_df[feature_df['symbol'] == sym].copy()
                decisions, _ = self._review(sym_df, schema_raw)
                all_decisions.extend(decisions)
                keep = [d.feature for d in decisions if d.action in ("KEEP", "MERGE")]
                approved_features_per_symbol[sym] = keep
                feature_union_keep.update(keep)
                feature_union_remove.update([d.feature for d in decisions if d.action == "REMOVE"])

            approved_features = list(feature_union_keep)
            removed_features = list(feature_union_remove)
            sae_recommended = len(approved_features) > SAE_TRIGGER_COUNT
            ema_state_note = self._check_ema_state_representation(approved_features)

            # Mark parent as approved
            self.store.update_status(input_artifact_id, ArtifactStatus.APPROVED if approved_features else ArtifactStatus.REJECTED)

            # ✅ CRITICAL CHANGE: Do NOT copy the full DataFrame – we store only metadata.
            # Downstream agents must read from the original feature artifact and filter on the fly.
            output_id = self._produce_artifact(
                name="governance_approved_feature_schema",
                data={
                    "approved_features": approved_features,
                    "removed_features": removed_features,
                    "per_symbol": approved_features_per_symbol,
                    "original_feature_artifact_id": input_artifact_id,  # reference for downstream
                    "approved_df": None,  # prevent memory explosion
                },
                phase="governance",
                parent_artifact=input_artifact_id,
                tags=["governance", "approved"],
                notes=f"Approved {len(approved_features)} features. SAE={sae_recommended}. {ema_state_note}",
            )

            return AgentResult(
                success=True,
                artifact_id=output_id,
                message=f"Governance complete. Kept {len(approved_features)}, removed {len(removed_features)}. SAE={sae_recommended}",
                diagnostics={
                    "sae_recommended": sae_recommended,
                    "approved_count": len(approved_features),
                    "removed_count": len(removed_features),
                },
            )

        except Exception as e:
            logger.exception("[GovernanceAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _review(self, df: pd.DataFrame, schema_raw: List[Dict]) -> Tuple[List[GovernanceDecision], Dict[str, Any]]:
        exclude = {"time", "symbol", "open", "high", "low", "close", "volume"}
        numeric_cols = [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]
        decisions: List[GovernanceDecision] = []
        diagnostics: Dict[str, Any] = {"correlation_matrix": None, "leakage_flags": [], "complexity_score": 0}

        if len(numeric_cols) > 1:
            corr = df[numeric_cols].corr().abs()
            diagnostics["correlation_matrix"] = corr.to_dict()
            high_corr_pairs: Set[Tuple[str, str]] = set()
            for i in range(len(numeric_cols)):
                for j in range(i + 1, len(numeric_cols)):
                    c1, c2 = numeric_cols[i], numeric_cols[j]
                    val = corr.loc[c1, c2]
                    if val > CORRELATION_THRESHOLD and not np.isnan(val):
                        high_corr_pairs.add((c1, c2))
            merged = set()
            for c1, c2 in high_corr_pairs:
                if c1 in merged or c2 in merged:
                    continue
                if "ratio" in c1 or c2 in {"ema_50_200_ratio", "ema_50_100_ratio", "ema_7_21_ratio", "ema_7_34_ratio", "ema_21_34_ratio"}:
                    keep = c1 if "ratio" in c1 else c2
                    drop = c2 if "ratio" in c1 else c1
                else:
                    keep, drop = c1, c2
                decisions.append(GovernanceDecision(feature=drop, action="REMOVE", reason=f"Redundant with {keep} (corr={corr.loc[c1, c2]:.3f})"))
                merged.add(drop)

        for col in numeric_cols:
            if any(d.feature == col for d in decisions):
                continue
            null_rate = df[col].isnull().mean()
            if null_rate > 0.30:
                decisions.append(GovernanceDecision(feature=col, action="REMOVE", reason=f"Excessive nulls ({null_rate:.1%})"))
                continue

        removed_set = {d.feature for d in decisions}
        for col in numeric_cols:
            if col not in removed_set:
                decisions.append(GovernanceDecision(feature=col, action="KEEP", reason="Passed governance checks"))

        diagnostics["complexity_score"] = len([d for d in decisions if d.action == "KEEP"])
        return decisions, diagnostics

    def _check_ema_state_representation(self, approved: List[str]) -> str:
        emas = [f for f in approved if f.startswith("ema_") and "ratio" not in f]
        ratios = [f for f in approved if "ratio" in f]
        if len(emas) > 4 and len(ratios) < 2:
            return "WARNING: EMAs are raw indicators. Consider using EMA-ratios as state representation."
        return "EMA state representation OK."