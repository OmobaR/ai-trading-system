"""
Strategy Agent (Phase 5) – per symbol, file‑based.
Uses: regime, filtered data, approved features.
CRITICAL CONSTRAINT: Strategy cannot override regime or filters.
- Strategy receives regime labels as immutable context
- Generates directional signals with confidence scores
- Position sizing recommendations go to Risk Agent, not executed here
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
        self.output_dir = Path("data/processed/strategy")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[StrategyAgent] Generating trading signals...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="StrategyAgent requires filtered data artifact")

            filter_artifact = self.store.load(input_artifact_id)
            file_paths = filter_artifact.data.get("file_paths", [])
            if not file_paths:
                return AgentResult(success=False, message="No filtered files found")

            signal_files = []
            all_signals = []

            for file_path in file_paths:
                symbol = Path(file_path).stem.replace("_filtered", "")
                logger.info(f"  Generating signals for {symbol}...")
                df = pd.read_parquet(file_path)
                sym_signals = self._generate_signals(df)
                out_df = pd.DataFrame([s.__dict__ for s in sym_signals])
                out_path = self.output_dir / f"{symbol}_signals.parquet"
                out_df.to_parquet(out_path, index=False)
                signal_files.append(str(out_path))
                all_signals.extend(sym_signals)

            diagnostics = self._summarize_signals(all_signals)

            artifact_id = self._produce_artifact(
                name="strategy_signals",
                data={
                    "file_paths": signal_files,
                    "signals": [s.__dict__ for s in all_signals],
                },
                phase="strategy",
                parent_artifact=input_artifact_id,
                tags=["signals", "strategy"],
                notes=f"Generated {len(all_signals)} signals: {diagnostics['action_counts']}",
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