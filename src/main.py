# C:\Users\olugb\ai-trading-system\src\main.py
#!/usr/bin/env python3
"""
AI Trading System - Main Entry Point
Single-container service that orchestrates all trading components
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime
import os

# Fix imports to work from any directory
try:
    from market_data.market_data_agent import MarketDataAgent
    from database.redis_feature_store import UnifiedRegimeFeatureStore
    from events.event_store import EventStore
    from risk.risk_manager import RiskManagerAgent
    from strategy.nnfx_strategy import NNFXStrategy
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from market_data.market_data_agent import MarketDataAgent
    from database.redis_feature_store import UnifiedRegimeFeatureStore
    from events.event_store import EventStore
    from risk.risk_manager import RiskManagerAgent
    from strategy.nnfx_strategy import NNFXStrategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('trading_system.log')
    ]
)
logger = logging.getLogger(__name__)

class AITradingSystem:
    """Main orchestrator for the AI Trading System"""
    
    def __init__(self):
        self.running = False
        self.components = {}
        
        # Configuration
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'ai_trading_db'),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', 'password')
        }
        
        self.redis_config = {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', 6379)),
            'db': 0
        }
        
        self.mt5_config = {
            'login': int(os.getenv('MT5_LOGIN', 19345714)),
            'password': os.getenv('MT5_PASSWORD', 'bL$3Vs5)'),
            'server': os.getenv('MT5_SERVER', 'Weltrade-Demo')
        }
    
    def initialize_components(self):
        """Initialize all trading system components"""
        logger.info("Initializing AI Trading System components...")
        
        try:
            # Event Store
            self.components['event_store'] = EventStore(self.db_config)
            logger.info("Event Store initialized")
            
            # Feature Store
            self.components['feature_store'] = UnifiedRegimeFeatureStore(
                self.redis_config, 
                regime_model='comprehensive'
            )
            logger.info("Feature Store initialized")
            
            # Market Data Agent
            self.components['market_data'] = MarketDataAgent(
                self.db_config,
                self.redis_config,
                self.mt5_config,
                mode='simulate',  # Change to 'live' for production
                regime_model='comprehensive'
            )
            logger.info("Market Data Agent initialized")
            
            # Risk Manager
            self.components['risk_manager'] = RiskManagerAgent()
            logger.info("Risk Manager initialized")
            
            # Strategy Engine
            self.components['strategy'] = NNFXStrategy()
            logger.info("Strategy Engine initialized")
            
            logger.info("All components initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            return False
    
    async def run_market_data_pipeline(self):
        """Run the market data ingestion pipeline"""
        logger.info("Starting market data pipeline...")
        
        while self.running:
            try:
                # Run market data collection
                self.components['market_data'].run_simulate()
                
                # Brief pause to prevent overwhelming the system
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Market data pipeline error: {e}")
                await asyncio.sleep(10)  # Longer pause on error
    
    async def run_strategy_engine(self):
        """Run the strategy and signal generation"""
        logger.info("Starting strategy engine...")
        
        while self.running:
            try:
                # Get current regimes for all symbols
                regimes = self.components['feature_store'].get_bulk_regimes(
                    self.components['market_data'].symbols
                )
                
                # Generate trading signals based on regimes
                for symbol, regime in regimes.items():
                    if regime and "trending" in regime:
                        # In a full implementation, this would generate actual trading signals
                        logger.debug(f"{symbol} in {regime} regime - potential trading opportunity")
                
                await asyncio.sleep(10)  # Check strategies every 10 seconds
                
            except Exception as e:
                logger.error(f"Strategy engine error: {e}")
                await asyncio.sleep(30)
    
    async def run_risk_monitor(self):
        """Run continuous risk monitoring"""
        logger.info("Starting risk monitor...")
        
        while self.running:
            try:
                # Monitor portfolio risk
                # This would integrate with actual position data in production
                await asyncio.sleep(15)  # Check risk every 15 seconds
                
            except Exception as e:
                logger.error(f"Risk monitor error: {e}")
                await asyncio.sleep(30)
    
    async def run_system_health(self):
        """Monitor system health and metrics"""
        logger.info("Starting system health monitor...")
        
        while self.running:
            try:
                # Log system status
                component_status = {}
                for name, component in self.components.items():
                    component_status[name] = "active" if component else "inactive"
                
                logger.info(f"System Status: {component_status}")
                
                # Store health metrics
                health_event = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'component_status': component_status,
                    'system_uptime': time.time() - self.start_time
                }
                
                self.components['event_store'].append_event(
                    'system_health',
                    'system',
                    health_event,
                    {'source': 'health_monitor'}
                )
                
                await asyncio.sleep(60)  # Log health every minute
                
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(60)
    
    async def start(self):
        """Start the AI trading system"""
        logger.info("Starting AI Trading System...")
        
        if not self.initialize_components():
            logger.error("Failed to initialize system components")
            return False
        
        self.running = True
        self.start_time = time.time()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        try:
            # Run all system components concurrently
            await asyncio.gather(
                self.run_market_data_pipeline(),
                self.run_strategy_engine(),
                self.run_risk_monitor(),
                self.run_system_health(),
                return_exceptions=True
            )
            
        except Exception as e:
            logger.error(f"System runtime error: {e}")
        finally:
            await self.shutdown()
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    async def shutdown(self):
        """Gracefully shutdown the system"""
        logger.info("Shutting down AI Trading System...")
        
        self.running = False
        
        # Stop all components
        if 'market_data' in self.components:
            self.components['market_data'].stop()
        
        logger.info("AI Trading System shutdown complete")

def main():
    """Main entry point"""
    system = AITradingSystem()
    
    try:
        # Run the system
        asyncio.run(system.start())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal system error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
