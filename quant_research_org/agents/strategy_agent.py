"""
Strategy Agent (Phase 5)
Uses: regime, filtered data, approved features.

CRITICAL CONSTRAINT: Strategy cannot override regime or filters.
- Strategy receives regime labels as immutable context
- Generates directional signals with confidence scores
- Position sizing recommendations go to Risk Agent, not executed here
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
class Signal:
    direction: int  # 1 Buy, -1 Sell, 0 Hold
    confidence: float
    regime: str
    symbol: str
    timestamp: str
    rationale: str

class StrategyAgent(BaseAgent):
    """
    Owns the constraint: SIGNAL LOGIC CONSISTENCY with REGIME.
    - Trend continuation → trend-following signals
    - Range → mean-reversion signals
    - Weak trend / Transition → no signal (Hold)
    - Breakout → momentum continuation
    """

    def __init__(self, state_store: StateStore, message_bus: MessageBus):
        super().__init__("strategy_agent", state_store, message_bus)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[StrategyAgent] Generating trading signals...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="StrategyAgent requires filtered data artifact")

            artifact = self.store.load(input_artifact_id)
            bundle = artifact.data
            df = bundle.get("filtered_df") if isinstance(bundle, dict) else bundle
            if not isinstance(df, pd.DataFrame):
                return AgentResult(success=False, message="StrategyAgent expects DataFrame")

            signals: List[Signal] = []
            for symbol, grp in df.groupby("symbol"):
                grp = grp.sort_values("time").copy()
                sym_signals = self._generate_signals(grp)
                signals.extend(sym_signals)

            signal_df = pd.DataFrame([s.__dict__ for s in signals])

            diagnostics = self._summarize_signals(signals)

            artifact_id = self._produce_artifact(
                name="strategy_signals",
                data={
                    "signal_df": signal_df,
                    "signals": [s.__dict__ for s in signals],
                },
                phase="strategy",
                parent_artifact=input_artifact_id,
                tags=["signals", "strategy"],
                notes=f"Generated {len(signals)} signals: {diagnostics['action_counts']}",
            )

            return AgentResult(
                success=True,
                artifact_id=artifact_id,
                message=f"Signal generation complete. {diagnostics['summary']}",
                diagnostics=diagnostics,
            )

        except Exception as e:
            logger.exception("[StrategyAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _generate_signals(self, df: pd.DataFrame) -> List[Signal]:
        signals = []
        for i in range(len(df)):
            row = df.iloc[i]
            regime = row.get("regime", "unknown")
            confidence = row.get("regime_confidence", 0.0)
            symbol = row.get("symbol", "UNKNOWN")
            timestamp = row.get("time", pd.NaT)
            close = row.get("close", np.nan)
            rsi = row.get("rsi_14", 50.0)
            ema_7 = row.get("ema_7", np.nan)
            ema_21 = row.get("ema_21", np.nan)

            direction = 0
            rationale = ""

            if regime == "trend_continuation":
                if not np.isnan(ema_7) and not np.isnan(ema_21):
                    if ema_7 > ema_21 and rsi < 70:
                        direction = 1
                        rationale = "Trend up, EMA7>EMA21, RSI not overbought"
                    elif ema_7 < ema_21 and rsi > 30:
                        direction = -1
                        rationale = "Trend down, EMA7<EMA21, RSI not oversold"
                    else:
                        rationale = "Trend conditions unclear"
                else:
                    rationale = "Missing EMA data"

            elif regime == "range":
                position = row.get("position_in_yearly_range", 0.5)
                if position > 0.7 and rsi > 60:
                    direction = -1
                    rationale = "Range, near top, RSI elevated"
                elif position < 0.3 and rsi < 40:
                    direction = 1
                    rationale = "Range, near bottom, RSI depressed"
                else:
                    rationale = "Range, mid-zone, no edge"

            elif regime == "breakout":
                if not np.isnan(ema_7) and not np.isnan(close):
                    if close > ema_7 * 1.01:
                        direction = 1
                        rationale = "Breakout continuation, price above EMA7"
                    elif close < ema_7 * 0.99:
                        direction = -1
                        rationale = "Breakout continuation, price below EMA7"
                    else:
                        rationale = "Breakout but price near EMA7"

            elif regime in ("weak_trend", "transition"):
                direction = 0
                rationale = f"Regime '{regime}' → no signal"

            else:
                direction = 0
                rationale = f"Unknown regime '{regime}'"

            sig_confidence = confidence * 0.8 if direction != 0 else confidence * 0.3
            signals.append(Signal(
                direction=direction,
                confidence=round(sig_confidence, 3),
                regime=regime,
                symbol=symbol,
                timestamp=str(timestamp),
                rationale=rationale,
            ))

        return signals

    def _summarize_signals(self, signals: List[Signal]) -> Dict[str, Any]:
        if not signals:
            return {"summary": "No signals generated", "action_counts": {}}
        buys = sum(1 for s in signals if s.direction == 1)
        sells = sum(1 for s in signals if s.direction == -1)
        holds = sum(1 for s in signals if s.direction == 0)
        avg_conf = np.mean([s.confidence for s in signals if s.direction != 0]) if (buys + sells) > 0 else 0.0
        return {
            "summary": f"Buys={buys}, Sells={sells}, Holds={holds}",
            "action_counts": {"buy": buys, "sell": sells, "hold": holds},
            "avg_signal_confidence": round(float(avg_conf), 3),
            "signal_rate": round((buys + sells) / len(signals), 3),
        }
