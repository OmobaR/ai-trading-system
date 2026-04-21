# src/risk/risk_manager.py
import logging
import numpy as np
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RiskManagerAgent:
    """
    Enhanced Risk Manager with correlation monitoring, circuit breakers, and portfolio-level risk.
    Currently in SOFT TUNING MODE (higher limits to allow more activity during calibration).
    """
    
    def __init__(self, redis_config: Dict, risk_capital: float = 10000, 
                 max_drawdown: float = 0.18, correlation_threshold: float = 0.7,
                 max_position_size: float = 0.12, max_daily_loss: float = 0.08):
        
        self.risk_capital = risk_capital
        self.max_drawdown = max_drawdown                    # Softened: 18% (was 15%)
        self.correlation_threshold = correlation_threshold
        self.max_position_size = max_position_size          # Softened: 12% (was 10%)
        self.max_daily_loss = max_daily_loss                # Softened: 8% (was 5%)
        
        # Risk state
        self.current_drawdown = 0.0
        self.daily_pnl = 0.0
        self.portfolio_positions = {}
        self.trade_history = []
        self.consecutive_losses = 0
        self.max_consecutive_losses = 5                     # Softened: 5 (was 3)
        
        # Risk metrics
        self.var_95 = 0.0
        self.expected_shortfall = 0.0
        self.sharpe_ratio = 0.0
        
        logger.info(f"✅ Risk Manager initialized with {risk_capital} capital (SOFT TUNING MODE)")
    
    def calculate_position_size(self, symbol: str, atr: float, confidence: float, 
                              price: float, k: float = 2.0) -> Tuple[float, Dict[str, float]]:
        """
        Calculate position size based on volatility and risk rules
        """
        try:
            if atr <= 0 or price <= 0:
                return 0.0, {}
            
            # Risk per trade (2% of capital)
            risk_per_trade = self.risk_capital * 0.02
            
            # Stop loss distance (1.5x ATR)
            stop_loss_distance = atr * 1.5
            
            # Base position size
            base_size = risk_per_trade / stop_loss_distance if stop_loss_distance > 0 else 0.0
            
            # Adjust for confidence
            confidence_size = base_size * confidence
            
            # Adjust for current drawdown
            drawdown_factor = self._get_drawdown_factor()
            adjusted_size = confidence_size * drawdown_factor
            
            # Apply position size limits
            max_size = self.risk_capital * self.max_position_size / price
            final_size = min(adjusted_size, max_size)
            
            # Ensure minimum lot size
            final_size = max(0.01, final_size)
            
            risk_metrics = {
                'risk_amount': risk_per_trade,
                'stop_loss_distance': stop_loss_distance,
                'base_size': base_size,
                'confidence_size': confidence_size,
                'drawdown_factor': drawdown_factor,
                'max_size': max_size,
                'final_size': final_size,
                'position_value': final_size * price
            }
            
            return final_size, risk_metrics
            
        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}")
            return 0.0, {}
    
    def _get_drawdown_factor(self) -> float:
        """Reduce position size during drawdown periods (softened recovery)"""
        if self.current_drawdown <= 0.03:   # < 3% DD
            return 1.0
        elif self.current_drawdown <= 0.08: # 3-8% DD
            return 0.80
        elif self.current_drawdown <= 0.13: # 8-13% DD
            return 0.60
        else:                               # >13% DD
            return 0.35
    
    def monitor_correlation(self, symbols: List[str]) -> float:
        """Monitor portfolio correlation and return adjustment factor"""
        try:
            if len(symbols) <= 1:
                return 1.0
            
            # Placeholder simulation (in production use real correlation matrix)
            import random
            if random.random() < 0.20:
                logger.warning("🔄 High correlation detected in portfolio")
                return 0.60  # Reduce by 40%
            
            return 1.0
            
        except Exception as e:
            logger.error(f"Error in correlation monitoring: {e}")
            return 1.0
    
    def check_circuit_breakers(self, proposed_size: float, symbol: str) -> float:
        """
        Apply circuit breakers based on risk state (softened for tuning)
        """
        adjusted_size = proposed_size
        
        # Tier 1: 6% drawdown (softened)
        if self.current_drawdown > 0.06:
            adjusted_size *= 0.80
            logger.warning("🔴 Tier 1 circuit breaker: Reduced size by 20%")
        
        # Tier 2: 12% drawdown (softened)
        if self.current_drawdown > 0.12:
            adjusted_size *= 0.60
            logger.warning("🔴 Tier 2 circuit breaker: Reduced size by 40%")
        
        # Tier 3: 16% drawdown - hard limit (softened)
        if self.current_drawdown > 0.16:
            logger.critical("🔴 HARD CIRCUIT BREAKER: Closing all positions")
            self.close_all_positions()
            return 0.0
        
        # Daily loss limit (softened)
        if self.daily_pnl < -self.risk_capital * self.max_daily_loss:
            logger.warning("🔴 Daily loss limit reached: No new positions")
            return 0.0
        
        # Consecutive losses check
        if self.consecutive_losses >= self.max_consecutive_losses:
            logger.warning("🔴 Max consecutive losses reached")
            return 0.0
        
        return adjusted_size
    
    def close_all_positions(self):
        """Close all positions - emergency procedure"""
        logger.critical("🛑 EMERGENCY: Closing all portfolio positions")
        self.portfolio_positions.clear()
        
        self._log_risk_event("EMERGENCY_POSITION_CLOSE", {
            'reason': 'hard_circuit_breaker',
            'drawdown': self.current_drawdown,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    def update_risk_metrics(self, pnl: float, symbol: str = None):
        """Update risk metrics with new P&L"""
        self.daily_pnl += pnl
        
        if pnl < 0:
            self.current_drawdown = min(1.0, self.current_drawdown + abs(pnl) / self.risk_capital)
            self.consecutive_losses += 1
        else:
            # Recover from drawdown
            self.current_drawdown = max(0.0, self.current_drawdown - (abs(pnl) / self.risk_capital) * 0.12)
            if self.consecutive_losses > 0:
                self.consecutive_losses = max(0, self.consecutive_losses - 1)
        
        # Update portfolio position
        if symbol:
            if symbol in self.portfolio_positions:
                self.portfolio_positions[symbol]['pnl'] += pnl
                if pnl == 0:  # closed
                    del self.portfolio_positions[symbol]
            else:
                self.portfolio_positions[symbol] = {'pnl': pnl, 'opened': datetime.utcnow()}
        
        # Add to trade history
        self.trade_history.append({
            'symbol': symbol,
            'pnl': pnl,
            'timestamp': datetime.utcnow(),
            'drawdown': self.current_drawdown
        })
        
        if len(self.trade_history) > 1000:
            self.trade_history = self.trade_history[-1000:]
    
    def calculate_var(self, confidence_level: float = 0.95) -> float:
        if len(self.trade_history) < 30:
            return 0.0
        returns = [trade['pnl'] / self.risk_capital for trade in self.trade_history[-100:]]
        self.var_95 = np.percentile(returns, (1 - confidence_level) * 100)
        return self.var_95
    
    def get_risk_report(self) -> Dict[str, Any]:
        """Generate comprehensive risk report"""
        var_95 = self.calculate_var(0.95)
        
        return {
            'current_drawdown': self.current_drawdown,
            'daily_pnl': self.daily_pnl,
            'active_positions': len(self.portfolio_positions),
            'var_95': var_95,
            'max_position_size': self.max_position_size,
            'max_daily_loss': self.max_daily_loss,
            'total_trades': len(self.trade_history),
            'winning_trades': len([t for t in self.trade_history if t['pnl'] > 0]),
            'losing_trades': len([t for t in self.trade_history if t['pnl'] < 0]),
            'consecutive_losses': self.consecutive_losses,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def approve_trade(self, symbol: str, atr: float, confidence: float, 
                     price: float, k: float = 2.0) -> Tuple[float, Dict[str, float]]:
        """
        Main method to approve trades with risk management
        """
        position_size, risk_metrics = self.calculate_position_size(
            symbol, atr, confidence, price, k
        )
        
        if position_size <= 0:
            return 0.0, risk_metrics
        
        # Check correlation
        portfolio_symbols = list(self.portfolio_positions.keys()) + [symbol]
        correlation_factor = self.monitor_correlation(portfolio_symbols)
        position_size *= correlation_factor
        
        # Apply circuit breakers
        approved_size = self.check_circuit_breakers(position_size, symbol)
        
        risk_metrics.update({
            'correlation_factor': correlation_factor,
            'approved_size': approved_size,
            'circuit_breaker_applied': position_size != approved_size
        })
        
        return approved_size, risk_metrics
    
    def _log_risk_event(self, event_type: str, data: Dict):
        """Log risk events"""
        logger.info(f"📊 Risk Event: {event_type} - {data}")
    
    def reset_daily_metrics(self):
        """Reset daily metrics (call at start of trading day)"""
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        logger.info("📊 Daily risk metrics reset (SOFT TUNING MODE)")

# Example usage
if __name__ == "__main__":
    redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
    risk_manager = RiskManagerAgent(redis_config, risk_capital=10000)
    
    size, metrics = risk_manager.approve_trade('GainX 600', atr=1.5, confidence=0.8, price=100.0)
    print(f"Approved size: {size}")
    print(f"Risk metrics: {metrics}")
    
    report = risk_manager.get_risk_report()
    print(f"Risk report: {report}")