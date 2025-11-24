# tests/unit/test_risk_manager.py
import pytest
import sys
import os
from unittest.mock import Mock, patch

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.risk.risk_manager import RiskManagerAgent

class TestRiskManagerAgent:
    @pytest.fixture
    def risk_manager(self):
        redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
        return RiskManagerAgent(redis_config, risk_capital=10000)
    
    def test_initialization(self, risk_manager):
        """Test risk manager initialization"""
        assert risk_manager.risk_capital == 10000
        assert risk_manager.max_drawdown == 0.15
        assert risk_manager.max_position_size == 0.1
        assert risk_manager.current_drawdown == 0.0
    
    def test_calculate_position_size(self, risk_manager):
        """Test position size calculation"""
        size, metrics = risk_manager.calculate_position_size(
            symbol='TEST', 
            atr=1.5, 
            confidence=0.8, 
            price=100.0
        )
        
        assert size > 0
        assert isinstance(metrics, dict)
        assert 'risk_amount' in metrics
        assert 'stop_loss_distance' in metrics
        assert metrics['risk_amount'] == 200.0  # 2% of 10000
    
    def test_calculate_position_size_zero_atr(self, risk_manager):
        """Test position size with zero ATR"""
        size, metrics = risk_manager.calculate_position_size(
            symbol='TEST', 
            atr=0.0, 
            confidence=0.8, 
            price=100.0
        )
        
        assert size == 0.0
        assert metrics == {}
    
    def test_drawdown_factor_calculation(self, risk_manager):
        """Test drawdown factor calculation"""
        # Test different drawdown levels
        risk_manager.current_drawdown = 0.01  # 1% DD
        assert risk_manager._get_drawdown_factor() == 1.0
        
        risk_manager.current_drawdown = 0.04  # 4% DD  
        assert risk_manager._get_drawdown_factor() == 0.75
        
        risk_manager.current_drawdown = 0.08  # 8% DD
        assert risk_manager._get_drawdown_factor() == 0.5
        
        risk_manager.current_drawdown = 0.12  # 12% DD
        assert risk_manager._get_drawdown_factor() == 0.25
    
    def test_circuit_breakers(self, risk_manager):
        """Test circuit breaker functionality"""
        # Test normal conditions
        size = risk_manager.check_circuit_breakers(1.0, 'TEST')
        assert size == 1.0
        
        # Test tier 1 breaker
        risk_manager.current_drawdown = 0.06
        size = risk_manager.check_circuit_breakers(1.0, 'TEST')
        assert size == 0.75
        
        # Test tier 2 breaker
        risk_manager.current_drawdown = 0.11
        size = risk_manager.check_circuit_breakers(1.0, 'TEST')
        assert size == 0.5
        
        # Test hard breaker
        risk_manager.current_drawdown = 0.15
        size = risk_manager.check_circuit_breakers(1.0, 'TEST')
        assert size == 0.0
    
    def test_approve_trade(self, risk_manager):
        """Test complete trade approval process"""
        approved_size, metrics = risk_manager.approve_trade(
            symbol='TEST',
            atr=1.5,
            confidence=0.8,
            price=100.0
        )
        
        assert approved_size >= 0
        assert isinstance(metrics, dict)
        assert 'approved_size' in metrics
        assert 'correlation_factor' in metrics
    
    def test_update_risk_metrics(self, risk_manager):
        """Test risk metrics update"""
        initial_drawdown = risk_manager.current_drawdown
        initial_daily_pnl = risk_manager.daily_pnl
        
        # Test positive P&L
        risk_manager.update_risk_metrics(100.0, 'TEST')
        assert risk_manager.daily_pnl == 100.0
        assert risk_manager.current_drawdown < initial_drawdown  # Should improve
        
        # Test negative P&L
        risk_manager.update_risk_metrics(-50.0, 'TEST')
        assert risk_manager.daily_pnl == 50.0
        assert 'TEST' in risk_manager.portfolio_positions
    
    def test_risk_report(self, risk_manager):
        """Test risk report generation"""
        report = risk_manager.get_risk_report()
        
        assert isinstance(report, dict)
        assert 'current_drawdown' in report
        assert 'daily_pnl' in report
        assert 'active_positions' in report
        assert 'var_95' in report
    
    def test_var_calculation(self, risk_manager):
        """Test Value at Risk calculation"""
        # Add some trade history
        for i in range(50):
            pnl = 10.0 if i % 2 == 0 else -5.0
            risk_manager.update_risk_metrics(pnl, f'SYMBOL_{i}')
        
        var = risk_manager.calculate_var(0.95)
        assert isinstance(var, float)
    
    def test_close_all_positions(self, risk_manager):
        """Test emergency position close"""
        # Add some positions
        risk_manager.portfolio_positions = {
            'SYMBOL1': {'pnl': 100, 'opened': '2024-01-01'},
            'SYMBOL2': {'pnl': -50, 'opened': '2024-01-01'}
        }
        
        risk_manager.close_all_positions()
        assert len(risk_manager.portfolio_positions) == 0
    
    def test_reset_daily_metrics(self, risk_manager):
        """Test daily metrics reset"""
        risk_manager.daily_pnl = 500.0
        risk_manager.reset_daily_metrics()
        assert risk_manager.daily_pnl == 0.0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])