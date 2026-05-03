"""
Feedback Loop Agent (NEW)
Input: backtest results, live trading logs (when available)
Tasks:
- Detect failure patterns
- Identify regime misclassification
- Detect overfitting signals
Recommend:
- Feature changes
- Parameter adjustments
- Strategy modifications
Output: improvement plan (loops back to Feature / Regime)
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from core.base_agent import BaseAgent, AgentResult
from core.state_store import StateStore
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)

@dataclass
class ImprovementPlan:
    trigger: str
    target_phase: str  # 'features' or 'regime' or 'strategy'
    action: str
    priority: str  # high / medium / low
    rationale: str

class FeedbackAgent(BaseAgent):
    """
    Owns the constraint: CONTINUOUS IMPROVEMENT.
    - Monitors backtest and live performance
    - Detects decay / misalignment
    - Produces actionable improvement plans
    """

    def __init__(self, state_store: StateStore, message_bus: MessageBus):
        super().__init__("feedback_agent", state_store, message_bus)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[FeedbackAgent] Analyzing for improvement opportunities...")

        try:
            # Load backtest report
            backtest_id = kwargs.get("backtest_artifact_id")
            report = None
            if backtest_id:
                try:
                    bt_art = self.store.load(backtest_id)
                    report = bt_art.data.get("report") if isinstance(bt_art.data, dict) else None
                except Exception:
                    pass

            plans: List[ImprovementPlan] = []

            if report:
                sharpe = report.get("sharpe", 0)
                win_rate = report.get("win_rate", 0)
                regime_correctness = report.get("regime_correctness_score", 1.0)
                max_dd = report.get("max_drawdown", 0)

                # Failure pattern detection
                if sharpe < 0.5:
                    plans.append(ImprovementPlan(
                        trigger="low_sharpe",
                        target_phase="features",
                        action="Expand contextual features (liquidity, volume profile)",
                        priority="high",
                        rationale=f"Sharpe {sharpe:.2f} indicates weak signal quality",
                    ))

                if win_rate < 0.45 and report.get("total_trades", 0) > 50:
                    plans.append(ImprovementPlan(
                        trigger="low_winrate",
                        target_phase="strategy",
                        action="Tighten signal confirmation rules or flip regime logic",
                        priority="high",
                        rationale=f"Win rate {win_rate:.1%} below random expectation",
                    ))

                if regime_correctness < 0.6:
                    plans.append(ImprovementPlan(
                        trigger="regime_misclassification",
                        target_phase="regime",
                        action="Retrain regime boundaries or add ADX/ATR weighting",
                        priority="high",
                        rationale=f"Regime correctness {regime_correctness:.1%} too low",
                    ))

                if max_dd > 0.20:
                    plans.append(ImprovementPlan(
                        trigger="high_drawdown",
                        target_phase="risk",
                        action="Reduce position size factor or tighten stop losses",
                        priority="medium",
                        rationale=f"Max drawdown {max_dd:.1%} exceeds 20% threshold",
                    ))

                # Overfit signal: impossible Sharpe on small sample
                total_trades = report.get("total_trades", 0)
                if sharpe > 2.5 and total_trades < 200:
                    plans.append(ImprovementPlan(
                        trigger="overfit_signal",
                        target_phase="validation",
                        action="Increase minimum sample size or add cross-validation fold",
                        priority="high",
                        rationale=f"Sharpe {sharpe:.2f} on only {total_trades} trades suggests overfit",
                    ))

            if not plans:
                plans.append(ImprovementPlan(
                    trigger="healthy",
                    target_phase="none",
                    action="Continue monitoring; no changes recommended",
                    priority="low",
                    rationale="All metrics within acceptable bands",
                ))

            artifact_id = self._produce_artifact(
                name="feedback_improvement_plan",
                data={
                    "plans": [p.__dict__ for p in plans],
                    "backtest_artifact_id": backtest_id,
                },
                phase="feedback",
                parent_artifact=input_artifact_id,
                tags=["feedback", "improvement"],
                notes=f"{len(plans)} improvement recommendations generated",
            )

            return AgentResult(
                success=True,
                artifact_id=artifact_id,
                message=f"Feedback analysis complete. {len(plans)} recommendations.",
                diagnostics={
                    "plans_count": len(plans),
                    "high_priority": sum(1 for p in plans if p.priority == "high"),
                    "target_phases": list(set(p.target_phase for p in plans)),
                },
            )

        except Exception as e:
            logger.exception("[FeedbackAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)
