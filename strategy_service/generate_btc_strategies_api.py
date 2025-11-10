"""
Generate Bitcoin Correlation Trading Strategies via API

This script creates multiple strategies that focus on trading altcoins based on 
their correlation with Bitcoin price movements using the Strategy Service API.
"""

import requests
import json
from typing import List, Dict, Any


def generate_btc_correlation_strategies() -> List[Dict[str, Any]]:
    """Generate multiple BTC correlation strategies"""
    
    strategies = [
        # Strategy 1: High Positive Correlation - Momentum Following
        {
            "name": "BTC Momentum Follower",
            "type": "btc_correlation",
            "parameters": {
                "description": "Trades altcoins with high positive BTC correlation when BTC shows strong momentum",
                "correlation_threshold": 0.7,
                "correlation_period": "7d",
                "btc_momentum_period": "4h",
                "btc_momentum_threshold": 2.0,
                "entry_signal": "btc_strong_uptrend",
                "exit_signal": "btc_momentum_weakens",
                "position_size": 0.02,
                "stop_loss": 0.03,
                "take_profit": 0.06,
                "max_positions": 3,
                "min_volume_24h": 1000000,
                "correlation_update_interval": "1h"
            },
            "symbols": ["ETHUSDC", "BNBUSDC", "ADAUSDC", "SOLUSDC", "DOTUSDC", 
                       "AVAXUSDC", "MATICUSDC", "LINKUSDC", "ATOMUSDC"],
            "is_active": False
        },
        
        # Strategy 2: Negative Correlation - Counter-Trend
        {
            "name": "BTC Inverse Trader",
            "type": "btc_correlation",
            "parameters": {
                "description": "Trades assets with negative BTC correlation for diversification",
                "correlation_threshold": -0.5,
                "correlation_period": "14d",
                "btc_trend_period": "1d",
                "entry_signal": "btc_downtrend_and_negative_correlation",
                "exit_signal": "btc_reversal",
                "position_size": 0.015,
                "stop_loss": 0.04,
                "take_profit": 0.08,
                "max_positions": 2,
                "min_volume_24h": 500000,
                "correlation_update_interval": "4h",
                "hedge_mode": True
            },
            "symbols": ["ETHUSDC", "BNBUSDC", "XRPUSDC", "ADAUSDC", "DOGEUSDC"],
            "is_active": False
        },
        
        # Strategy 3: Correlation Divergence
        {
            "name": "BTC Correlation Divergence",
            "type": "btc_correlation",
            "parameters": {
                "description": "Identifies and trades divergences between altcoin price and expected correlation with BTC",
                "correlation_threshold": 0.6,
                "correlation_period": "30d",
                "short_correlation_period": "3d",
                "divergence_threshold": 0.3,
                "btc_price_change_min": 1.5,
                "entry_signal": "correlation_divergence_detected",
                "exit_signal": "correlation_normalized",
                "position_size": 0.025,
                "stop_loss": 0.035,
                "take_profit": 0.07,
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
            "parameters": {
                "description": "Trades high-beta altcoins that amplify BTC movements during strong trends",
                "correlation_threshold": 0.8,
                "beta_threshold": 1.5,
                "correlation_period": "14d",
                "btc_trend_strength": "strong",
                "btc_trend_period": "1d",
                "volatility_period": "7d",
                "entry_signal": "strong_btc_trend_with_high_beta",
                "exit_signal": "trend_weakening",
                "position_size": 0.03,
                "stop_loss": 0.05,
                "take_profit": 0.10,
                "max_positions": 2,
                "min_volume_24h": 3000000,
                "correlation_update_interval": "2h",
                "trailing_stop": 0.03
            },
            "symbols": ["SOLUSDC", "AVAXUSDC", "LINKUSDC", "AAVEUSDC", "UNIUSDC", "SUSHIUSDC"],
            "is_active": False
        },
        
        # Strategy 5: Correlation Stability Scanner
        {
            "name": "BTC Stable Correlator",
            "type": "btc_correlation",
            "parameters": {
                "description": "Trades assets with stable, consistent correlation to BTC across timeframes",
                "correlation_threshold": 0.65,
                "correlation_stability": 0.15,
                "timeframes": ["1d", "7d", "30d"],
                "btc_trend_confirmation": True,
                "entry_signal": "stable_correlation_confirmed",
                "exit_signal": "correlation_instability",
                "position_size": 0.02,
                "stop_loss": 0.025,
                "take_profit": 0.05,
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
            "parameters": {
                "description": "Trades highly correlated altcoins during BTC breakout events",
                "correlation_threshold": 0.75,
                "correlation_period": "7d",
                "btc_breakout_period": "4h",
                "btc_resistance_threshold": 0.02,
                "volume_surge_multiplier": 1.5,
                "entry_signal": "btc_breakout_with_volume",
                "exit_signal": "momentum_exhaustion",
                "position_size": 0.035,
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
            "parameters": {
                "description": "Maintains positions in low-correlation assets for portfolio diversification",
                "correlation_threshold": 0.3,
                "max_correlation": 0.5,
                "correlation_period": "30d",
                "rebalance_interval": "1d",
                "target_allocation": 0.20,
                "entry_signal": "low_correlation_maintained",
                "exit_signal": "correlation_increases",
                "position_size": 0.04,
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
            "parameters": {
                "description": "Trades mean reversion when short-term correlation deviates from long-term baseline",
                "long_term_correlation_period": "90d",
                "short_term_correlation_period": "7d",
                "deviation_threshold": 0.4,
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


def create_strategies_via_api(api_url: str = "http://localhost:8001"):
    """Create strategies using the Strategy Service API"""
    
    strategies = generate_btc_correlation_strategies()
    
    created = []
    failed = []
    
    print("\n" + "="*70)
    print("BITCOIN CORRELATION STRATEGIES GENERATION")
    print("="*70)
    print(f"API Endpoint: {api_url}")
    print(f"Total Strategies to Create: {len(strategies)}\n")
    
    for idx, strategy in enumerate(strategies, 1):
        try:
            print(f"[{idx}/{len(strategies)}] Creating: {strategy['name']}...")
            
            # Since we don't have a direct create endpoint, let's store them in a file
            # that can be used by the Strategy Service
            created.append(strategy)
            print(f"  ✓ Prepared: {strategy['name']}")
            print(f"    Type: {strategy['type']}")
            print(f"    Symbols: {len(strategy['symbols'])} assets")
            print(f"    Status: Inactive (for testing)\n")
            
        except Exception as e:
            failed.append({
                "name": strategy['name'],
                "error": str(e)
            })
            print(f"  ✗ Failed: {strategy['name']}")
            print(f"    Error: {str(e)}\n")
    
    # Save strategies to JSON file for import
    output_file = "btc_correlation_strategies.json"
    with open(output_file, 'w') as f:
        json.dump({
            "strategies": strategies,
            "metadata": {
                "created_at": "2025-11-09",
                "type": "btc_correlation",
                "total_count": len(strategies),
                "status": "ready_for_import"
            }
        }, f, indent=2)
    
    # Print summary
    print("="*70)
    print("GENERATION COMPLETE")
    print("="*70)
    print(f"✓ Prepared: {len(created)} strategies")
    print(f"✗ Failed: {len(failed)} strategies")
    print(f"📄 Saved to: {output_file}")
    print("\n" + "="*70)
    print("STRATEGY DESCRIPTIONS")
    print("="*70)
    
    for idx, strategy in enumerate(strategies, 1):
        desc = strategy['parameters'].get('description', 'No description')
        print(f"\n{idx}. {strategy['name']}")
        print(f"   {desc}")
        print(f"   Symbols: {', '.join(strategy['symbols'][:5])}{'...' if len(strategy['symbols']) > 5 else ''}")
        print(f"   Position Size: {strategy['parameters']['position_size']*100}%")
        print(f"   Risk/Reward: {strategy['parameters']['stop_loss']*100}% / {strategy['parameters']['take_profit']*100}%")
    
    print("\n" + "="*70)
    print("NEXT STEPS")
    print("="*70)
    print("1. Review the strategies in btc_correlation_strategies.json")
    print("2. Import strategies via Strategy Service API or database")
    print("3. Activate desired strategies for backtesting")
    print("4. Monitor performance before live trading")
    print("="*70 + "\n")
    
    return {
        "created": len(created),
        "failed": len(failed),
        "output_file": output_file,
        "strategies": created
    }


if __name__ == "__main__":
    result = create_strategies_via_api()
    print(f"\n✅ Generated {result['created']} Bitcoin correlation strategies")
    print(f"📊 Ready for import into Strategy Service\n")
