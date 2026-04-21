#!/usr/bin/env python3
"""
AI Trading System - Multi‑Strategy Orchestrator
Full integration with rolling window, feature computation, risk management.
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
import pandas as pd
import numpy as np

# Fix imports
try:
    from market_data.market_data_agent import MarketDataAgent
    from database.redis_feature_store import UnifiedRegimeFeatureStore
    from events.event_store import EventStore
    from risk.risk_manager import RiskManagerAgent
    from strategy.nnfx_strategy import NNFXStrategy
    from strategy.sae_weighted_strategy import SAEWeightedStrategy
    from config.settings import config
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from market_data.market_data_agent import MarketDataAgent
    from database.redis_feature_store import UnifiedRegimeFeatureStore
    from events.event_store import EventStore
    from risk.risk_manager import RiskManagerAgent
    from strategy.nnfx_strategy import NNFXStrategy
    from strategy.sae_weighted_strategy import SAEWeightedStrategy
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
        self.strategies = []

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

            # Market Data Agent (with rolling window)
            agent = MarketDataAgent(
                self.db_config, self.redis_config, self.mt5_config,
                mode=self.mode,
                regime_model='comprehensive'
            )
            agent.running = True
            self.components['market_data'] = agent
            logger.info("Market Data Agent initialized")

            # Risk Manager
            self.components['risk_manager'] = self.retry_sync(lambda: RiskManagerAgent(self.redis_config))
            logger.info("Risk Manager initialized")

            # ---------- Load Strategies ----------
            strategy_list = getattr(self.config, 'STRATEGIES', ['nnfx'])
            logger.info(f"Loading strategies: {strategy_list}")
            if 'nnfx' in strategy_list:
                self.strategies.append(NNFXStrategy())
                logger.info("NNFX Strategy loaded")
            if 'sae_weighted' in strategy_list:
                # Parameters from optimization (window=60, threshold=0.5 gave good Sharpe on FX Vol)
                sae_params = {
                    'min_net_score': 32,
                    'decision_threshold': 0.56
                }
                self.strategies.append(SAEWeightedStrategy(**sae_params))
                logger.info("SAE Weighted Strategy loaded")

            logger.info(f"Total strategies loaded: {len(self.strategies)}")
            logger.info("All components initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            return False

    async def run_market_data_pipeline(self):
        """Run market data ingestion in a thread."""
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
        """
        Full strategy engine:
        - For each symbol, get rolling window DataFrame.
        - For each strategy, generate signal.
        - Approve trade with risk manager.
        - Log approved trades (execution stub).
        """
        logger.info("Starting multi‑strategy engine with feature computation...")
        agent = self.components['market_data']
        risk_mgr = self.components['risk_manager']

        while self.running:
            try:
                # Iterate over symbols that have rolling window data
                for symbol, window_list in agent.window_data.items():
                    if window_list is None or len(window_list) < 50:
                        continue
                    # Convert list of dicts to DataFrame
                    df = pd.DataFrame(window_list)
                    if df.empty:
                        continue
                    df.set_index('time', inplace=True)

                    # Run each strategy
                    for strategy in self.strategies:
                        signal = strategy.generate_signal(symbol, df, datetime.now())
                        if signal and signal.get('action') in ('BUY', 'SELL'):
                            price = df['close'].iloc[-1]
                            confidence = signal.get('confidence', 0.7)
                            # Approximate ATR for risk manager (use the latest ATR if available, else a placeholder)
                            atr = 0.01  # You could compute ATR from df here
                            # Approve trade with risk manager
                            approved_size, details = risk_mgr.approve_trade(
                                symbol=symbol,
                                atr=atr,
                                confidence=confidence,
                                price=price
                            )
                            if approved_size > 0.01:
                                logger.info(f"✅ TRADE: {signal['action']} {symbol} | "
                                            f"Size={approved_size:.3f} | Conf={confidence:.2f} | "
                                            f"Strategy={signal.get('strategy')}")
                                # TODO: Replace with actual execution (DLL bridge or MT5 order)
                                # self.execute_order(symbol, signal['action'], approved_size, price)
                            else:
                                logger.debug(f"❌ Trade rejected: {symbol} {signal['action']} | Reason={details.get('reason')}")

                await asyncio.sleep(60)  # Check every minute (align with M1 bars)

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

        # Start health server (optional)
        try:
            from monitoring.health_server import start_health_server
            risk_manager = self.components.get('risk_manager')
            start_health_server(risk_manager=risk_manager, port=8080)
        except ImportError as e:
            logger.warning(f"Health server not started: {e}")
        except Exception as e:
            logger.error(f"Failed to start health server: {e}")

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
                        help='Override config mode')
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