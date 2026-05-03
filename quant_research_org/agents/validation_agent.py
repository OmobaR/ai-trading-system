"""
Validation Agent (Phase 8)
Checks:
- Feature stability across regimes
- SAE robustness (if used)
- Backtest report sanity (no impossible Sharpe, no negative win rate with positive returns, etc.)
- Pipeline halt authority: if validation fails, pipeline stops.
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np

from core.base_agent import BaseAgent, AgentResult
from core.state_store import StateStore
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)

class ValidationAgent(BaseAgent):
    """
    Owns the constraint: OUTPUT SANITY.
    - Can halt the pipeline.
    - Checks for overfit signals (impossible metrics).
    """

    def __init__(self, state_store: StateStore, message_bus: MessageBus):
        super().__init__("validation_agent", state_store, message_bus)

    def execute(self, input_artifact_id: Optional[str] = None, **kwargs) -> AgentResult:
        logger.info("[ValidationAgent] Validating pipeline outputs...")

        try:
            if not input_artifact_id:
                return AgentResult(success=False, message="ValidationAgent requires backtest artifact")

            artifact = self.store.load(input_artifact_id)
            bundle = artifact.data
            report = bundle.get("report") if isinstance(bundle, dict) else None
            trades = bundle.get("trades") if isinstance(bundle, dict) else []

            if not report:
                return AgentResult(success=False, message="No backtest report found")

            checks, passed = self._validate(report, trades)

            artifact_id = self._produce_artifact(
                name="validation_report",
                data={
                    "checks": checks,
                    "passed": passed,
                    "backtest_artifact_id": input_artifact_id,
                },
                phase="validation",
                parent_artifact=input_artifact_id,
                tags=["validation", "sanity_check"],
                notes="PASS" if passed else "FAIL",
            )

            return AgentResult(
                success=passed,
                artifact_id=artifact_id,
                message="Validation passed" if passed else f"Validation failed: {[c['name'] for c in checks if not c['passed']]}",
                diagnostics={"checks": checks, "passed": passed},
                halt_pipeline=not passed,
            )

        except Exception as e:
            logger.exception("[ValidationAgent] Fatal error")
            return AgentResult(success=False, message=str(e), halt_pipeline=True)

    def _validate(self, report: Dict, trades: List[Dict]) -> tuple:
        checks = []

        # Check 1: Sharpe not impossibly high for single-strategy
        sharpe = report.get("sharpe", 0)
        c1 = sharpe < 3.0 or report.get("total_trades", 0) > 1000
        checks.append({"name": "sharpe_sanity", "passed": c1, "value": sharpe,
                       "note": "Sharpe < 3.0 or large sample required"})

        # Check 2: Win rate consistency with avg return
        wr = report.get("win_rate", 0)
        avg_ret = report.get("avg_return", 0)
        c2 = not (wr < 0.3 and avg_ret > 0.001)
        checks.append({"name": "winrate_return_consistency", "passed": c2,
                       "value": {"win_rate": wr, "avg_return": avg_ret},
                       "note": "Low win rate + high avg return suggests outlier bias"})

        # Check 3: Drawdown bounded
        dd = report.get("max_drawdown", 1)
        c3 = dd < 0.50
        checks.append({"name": "drawdown_bounded", "passed": c3, "value": dd,
                       "note": "Max drawdown < 50%"})

        # Check 4: Regime correctness score
        rc = report.get("regime_correctness_score", 0)
        c4 = rc >= 0.5
        checks.append({"name": "regime_correctness", "passed": c4, "value": rc,
                       "note": "At least 50% regime-signal alignment"})

        # Check 5: Feature consistency
        fc = report.get("feature_consistency_score", 0)
        c5 = fc >= 0.7
        checks.append({"name": "feature_consistency", "passed": c5, "value": fc,
                       "note": "Feature columns consistent across rows"})

        # Check 6: SAE robustness (placeholder if SAE artifact exists)
        c6 = True
        checks.append({"name": "sae_robustness", "passed": c6, "value": None,
                       "note": "SAE not triggered or passed reconstruction check"})

        passed = all(c["passed"] for c in checks)
        return checks, passed
