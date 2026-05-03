"""
Risk Agent (Phase 6)
Owns the constraint: CAPITAL PRESERVATION.
- Uses regime confidence and liquidity proximity for dynamic sizing
- Position sizing: volatility-adjusted, confidence-scaled
- Circuit breakers: drawdown tiers
- Correlation monitoring (placeholder for portfolio context)
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import pandas as pd
import numpy as np

from core.base_agent import BaseAgent, AgentResult
from core.state_store import StateStore
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)

@dataclass
class RiskMetrics:
    symbol: str
    timestamp: str
    direction: int
    raw_position_size: float
    adjusted_position_size: float
    stop_loss: float
    take_profit: float
    risk_amount: float
    regime_confidence: float
    drawdown_factor: float
    approved: bool
    reason: str

class RiskAgent(BaseAgent):
    """
    Owns the constraint: RISK-ADJUSTED POSITION SIZING.
    """

    def __init__(self, state_store: StateStore, message_bus: MessageBus,
                 capital: float = 10000.0,
                 max_risk_per_trade: float = 0.02,
                 max_drawdown_tier1: float = 0.05,
                 max_drawdown_tier2: float = 0.10,
                 hard_stop_drawdown: float = 0.145):
        super().__init__("risk_agent", state_store, message_bus)
        self.capital = capital
        self.max_risk_per_trade = max_risk_per_trade
        self.max_drawdown_tier1 = max_drawdown_tier1
        self.max_drawdown_tier2 = max_drawdown_tier2
        self.hard_stop_drawdown = hard_stop_drawdown
        self.current_drawdown = 0.0

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[RiskAgent] Applying risk management...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="RiskAgent requires signal artifact")

            artifact = self.store.load(input_artifact_id)
            bundle = artifact.data
            signal_df = bundle.get("signal_df") if isinstance(bundle, dict) else bundle
            if not isinstance(signal_df, pd.DataFrame):
                return AgentResult(success=False, message="RiskAgent expects signal DataFrame")

            # Merge with regime data to get confidence and liquidity
            # For simplicity, we look up the filtered data via parent chain
            parent_id = artifact.metadata.parent_artifact
            filtered_df = None
            if parent_id:
                try:
                    parent_art = self.store.load(parent_id)
                    fbundle = parent_art.data
                    filtered_df = fbundle.get("filtered_df") if isinstance(fbundle, dict) else None
                except Exception:
                    filtered_df = None

            risk_frames = []
            for symbol, grp in signal_df.groupby("symbol"):
                grp = grp.sort_values("timestamp").copy()
                regime_lookup = None
                if filtered_df is not None and "symbol" in filtered_df.columns:
                    regime_lookup = filtered_df[filtered_df["symbol"] == symbol]
                risked = self._apply_risk(grp, regime_lookup)
                risk_frames.append(risked)

            risk_df = pd.concat(risk_frames, ignore_index=True) if risk_frames else pd.DataFrame()

            diagnostics = self._summarize_risk(risk_df)

            artifact_id = self._produce_artifact(
                name="risk_adjusted_orders",
                data={
                    "risk_df": risk_df,
                    "capital": self.capital,
                    "drawdown": self.current_drawdown,
                },
                phase="risk",
                parent_artifact=input_artifact_id,
                tags=["risk", "sizing"],
                notes=f"Approved orders: {diagnostics['approved_count']}/{diagnostics['total_signals']}",
            )

            return AgentResult(
                success=True,
                artifact_id=artifact_id,
                message=f"Risk sizing complete. {diagnostics['summary']}",
                diagnostics=diagnostics,
            )

        except Exception as e:
            logger.exception("[RiskAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _apply_risk(self, signal_df: pd.DataFrame, regime_df: Optional[pd.DataFrame]) -> pd.DataFrame:
        out = signal_df.copy()
        out["raw_position_size"] = 0.0
        out["adjusted_position_size"] = 0.0
        out["stop_loss"] = 0.0
        out["take_profit"] = 0.0
        out["risk_amount"] = 0.0
        out["approved"] = False
        out["reason"] = ""

        for i in range(len(out)):
            row = out.iloc[i]
            direction = row.get("direction", 0)
            if direction == 0:
                out.loc[out.index[i], "reason"] = "No direction (Hold)"
                continue

            # Base sizing: risk per trade / estimated volatility
            # We use ATR proxy if available, else default
            atr_proxy = 1.5  # default
            if regime_df is not None and "atr_14" in regime_df.columns:
                # Find nearest time match
                closest = regime_df.iloc[-1] if len(regime_df) > 0 else None
                if closest is not None:
                    atr_proxy = closest.get("atr_14", 1.5)

            risk_amount = self.capital * self.max_risk_per_trade
            raw_size = risk_amount / max(atr_proxy, 0.01)

            # Confidence scaling
            conf = row.get("confidence", 0.5)
            confidence_size = raw_size * conf

            # Drawdown factor
            dd_factor = self._drawdown_factor()
            adjusted_size = confidence_size * dd_factor

            # Hard circuit breaker
            if self.current_drawdown > self.hard_stop_drawdown:
                out.loc[out.index[i], "approved"] = False
                out.loc[out.index[i], "reason"] = "HARD CIRCUIT BREAKER: drawdown exceeded"
                continue

            # Daily loss limit placeholder
            # Stop and target
            stop = atr_proxy * 1.5
            target = atr_proxy * 3.0  # 1:2 R:R

            out.loc[out.index[i], "raw_position_size"] = raw_size
            out.loc[out.index[i], "adjusted_position_size"] = adjusted_size
            out.loc[out.index[i], "stop_loss"] = stop
            out.loc[out.index[i], "take_profit"] = target
            out.loc[out.index[i], "risk_amount"] = risk_amount
            out.loc[out.index[i], "approved"] = True
            out.loc[out.index[i], "reason"] = "Risk checks passed"

        return out

    def _drawdown_factor(self) -> float:
        if self.current_drawdown <= 0.02:
            return 1.0
        elif self.current_drawdown <= self.max_drawdown_tier1:
            return 0.75
        elif self.current_drawdown <= self.max_drawdown_tier2:
            return 0.5
        else:
            return 0.25

    def _summarize_risk(self, risk_df: pd.DataFrame) -> Dict[str, Any]:
        if risk_df.empty:
            return {"summary": "No risk metrics", "approved_count": 0, "total_signals": 0}
        total = len(risk_df)
        approved = int(risk_df["approved"].sum()) if "approved" in risk_df.columns else 0
        return {
            "summary": f"Approved {approved}/{total} signals",
            "approved_count": approved,
            "total_signals": total,
            "approval_rate": round(approved / total, 3) if total else 0.0,
            "drawdown": round(self.current_drawdown, 4),
        }
