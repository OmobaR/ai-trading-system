# src/risk/risk_manager.py
import logging
import numpy as np
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RiskManagerAgent:
    """
    Enhanced Risk Manager with correlation monitoring, circuit breakers, and portfolio-level risk
    """
    
    def __init__(self, redis_config: Dict, risk_capital: float = 10000, 
                 max_drawdown: float = 0.15, correlation_threshold: float = 0.7,
                 max_position_size: float = 0.1, max_daily_loss: float = 0.05):
        
        self.risk_capital = risk_capital
        self.max_drawdown = max_drawdown
        self.correlation_threshold = correlation_threshold
        self.max_position_size = max_position_size  # Max 10% of capital per trade
        self.max_daily_loss = max_daily_loss
        
        # Risk state
        self.current_drawdown = 0.0
        self.daily_pnl = 0.0
        self.portfolio_positions = {}
        self.trade_history = []
        
        # Risk metrics
        self.var_95 = 0.0
        self.expected_shortfall = 0.0
        self.sharpe_ratio = 0.0
        
        logger.info(f"✅ Risk Manager initialized with {risk_capital} capital")
    
    def calculate_position_size(self, symbol: str, atr: float, confidence: float, 
                              price: float, k: float = 2.0) -> Tuple[float, Dict[str, float]]:
        """
        Calculate position size based on volatility and risk rules
        """
        try:
            # Base position size using Kelly Criterion variant
            if atr <= 0 or price <= 0:
                return 0.0, {}
            
            # Risk per trade (2% of capital)
            risk_per_trade = self.risk_capital * 0.02
            
            # Stop loss distance (1.5x ATR)
            stop_loss_distance = atr * 1.5
            
            # Base position size
            if stop_loss_distance > 0:
                base_size = risk_per_trade / stop_loss_distance
            else:
                base_size = 0.0
            
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
        """Reduce position size during drawdown periods"""
        if self.current_drawdown <= 0.02:  # < 2% DD
            return 1.0
        elif self.current_drawdown <= 0.05:  # 2-5% DD
            return 0.75
        elif self.current_drawdown <= 0.10:  # 5-10% DD
            return 0.5
        else:  # >10% DD
            return 0.25
    
    def monitor_correlation(self, symbols: List[str]) -> float:
        """
        Monitor portfolio correlation and return adjustment factor
        In production, this would use real correlation data
        """
        try:
            # Placeholder: Simulate correlation check
            # In real implementation, you'd calculate correlation matrix from returns
            if len(symbols) <= 1:
                return 1.0
            
            # Simulate high correlation scenario (20% chance)
            import random
            if random.random() < 0.2:
                logger.warning("🔄 High correlation detected in portfolio")
                return 0.5  # Reduce position sizes by 50%
            
            return 1.0
            
        except Exception as e:
            logger.error(f"Error in correlation monitoring: {e}")
            return 1.0
    
    def check_circuit_breakers(self, proposed_size: float, symbol: str) -> float:
        """
        Apply circuit breakers based on risk state
        """
        adjusted_size = proposed_size
        
        # Tier 1: 5% drawdown
        if self.current_drawdown > 0.05:
            adjusted_size *= 0.75
            logger.warning("🔴 Tier 1 circuit breaker: Reduced size by 25%")
        
        # Tier 2: 10% drawdown  
        if self.current_drawdown > 0.10:
            adjusted_size *= 0.5
            logger.warning("🔴 Tier 2 circuit breaker: Reduced size by 50%")
        
        # Tier 3: 14.5% drawdown - hard limit approach
        if self.current_drawdown > 0.145:
            logger.critical("🔴 HARD CIRCUIT BREAKER: Closing all positions")
            self.close_all_positions()
            return 0.0
        
        # Daily loss limit
        if self.daily_pnl < -self.risk_capital * self.max_daily_loss:
            logger.warning("🔴 Daily loss limit reached: No new positions")
            return 0.0
        
        return adjusted_size
    
    def close_all_positions(self):
        """Close all positions - emergency procedure"""
        logger.critical("🛑 EMERGENCY: Closing all portfolio positions")
        # In production, this would trigger execution to close all positions
        self.portfolio_positions.clear()
        
        # Log the event
        self._log_risk_event("EMERGENCY_POSITION_CLOSE", {
            'reason': 'hard_circuit_breaker',
            'drawdown': self.current_drawdown,
            'timestamp': datetime.utcnow().isoformat()
        })
    
    def update_risk_metrics(self, pnl: float, symbol: str = None):
        """Update risk metrics with new P&L"""
        self.daily_pnl += pnl
        
        # Update drawdown
        if pnl < 0:
            self.current_drawdown = min(1.0, self.current_drawdown + abs(pnl) / self.risk_capital)
        else:
            # Slowly recover from drawdown
            self.current_drawdown = max(0.0, self.current_drawdown - (abs(pnl) / self.risk_capital) * 0.1)
        
        # Update portfolio position
        if symbol:
            if pnl == 0 and symbol in self.portfolio_positions:
                # Position closed
                del self.portfolio_positions[symbol]
            elif symbol in self.portfolio_positions:
                self.portfolio_positions[symbol]['pnl'] += pnl
            else:
                self.portfolio_positions[symbol] = {'pnl': pnl, 'opened': datetime.utcnow()}
        
        # Add to trade history
        self.trade_history.append({
            'symbol': symbol,
            'pnl': pnl,
            'timestamp': datetime.utcnow(),
            'drawdown': self.current_drawdown
        })
        
        # Keep only last 1000 trades
        if len(self.trade_history) > 1000:
            self.trade_history = self.trade_history[-1000:]
    
    def calculate_var(self, confidence_level: float = 0.95) -> float:
        """Calculate Value at Risk"""
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
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def approve_trade(self, symbol: str, atr: float, confidence: float, 
                     price: float, k: float = 2.0) -> Tuple[float, Dict[str, float]]:
        """
        Main method to approve trades with risk management
        """
        # Calculate base position size
        position_size, risk_metrics = self.calculate_position_size(
            symbol, atr, confidence, price, k
        )
        
        if position_size <= 0:
            return 0.0, risk_metrics
        
        # Check correlation with existing portfolio
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
        logger.info("📊 Daily risk metrics reset")

# Example usage
if __name__ == "__main__":
    redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
    risk_manager = RiskManagerAgent(redis_config, risk_capital=10000)
    
    # Test position sizing
    size, metrics = risk_manager.approve_trade('GainX 600', atr=1.5, confidence=0.8, price=100.0)
    print(f"Approved size: {size}")
    print(f"Risk metrics: {metrics}")
    
    # Test risk report
    report = risk_manager.get_risk_report()
    print(f"Risk report: {report}")