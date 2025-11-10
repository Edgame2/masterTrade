"""
Generate Bitcoin Correlation Trading Strategies

This script creates multiple strategies that focus on trading altcoins based on 
their correlation with Bitcoin price movements.
"""

import asyncio
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any

import structlog

# Setup logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

# Import from local modules
from postgres_database import Database
from models import StrategyConfig


class BTCCorrelationStrategyGenerator:
    """Generate Bitcoin correlation-based trading strategies"""
    
    def __init__(self):
        self.database = Database()
        self.btc_correlation_strategies = []
        
    async def initialize(self):
        """Initialize database connection"""
        await self.database.connect()
        logger.info("Database connection established")
        
    async def generate_strategies(self) -> List[Dict[str, Any]]:
        """Generate multiple BTC correlation strategies"""
        
        strategies = [
            # Strategy 1: High Positive Correlation - Momentum Following
            {
                "name": "BTC Momentum Follower",
                "type": "btc_correlation",
                "description": "Trades altcoins with high positive BTC correlation when BTC shows strong momentum",
                "parameters": {
                    "correlation_threshold": 0.7,  # High positive correlation
                    "correlation_period": "7d",    # 7-day rolling correlation
                    "btc_momentum_period": "4h",   # 4-hour BTC momentum check
                    "btc_momentum_threshold": 2.0, # 2% BTC price change
                    "entry_signal": "btc_strong_uptrend",
                    "exit_signal": "btc_momentum_weakens",
                    "position_size": 0.02,         # 2% of portfolio per trade
                    "stop_loss": 0.03,             # 3% stop loss
                    "take_profit": 0.06,           # 6% take profit (2:1 R/R)
                    "max_positions": 3,
                    "min_volume_24h": 1000000,     # $1M minimum 24h volume
                    "correlation_update_interval": "1h"
                },
                "symbols": ["ETHUSDC", "BNBUSDC", "ADAUSDC", "SOLUSDC", "DOTUSDC", 
                           "AVAXUSDC", "MATICUSDC", "LINKUSDC", "ATOMUSDC"],
                "is_active": False  # Start inactive for testing
            },
            
            # Strategy 2: Negative Correlation - Counter-Trend
            {
                "name": "BTC Inverse Trader",
                "type": "btc_correlation",
                "description": "Trades assets with negative BTC correlation for diversification",
                "parameters": {
                    "correlation_threshold": -0.5,  # Negative correlation
                    "correlation_period": "14d",    # 14-day rolling correlation
                    "btc_trend_period": "1d",       # Daily BTC trend
                    "entry_signal": "btc_downtrend_and_negative_correlation",
                    "exit_signal": "btc_reversal",
                    "position_size": 0.015,         # 1.5% of portfolio per trade
                    "stop_loss": 0.04,              # 4% stop loss
                    "take_profit": 0.08,            # 8% take profit
                    "max_positions": 2,
                    "min_volume_24h": 500000,
                    "correlation_update_interval": "4h",
                    "hedge_mode": True              # Use as BTC hedge
                },
                "symbols": ["ETHUSDC", "BNBUSDC", "XRPUSDC", "ADAUSDC", "DOGEUSDC"],
                "is_active": False
            },
            
            # Strategy 3: Correlation Divergence
            {
                "name": "BTC Correlation Divergence",
                "type": "btc_correlation",
                "description": "Identifies and trades divergences between altcoin price and expected correlation with BTC",
                "parameters": {
                    "correlation_threshold": 0.6,   # Moderate positive correlation
                    "correlation_period": "30d",    # 30-day baseline correlation
                    "short_correlation_period": "3d", # 3-day recent correlation
                    "divergence_threshold": 0.3,    # 30% divergence in correlation
                    "btc_price_change_min": 1.5,    # Minimum 1.5% BTC price change
                    "entry_signal": "correlation_divergence_detected",
                    "exit_signal": "correlation_normalized",
                    "position_size": 0.025,         # 2.5% of portfolio per trade
                    "stop_loss": 0.035,             # 3.5% stop loss
                    "take_profit": 0.07,            # 7% take profit
                    "max_positions": 4,
                    "min_volume_24h": 2000000,
                    "correlation_update_interval": "30m",
                    "mean_reversion": True
                },
                "symbols": ["ETHUSDC", "BNBUSDC", "SOLUSDC", "AVAXUSDC", "LINKUSDC", 
                           "UNIUSDC", "AAVEUSDC", "DOTUSDC"],
                "is_active": False
            },
            
            # Strategy 4: High Correlation Beta Play
            {
                "name": "BTC Beta Amplifier",
                "type": "btc_correlation",
                "description": "Trades high-beta altcoins that amplify BTC movements during strong trends",
                "parameters": {
                    "correlation_threshold": 0.8,   # Very high correlation
                    "beta_threshold": 1.5,          # 1.5x BTC volatility
                    "correlation_period": "14d",
                    "btc_trend_strength": "strong", # Only trade in strong BTC trends
                    "btc_trend_period": "1d",
                    "volatility_period": "7d",
                    "entry_signal": "strong_btc_trend_with_high_beta",
                    "exit_signal": "trend_weakening",
                    "position_size": 0.03,          # 3% of portfolio per trade
                    "stop_loss": 0.05,              # 5% stop loss (higher due to volatility)
                    "take_profit": 0.10,            # 10% take profit (2:1 R/R)
                    "max_positions": 2,
                    "min_volume_24h": 3000000,
                    "correlation_update_interval": "2h",
                    "trailing_stop": 0.03           # 3% trailing stop to lock in profits
                },
                "symbols": ["SOLUSDC", "AVAXUSDC", "LINKUSDC", "AAVEUSDC", "UNIUSDC", "SUSHIUSDC"],
                "is_active": False
            },
            
            # Strategy 5: Correlation Stability Scanner
            {
                "name": "BTC Stable Correlator",
                "type": "btc_correlation",
                "description": "Trades assets with stable, consistent correlation to BTC across timeframes",
                "parameters": {
                    "correlation_threshold": 0.65,
                    "correlation_stability": 0.15,  # Max 15% correlation variance
                    "timeframes": ["1d", "7d", "30d"], # Multiple timeframe analysis
                    "btc_trend_confirmation": True,
                    "entry_signal": "stable_correlation_confirmed",
                    "exit_signal": "correlation_instability",
                    "position_size": 0.02,
                    "stop_loss": 0.025,             # 2.5% stop loss (lower risk)
                    "take_profit": 0.05,            # 5% take profit (2:1 R/R)
                    "max_positions": 5,
                    "min_volume_24h": 1500000,
                    "correlation_update_interval": "6h",
                    "risk_level": "low"
                },
                "symbols": ["ETHUSDC", "BNBUSDC", "ADAUSDC", "DOTUSDC", "MATICUSDC", 
                           "ATOMUSDC", "LTCUSDC"],
                "is_active": False
            },
            
            # Strategy 6: BTC Breakout Correlation Play
            {
                "name": "BTC Breakout Correlator",
                "type": "btc_correlation",
                "description": "Trades highly correlated altcoins during BTC breakout events",
                "parameters": {
                    "correlation_threshold": 0.75,
                    "correlation_period": "7d",
                    "btc_breakout_period": "4h",
                    "btc_resistance_threshold": 0.02, # 2% above resistance
                    "volume_surge_multiplier": 1.5,   # 1.5x average volume
                    "entry_signal": "btc_breakout_with_volume",
                    "exit_signal": "momentum_exhaustion",
                    "position_size": 0.035,           # 3.5% of portfolio per trade
                    "stop_loss": 0.04,
                    "take_profit": 0.08,
                    "max_positions": 3,
                    "min_volume_24h": 2500000,
                    "correlation_update_interval": "1h",
                    "breakout_confirmation_candles": 2
                },
                "symbols": ["ETHUSDC", "SOLUSDC", "AVAXUSDC", "LINKUSDC", "UNIUSDC"],
                "is_active": False
            },
            
            # Strategy 7: Low Correlation Portfolio Balancer
            {
                "name": "BTC Low Correlation Hedge",
                "type": "btc_correlation",
                "description": "Maintains positions in low-correlation assets for portfolio diversification",
                "parameters": {
                    "correlation_threshold": 0.3,   # Low correlation
                    "max_correlation": 0.5,         # Upper bound
                    "correlation_period": "30d",
                    "rebalance_interval": "1d",
                    "target_allocation": 0.20,      # 20% of portfolio in low-correlation assets
                    "entry_signal": "low_correlation_maintained",
                    "exit_signal": "correlation_increases",
                    "position_size": 0.04,          # 4% per position
                    "stop_loss": 0.06,
                    "take_profit": 0.12,
                    "max_positions": 5,
                    "min_volume_24h": 1000000,
                    "correlation_update_interval": "12h",
                    "portfolio_hedge": True
                },
                "symbols": ["ETHUSDC", "XRPUSDC", "ADAUSDC", "LTCUSDC", "DOGEUSDC"],
                "is_active": False
            },
            
            # Strategy 8: Correlation Mean Reversion
            {
                "name": "BTC Correlation Mean Reversion",
                "type": "btc_correlation",
                "description": "Trades mean reversion when short-term correlation deviates from long-term baseline",
                "parameters": {
                    "long_term_correlation_period": "90d",
                    "short_term_correlation_period": "7d",
                    "deviation_threshold": 0.4,     # 40% deviation triggers entry
                    "correlation_baseline": 0.7,
                    "entry_signal": "correlation_oversold_or_overbought",
                    "exit_signal": "correlation_returns_to_mean",
                    "position_size": 0.02,
                    "stop_loss": 0.04,
                    "take_profit": 0.06,
                    "max_positions": 4,
                    "min_volume_24h": 1500000,
                    "correlation_update_interval": "2h",
                    "mean_reversion_window": "14d"
                },
                "symbols": ["ETHUSDC", "BNBUSDC", "SOLUSDC", "AVAXUSDC", "DOTUSDC", "LINKUSDC"],
                "is_active": False
            }
        ]
        
        return strategies
    
    async def create_strategies_in_db(self):
        """Create all strategies in the database"""
        strategies = await self.generate_strategies()
        
        created_count = 0
        failed_count = 0
        
        for strategy_data in strategies:
            try:
                strategy_config = StrategyConfig(
                    name=strategy_data["name"],
                    type=strategy_data["type"],
                    parameters=strategy_data["parameters"],
                    symbols=strategy_data["symbols"],
                    is_active=strategy_data["is_active"]
                )
                
                success = await self.database.create_strategy(strategy_config)
                
                if success:
                    created_count += 1
                    logger.info(
                        "Strategy created successfully",
                        strategy_name=strategy_data["name"],
                        type=strategy_data["type"],
                        symbols_count=len(strategy_data["symbols"])
                    )
                else:
                    failed_count += 1
                    logger.error(
                        "Failed to create strategy",
                        strategy_name=strategy_data["name"]
                    )
                    
            except Exception as e:
                failed_count += 1
                logger.error(
                    "Error creating strategy",
                    strategy_name=strategy_data["name"],
                    error=str(e)
                )
        
        return {
            "total": len(strategies),
            "created": created_count,
            "failed": failed_count,
            "strategies": [s["name"] for s in strategies]
        }
    
    async def close(self):
        """Close database connection"""
        if self.database:
            await self.database.disconnect()
            logger.info("Database connection closed")


async def main():
    """Main execution function"""
    logger.info("Starting BTC Correlation Strategy Generator")
    
    generator = BTCCorrelationStrategyGenerator()
    
    try:
        # Initialize
        await generator.initialize()
        
        # Generate and create strategies
        result = await generator.create_strategies_in_db()
        
        # Print summary
        print("\n" + "="*60)
        print("BTC CORRELATION STRATEGIES GENERATION COMPLETE")
        print("="*60)
        print(f"Total Strategies: {result['total']}")
        print(f"Successfully Created: {result['created']}")
        print(f"Failed: {result['failed']}")
        print("\nStrategies Created:")
        for idx, name in enumerate(result['strategies'], 1):
            print(f"  {idx}. {name}")
        print("="*60)
        
        if result['created'] > 0:
            print("\n✅ Strategies are created in INACTIVE state for testing.")
            print("📊 Activate strategies via API after reviewing parameters.")
            print("🔗 API Endpoint: POST /api/v1/strategy/{strategy_id}/resume")
        
        return result
        
    except Exception as e:
        logger.error("Error in main execution", error=str(e))
        print(f"\n❌ Error: {str(e)}")
        return None
        
    finally:
        await generator.close()


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result and result['created'] > 0 else 1)
