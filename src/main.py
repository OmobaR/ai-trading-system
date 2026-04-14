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
import random
import argparse

# Fix imports
try:
    from market_data.market_data_agent import MarketDataAgent
    from database.redis_feature_store import UnifiedRegimeFeatureStore
    from events.event_store import EventStore
    from risk.risk_manager import RiskManagerAgent
    from strategy.nnfx_strategy import NNFXStrategy
    from config.settings import config
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from market_data.market_data_agent import MarketDataAgent
    from database.redis_feature_store import UnifiedRegimeFeatureStore
    from events.event_store import EventStore
    from risk.risk_manager import RiskManagerAgent
    from strategy.nnfx_strategy import NNFXStrategy
    from config.settings import config

# Configure logging
log_dir = '/tmp'
log_file_path = os.path.join(log_dir, 'trading_system.log')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file_path)
    ]
)
logger = logging.getLogger(__name__)

class AITradingSystem:
    def __init__(self, cli_mode=None):
        self.running = False
        self.components = {}
        
        # Use config singleton
        self.config = config
        self.mode = cli_mode if cli_mode else self.config.MODE
        
        self.db_config = {
            'host': self.config.DB_HOST,
            'port': self.config.DB_PORT,
            'database': self.config.DB_NAME,
            'user': self.config.DB_USER,
            'password': self.config.DB_PASSWORD
        }
        
        self.redis_config = {
            'host': self.config.REDIS_HOST,
            'port': self.config.REDIS_PORT,
            'db': self.config.REDIS_DB
        }
        
        self.mt5_config = {
            'login': self.config.MT5_LOGIN,
            'password': self.config.MT5_PASSWORD,
            'server': self.config.MT5_SERVER
        }
    
    def retry_sync(self, func, max_retries=5, base_delay=2, exceptions=(Exception,)):
        for attempt in range(1, max_retries + 1):
            try:
                return func()
            except exceptions as e:
                if attempt == max_retries:
                    raise
                delay = base_delay * attempt + random.uniform(0, 0.5)
                logger.warning(f"Retry {attempt}/{max_retries} in {delay:.1f}s: {e}")
                time.sleep(delay)
    
    def initialize_components(self):
        logger.info("Initializing AI Trading System components...")
        try:
            self.components['event_store'] = self.retry_sync(lambda: EventStore(self.db_config))
            logger.info("Event Store initialized")
            
            self.components['feature_store'] = self.retry_sync(
                lambda: UnifiedRegimeFeatureStore(self.redis_config, regime_model='comprehensive')
            )
            logger.info("Feature Store initialized")
            
            # Create market data agent with mode from config or CLI
            agent = MarketDataAgent(
                self.db_config, self.redis_config, self.mt5_config,
                mode=self.mode,
                regime_model='comprehensive'
            )
            # CRITICAL: Set running flag to True
            agent.running = True
            self.components['market_data'] = agent
            logger.info("Market Data Agent initialized")
            
            self.components['risk_manager'] = self.retry_sync(lambda: RiskManagerAgent(self.redis_config))
            logger.info("Risk Manager initialized")
            
            self.components['strategy'] = self.retry_sync(lambda: NNFXStrategy())
            logger.info("Strategy Engine initialized")
            
            logger.info("All components initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            return False
    
    async def run_market_data_pipeline(self):
        logger.info("Starting market data pipeline...")
        agent = self.components['market_data']
        while self.running:
            try:
                await asyncio.to_thread(agent.run_simulate)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Market data pipeline error: {e}")
                await asyncio.sleep(5)
    
    async def run_strategy_engine(self):
        logger.info("Starting strategy engine...")
        while self.running:
            try:
                regimes = self.components['feature_store'].get_bulk_regimes(
                    self.components['market_data'].symbols
                )
                # Placeholder – actual signal generation can be added here
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Strategy engine error: {e}")
                await asyncio.sleep(30)
    
    async def run_risk_monitor(self):
        logger.info("Starting risk monitor...")
        while self.running:
            await asyncio.sleep(15)
    
    async def run_system_health(self):
        logger.info("Starting system health monitor...")
        while self.running:
            try:
                status = {name: "active" if comp else "inactive"
                         for name, comp in self.components.items()}
                logger.info(f"System Status: {status}")
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(60)
    
    async def start(self):
        logger.info("Starting AI Trading System...")
        if not self.initialize_components():
            return False
        
        self.running = True
        self.start_time = time.time()
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        try:
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
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        if 'market_data' in self.components:
            self.components['market_data'].running = False
    
    async def shutdown(self):
        logger.info("Shutting down AI Trading System...")
        self.running = False
        if 'market_data' in self.components:
            self.components['market_data'].stop()
        logger.info("AI Trading System shutdown complete")

def main():
    parser = argparse.ArgumentParser(description='AI Trading System')
    parser.add_argument('--mode', choices=['simulate', 'live', 'historical'],
                        help='Override config mode (simulate, live, historical)')
    args = parser.parse_args()
    
    system = AITradingSystem(cli_mode=args.mode)
    try:
        asyncio.run(system.start())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()