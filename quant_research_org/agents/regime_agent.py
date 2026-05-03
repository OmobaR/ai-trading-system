"""
Regime Agent (Phase 3 — upgraded)
Integrates:
- EMA hierarchy (structural + tactical)
- ADX
- Liquidity context (distance to yearly high/low)
- Future HMM hook placeholder

Classifies into:
- Trend continuation
- Weak trend / exhaustion
- Range
- Breakout
- Transition

Does NOT generate trade signals.
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, List, Any
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
    regime_duration: int  # bars in current regime
    notes: str

class RegimeAgent(BaseAgent):
    """
    Owns the constraint: REGIME CORRECTNESS.
    If regime is wrong, everything downstream is wrong.
    """

    def __init__(self, state_store: StateStore, message_bus: MessageBus):
        super().__init__("regime_agent", state_store, message_bus)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[RegimeAgent] Classifying market regimes...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="RegimeAgent requires input artifact")

            artifact = self.store.load(input_artifact_id)
            bundle = artifact.data
            df = bundle.get("approved_df") if isinstance(bundle, dict) else bundle
            if isinstance(bundle, dict) and "approved_df" in bundle:
                df = bundle["approved_df"]
            elif isinstance(bundle, pd.DataFrame):
                df = bundle
            else:
                return AgentResult(success=False, message="RegimeAgent expects DataFrame input")

            regime_frames = []
            classifications: Dict[str, List[RegimeClassification]] = {}

            for symbol, grp in df.groupby("symbol"):
                grp = grp.sort_values("time").copy()
                classified, cls_list = self._classify(grp)
                regime_frames.append(classified)
                classifications[symbol] = cls_list

            regime_df = pd.concat(regime_frames, ignore_index=True)

            diagnostics = self._summarize_regimes(classifications)

            artifact_id = self._produce_artifact(
                name="regime_labels",
                data={
                    "regime_df": regime_df,
                    "classifications": {k: [c.__dict__ for c in v] for k, v in classifications.items()},
                },
                phase="regime",
                parent_artifact=input_artifact_id,
                tags=["regime", "classification"],
                notes=f"Regimes: {diagnostics['distribution']}",
            )

            return AgentResult(
                success=True,
                artifact_id=artifact_id,
                message=f"Regime classification complete. {diagnostics['summary']}",
                diagnostics=diagnostics,
            )

        except Exception as e:
            logger.exception("[RegimeAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _classify(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[RegimeClassification]]:
        """Classify regimes row-by-row for a single symbol."""
        out = df.copy()
        n = len(out)
        regimes = ["unknown"] * n
        confidences = [0.0] * n
        transition_flags = [False] * n

        for i in range(n):
            row = out.iloc[i]
            regime, confidence, transition = self._classify_row(row, out.iloc[:i+1])
            regimes[i] = regime
            confidences[i] = confidence
            transition_flags[i] = transition

        out["regime"] = regimes
        out["regime_confidence"] = confidences
        out["transition_flag"] = transition_flags
        out["regime_duration"] = self._compute_regime_durations(regimes)

        # Build classification objects
        cls_list = []
        for i in range(n):
            cls_list.append(RegimeClassification(
                regime=regimes[i],
                confidence=confidences[i],
                transition_flag=transition_flags[i],
                regime_duration=out["regime_duration"].iloc[i],
                notes="",
            ))

        return out, cls_list

    def _classify_row(self, row: pd.Series, history: pd.DataFrame) -> Tuple[str, float, bool]:
        """Classify a single bar based on structural/tactical/contextual signals."""
        # Extract available indicators
        close = row.get("close", np.nan)
        ema_50 = row.get("ema_50", np.nan)
        ema_100 = row.get("ema_100", np.nan)
        ema_200 = row.get("ema_200", np.nan)
        ema_7 = row.get("ema_7", np.nan)
        ema_21 = row.get("ema_21", np.nan)
        ema_34 = row.get("ema_34", np.nan)
        rsi = row.get("rsi_14", 50.0)
        dist_high = row.get("dist_to_yearly_high", np.nan)
        dist_low = row.get("dist_to_yearly_low", np.nan)
        position_range = row.get("position_in_yearly_range", 0.5)

        # Structural trend score (-1 to +1)
        structural_trend = 0.0
        votes = 0
        if not np.isnan(ema_50) and not np.isnan(ema_200):
            structural_trend += 1 if ema_50 > ema_200 else -1
            votes += 1
        if not np.isnan(ema_100) and not np.isnan(ema_200):
            structural_trend += 1 if ema_100 > ema_200 else -1
            votes += 1
        if not np.isnan(ema_50) and not np.isnan(ema_100):
            structural_trend += 1 if ema_50 > ema_100 else -1
            votes += 1
        structural_trend = structural_trend / max(votes, 1) if votes > 0 else 0.0

        # Tactical momentum score
        tactical_momentum = 0.0
        t_votes = 0
        if not np.isnan(ema_7) and not np.isnan(ema_21):
            tactical_momentum += 1 if ema_7 > ema_21 else -1
            t_votes += 1
        if not np.isnan(ema_7) and not np.isnan(ema_34):
            tactical_momentum += 1 if ema_7 > ema_34 else -1
            t_votes += 1
        if not np.isnan(ema_21) and not np.isnan(ema_34):
            tactical_momentum += 1 if ema_21 > ema_34 else -1
            t_votes += 1
        tactical_momentum = tactical_momentum / max(t_votes, 1) if t_votes > 0 else 0.0

        # ADX proxy (use trend strength if available, else infer)
        adx_proxy = abs(structural_trend) * 50 + abs(tactical_momentum) * 25
        adx_proxy = min(adx_proxy, 60.0)

        # Context: distance to extremes
        near_high = not np.isnan(dist_high) and dist_high < 0.02
        near_low = not np.isnan(dist_low) and dist_low < 0.02
        mid_range = abs(position_range - 0.5) < 0.2

        # Classification logic
        if near_high or near_low:
            if abs(tactical_momentum) > 0.5 and adx_proxy > 30:
                regime = "breakout"
                confidence = 0.7 + adx_proxy / 100
            else:
                regime = "transition"
                confidence = 0.55
        elif abs(structural_trend) > 0.5 and abs(tactical_momentum) > 0.3 and adx_proxy > 25:
            regime = "trend_continuation"
            confidence = 0.6 + abs(structural_trend) * 0.3
        elif abs(structural_trend) < 0.3 and abs(tactical_momentum) < 0.3 and mid_range:
            regime = "range"
            confidence = 0.6
        elif adx_proxy < 15 and abs(tactical_momentum) < 0.3:
            regime = "weak_trend"
            confidence = 0.55
        else:
            regime = "transition"
            confidence = 0.5

        # Transition flag: if recent history shows regime change
        transition = False
        if len(history) >= 3:
            recent = history["regime"].iloc[-3:] if "regime" in history.columns else []
            if len(recent) >= 2 and len(set(recent.iloc[-2:])) > 1:
                transition = True

        confidence = min(confidence, 0.95)
        return regime, confidence, transition

    def _compute_regime_durations(self, regimes: List[str]) -> List[int]:
        durations = [1] * len(regimes)
        for i in range(1, len(regimes)):
            if regimes[i] == regimes[i - 1]:
                durations[i] = durations[i - 1] + 1
            else:
                durations[i] = 1
        return durations

    def _summarize_regimes(self, classifications: Dict[str, List[RegimeClassification]]) -> Dict[str, Any]:
        all_regimes = []
        all_confidences = []
        for sym, cls_list in classifications.items():
            for c in cls_list:
                all_regimes.append(c.regime)
                all_confidences.append(c.confidence)

        counts = {}
        for r in all_regimes:
            counts[r] = counts.get(r, 0) + 1
        total = len(all_regimes) if all_regimes else 1
        distribution = {k: round(v / total, 3) for k, v in counts.items()}

        return {
            "summary": f"{len(classifications)} symbols, {total} bars classified",
            "distribution": distribution,
            "avg_confidence": round(np.mean(all_confidences), 3) if all_confidences else 0.0,
            "transition_rate": round(sum(1 for r in all_regimes if r == "transition") / total, 3) if total else 0.0,
        }
