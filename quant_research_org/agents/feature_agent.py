"""
Feature Agent (Phase 2)
Builds features in 3 layers:
1. Structural: EMA 50, 100, 200
2. Tactical: EMA 7, 21, 34, RSI phases
3. Contextual: Yearly High/Low distance, Candle direction relative to liquidity

Key constraint: This agent does NOT decide what stays. It only proposes.
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
class FeatureSchema:
    name: str
    layer: str  # structural / tactical / contextual
    formula: str
    dependencies: List[str]

class FeatureAgent(BaseAgent):
    """
    Owns the constraint: FEATURE COMPLETENESS and CORRECTNESS.
    - Computes all 3-layer features
    - Classifies each feature by layer
    - Passes full feature set to Governance; does NOT filter.
    """

    def __init__(self, state_store: StateStore, message_bus: MessageBus):
        super().__init__("feature_agent", state_store, message_bus)
        self.schema: List[FeatureSchema] = []

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[FeatureAgent] Starting feature engineering...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="FeatureAgent requires input_artifact_id (clean dataset)")

            artifact = self.store.load(input_artifact_id)
            df = artifact.data
            if not isinstance(df, pd.DataFrame):
                return AgentResult(success=False, message="Input data is not a DataFrame")

            # Build features per symbol
            feature_frames = []
            for symbol, grp in df.groupby("symbol"):
                grp = grp.sort_values("time").copy()
                featured = self._build_features(grp)
                feature_frames.append(featured)

            full_features = pd.concat(feature_frames, ignore_index=True)

            # Schema documentation
            self.schema = self._build_schema(full_features)

            diagnostics = {
                "total_features": len(full_features.columns) - len(df.columns),
                "structural_features": len([s for s in self.schema if s.layer == "structural"]),
                "tactical_features": len([s for s in self.schema if s.layer == "tactical"]),
                "contextual_features": len([s for s in self.schema if s.layer == "contextual"]),
                "symbols": full_features["symbol"].nunique(),
                "rows": len(full_features),
            }

            artifact_id = self._produce_artifact(
                name="proposed_feature_set",
                data={
                    "feature_df": full_features,
                    "schema": [s.__dict__ for s in self.schema],
                },
                phase="features",
                parent_artifact=input_artifact_id,
                tags=["features", "proposed", "ema_stack"],
                notes=f"Proposed {diagnostics['total_features']} features across 3 layers",
            )

            # Explicitly request governance review
            self._request_governance(artifact_id)

            return AgentResult(
                success=True,
                artifact_id=artifact_id,
                message=f"Proposed {diagnostics['total_features']} features. Awaiting governance.",
                diagnostics=diagnostics,
            )

        except Exception as e:
            logger.exception("[FeatureAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute 3-layer feature stack for a single symbol's data."""
        out = df.copy()
        close = out["close"]
        high = out["high"]
        low = out["low"]
        open_p = out["open"]

        # ===== 1. STRUCTURAL: EMA 50, 100, 200 =====
        for period in [50, 100, 200]:
            out[f"ema_{period}"] = close.ewm(span=period, adjust=False).mean()

        out["ema_50_200_ratio"] = out["ema_50"] / out["ema_200"]
        out["ema_50_100_ratio"] = out["ema_50"] / out["ema_100"]

        # ===== 2. TACTICAL: EMA 7, 21, 34, RSI =====
        for period in [7, 21, 34]:
            out[f"ema_{period}"] = close.ewm(span=period, adjust=False).mean()

        out["ema_7_21_ratio"] = out["ema_7"] / out["ema_21"]
        out["ema_7_34_ratio"] = out["ema_7"] / out["ema_34"]
        out["ema_21_34_ratio"] = out["ema_21"] / out["ema_34"]

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=14, min_periods=1).mean()
        avg_loss = loss.rolling(window=14, min_periods=1).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        out["rsi_14"] = 100 - (100 / (1 + rs))
        out["rsi_14"] = out["rsi_14"].fillna(50.0)

        # RSI phases
        out["rsi_phase"] = pd.cut(
            out["rsi_14"],
            bins=[-np.inf, 30, 45, 55, 70, np.inf],
            labels=["oversold", "weak_bull", "neutral", "weak_bear", "overbought"],
        )
        # One-hot encode RSI phase
        rsi_dummies = pd.get_dummies(out["rsi_phase"], prefix="rsi")
        out = pd.concat([out, rsi_dummies], axis=1)
        out = out.drop(columns=["rsi_phase"])

        # ===== 3. CONTEXTUAL: Yearly H/L, Liquidity =====
        out["yearly_high"] = high.rolling(window=252, min_periods=1).max()
        out["yearly_low"] = low.rolling(window=252, min_periods=1).min()
        out["dist_to_yearly_high"] = (out["yearly_high"] - close) / out["yearly_high"]
        out["dist_to_yearly_low"] = (close - out["yearly_low"]) / out["yearly_low"]
        out["position_in_yearly_range"] = (close - out["yearly_low"]) / (out["yearly_high"] - out["yearly_low"]).replace(0, np.nan)
        out["position_in_yearly_range"] = out["position_in_yearly_range"].fillna(0.5)

        # Candle direction relative to liquidity
        out["candle_direction"] = np.where(close > open_p, 1, np.where(close < open_p, -1, 0))
        out["liquidity_proximity"] = 1 - 2 * np.abs(out["position_in_yearly_range"] - 0.5)
        out["candle_vs_liquidity"] = out["candle_direction"] * out["liquidity_proximity"]

        # Derived features
        out["body_size"] = np.abs(close - open_p)
        out["upper_wick"] = high - np.maximum(close, open_p)
        out["lower_wick"] = np.minimum(close, open_p) - low
        out["true_range"] = np.maximum(high - low, np.maximum(np.abs(high - close.shift(1)), np.abs(low - close.shift(1))))
        out["atr_14"] = out["true_range"].rolling(window=14, min_periods=1).mean()

        return out

    def _build_schema(self, df: pd.DataFrame) -> List[FeatureSchema]:
        """Document feature provenance."""
        structural = {"ema_50", "ema_100", "ema_200", "ema_50_200_ratio", "ema_50_100_ratio"}
        tactical = {"ema_7", "ema_21", "ema_34", "ema_7_21_ratio", "ema_7_34_ratio", "ema_21_34_ratio",
                    "rsi_14", "rsi_oversold", "rsi_weak_bull", "rsi_neutral", "rsi_weak_bear", "rsi_overbought"}
        contextual = {"yearly_high", "yearly_low", "dist_to_yearly_high", "dist_to_yearly_low",
                      "position_in_yearly_range", "candle_direction", "liquidity_proximity",
                      "candle_vs_liquidity", "body_size", "upper_wick", "lower_wick", "true_range", "atr_14"}

        schema = []
        for col in df.columns:
            if col in ["time", "symbol", "open", "high", "low", "close", "volume"]:
                continue
            if col in structural:
                layer = "structural"
            elif col in tactical:
                layer = "tactical"
            elif col in contextual:
                layer = "contextual"
            else:
                layer = "derived"
            schema.append(FeatureSchema(name=col, layer=layer, formula="see FeatureAgent._build_features", dependencies=["close", "high", "low"]))
        return schema
