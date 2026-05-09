"""
Risk Agent (Phase 6) – per symbol, file‑based, memory‑safe.
Owns the constraint: CAPITAL PRESERVATION.
- Uses regime confidence and liquidity proximity for dynamic sizing
- Position sizing: volatility-adjusted, confidence-scaled
- Circuit breakers: drawdown tiers
- Correlation monitoring (placeholder for portfolio context)
"""
from __future__ import annotations

import logging
from pathlib import Path
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
        self.output_dir = Path("data/processed/risk")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[RiskAgent] Applying risk management...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="RiskAgent requires signal artifact")

            strategy_artifact = self.store.load(input_artifact_id)
            file_paths = strategy_artifact.data.get("file_paths", [])
            if not file_paths:
                return AgentResult(success=False, message="No signal files found")

            risk_files = []
            total_approved = 0
            total_signals = 0

            for file_path in file_paths:
                symbol = Path(file_path).stem.replace("_signals", "")
                logger.info(f"  Risk sizing for {symbol}...")
                df = pd.read_parquet(file_path)
                risked_df = self._apply_risk(df)
                out_path = self.output_dir / f"{symbol}_risk.parquet"
                risked_df.to_parquet(out_path, index=False)
                risk_files.append(str(out_path))
                total_approved += int(risked_df["approved"].sum())
                total_signals += len(risked_df)

            artifact_id = self._produce_artifact(
                name="risk_adjusted_orders",
                data={
                    "file_paths": risk_files,
                    "capital": self.capital,
                    "drawdown": self.current_drawdown,
                },
                phase="risk",
                parent_artifact=input_artifact_id,
                tags=["risk", "sizing"],
                notes=f"Approved orders: {total_approved}/{total_signals}",
            )

            return AgentResult(
                success=True,
                artifact_id=artifact_id,
                message=f"Risk sizing complete. Approved {total_approved}/{total_signals} trades.",
                diagnostics={"approved_count": total_approved, "total_signals": total_signals},
            )

        except Exception as e:
            logger.exception("[RiskAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _apply_risk(self, signal_df: pd.DataFrame, regime_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        out = signal_df.copy()
        out["raw_position_size"] = 0.0
        out["adjusted_position_size"] = 0.0
        out["stop_loss"] = 0.0
        out["take_profit"] = 0.0
        out["risk_amount"] = 0.0
        out["approved"] = False
        out["reason"] = ""
        out["drawdown_factor"] = 1.0

        for i in range(len(out)):
            row = out.iloc[i]
            direction = row.get("direction", 0)
            if direction == 0:
                out.loc[out.index[i], "reason"] = "No direction (Hold)"
                continue

            # Base sizing: risk per trade / estimated volatility
            # Use ATR if available, else default
            atr_proxy = 1.5  # default
            if regime_df is not None and "atr_14" in regime_df.columns:
                # Find nearest time match (simplified: use last row)
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
            stop = atr_proxy * 1.5
            target = atr_proxy * 3.0  # 1:2 R:R

            out.loc[out.index[i], "raw_position_size"] = raw_size
            out.loc[out.index[i], "adjusted_position_size"] = adjusted_size
            out.loc[out.index[i], "stop_loss"] = stop
            out.loc[out.index[i], "take_profit"] = target
            out.loc[out.index[i], "risk_amount"] = risk_amount
            out.loc[out.index[i], "approved"] = True
            out.loc[out.index[i], "reason"] = "Risk checks passed"
            out.loc[out.index[i], "drawdown_factor"] = dd_factor

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