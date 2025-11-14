#!/usr/bin/env python3
"""
Generate 1000 Diverse Trading Strategies for Backtesting
Covers multiple strategy types with parameter variations
"""

import json
import random
from datetime import datetime
from typing import List, Dict, Any

# Seed for reproducibility
random.seed(42)

# Symbol pools for different strategy types
# NOTE: Using USDC pairs to match available market data in database
HIGH_VOLUME_SYMBOLS = ["ETHUSDC", "BNBUSDC", "ADAUSDC", "SOLUSDC", "DOTUSDC", "AVAXUSDC", "LINKUSDC", "UNIUSDC"]
VOLATILE_SYMBOLS = ["ETHUSDC", "SOLUSDC", "AVAXUSDC", "ATOMUSDC", "AAVEUSDC", "UNIUSDC", "SUSHIUSDC"]
STABLE_SYMBOLS = ["ETHUSDC", "BNBUSDC", "ADAUSDC", "XRPUSDC", "LTCUSDC", "LINKUSDC"]
ALTCOIN_SYMBOLS = ["ADAUSDC", "LINKUSDC", "UNIUSDC", "ATOMUSDC", "AAVEUSDC", "SUSHIUSDC", "DOTUSDC"]
ALL_SYMBOLS = ["ETHUSDC", "BNBUSDC", "ADAUSDC", "SOLUSDC", "LINKUSDC", "DOTUSDC", 
               "AVAXUSDC", "ATOMUSDC", "UNIUSDC", "AAVEUSDC", "SUSHIUSDC", 
               "LTCUSDC", "XRPUSDC", "BTCUSDC"]

def generate_momentum_strategy(strategy_id: int, variation: int) -> Dict[str, Any]:
    """Generate momentum-based strategies with various parameters"""
    timeframes = ["5m", "15m", "1h", "4h"]
    momentum_periods = [10, 14, 20, 30, 50]
    thresholds = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    
    tf = random.choice(timeframes)
    period = random.choice(momentum_periods)
    threshold = random.choice(thresholds)
    symbols = random.sample(ALL_SYMBOLS, random.randint(3, 8))
    
    return {
        "id": f"momentum_{strategy_id}_{variation}",
        "name": f"Momentum Strategy {strategy_id} - {tf} {period}p",
        "type": "momentum",
        "status": "INACTIVE",
        "symbols": symbols,
        "timeframe": tf,
        "parameters": {
            "momentum_period": period,
            "momentum_threshold": threshold,
            "rsi_oversold": random.randint(25, 35),
            "rsi_overbought": random.randint(65, 75),
            "use_volume_filter": random.choice([True, False]),
            "min_volume_multiplier": random.uniform(1.2, 2.5)
        },
        "entry_signals": [
            {"type": "momentum", "operator": "gt", "threshold": threshold},
            {"type": "rsi", "operator": "gt", "threshold": 50}
        ],
        "exit_signals": [
            {"type": "momentum", "operator": "lt", "threshold": 0},
            {"type": "rsi", "operator": "lt", "threshold": 45}
        ],
        "risk_parameters": {
            "position_size": round(random.uniform(0.01, 0.04), 3),
            "stop_loss_pct": round(random.uniform(2.0, 8.0), 1),
            "take_profit_pct": round(random.uniform(4.0, 15.0), 1),
            "max_positions": random.randint(2, 5),
            "trailing_stop": random.choice([True, False])
        },
        "update_interval_seconds": 60 if tf in ["1m", "5m"] else 300
    }

def generate_mean_reversion_strategy(strategy_id: int, variation: int) -> Dict[str, Any]:
    """Generate mean reversion strategies"""
    timeframes = ["15m", "1h", "4h"]
    bb_periods = [14, 20, 30, 50]
    bb_stds = [1.5, 2.0, 2.5, 3.0]
    
    tf = random.choice(timeframes)
    bb_period = random.choice(bb_periods)
    bb_std = random.choice(bb_stds)
    symbols = random.sample(ALL_SYMBOLS, random.randint(3, 7))
    
    return {
        "id": f"mean_reversion_{strategy_id}_{variation}",
        "name": f"Mean Reversion {strategy_id} - BB({bb_period},{bb_std})",
        "type": "mean_reversion",
        "status": "INACTIVE",
        "symbols": symbols,
        "timeframe": tf,
        "parameters": {
            "bb_period": bb_period,
            "bb_std_dev": bb_std,
            "rsi_period": random.randint(10, 20),
            "oversold_level": random.randint(20, 35),
            "overbought_level": random.randint(65, 80),
            "mean_reversion_threshold": random.uniform(0.8, 1.2)
        },
        "entry_signals": [
            {"type": "bb_lower", "operator": "crosses_below"},
            {"type": "rsi", "operator": "lt", "threshold": random.randint(25, 35)}
        ],
        "exit_signals": [
            {"type": "bb_middle", "operator": "crosses_above"},
            {"type": "rsi", "operator": "gt", "threshold": 50}
        ],
        "risk_parameters": {
            "position_size": round(random.uniform(0.015, 0.045), 3),
            "stop_loss_pct": round(random.uniform(3.0, 10.0), 1),
            "take_profit_pct": round(random.uniform(5.0, 20.0), 1),
            "max_positions": random.randint(2, 6),
            "trailing_stop": random.choice([True, False])
        },
        "update_interval_seconds": 300 if tf == "15m" else 600
    }

def generate_breakout_strategy(strategy_id: int, variation: int) -> Dict[str, Any]:
    """Generate breakout strategies"""
    timeframes = ["5m", "15m", "1h", "4h"]
    lookback_periods = [10, 20, 30, 50, 100]
    
    tf = random.choice(timeframes)
    lookback = random.choice(lookback_periods)
    symbols = random.sample(VOLATILE_SYMBOLS, random.randint(3, 6))
    
    return {
        "id": f"breakout_{strategy_id}_{variation}",
        "name": f"Breakout {strategy_id} - {tf} {lookback}p",
        "type": "breakout",
        "status": "INACTIVE",
        "symbols": symbols,
        "timeframe": tf,
        "parameters": {
            "lookback_period": lookback,
            "breakout_threshold": round(random.uniform(0.5, 3.0), 2),
            "volume_multiplier": round(random.uniform(1.5, 3.0), 2),
            "consolidation_period": random.randint(5, 20),
            "atr_multiplier": round(random.uniform(1.0, 2.5), 2)
        },
        "entry_signals": [
            {"type": "price", "operator": "breaks_high", "lookback": lookback},
            {"type": "volume", "operator": "gt", "multiplier": random.uniform(1.5, 2.5)}
        ],
        "exit_signals": [
            {"type": "price", "operator": "breaks_low", "lookback": 10},
            {"type": "atr_trailing_stop"}
        ],
        "risk_parameters": {
            "position_size": round(random.uniform(0.02, 0.05), 3),
            "stop_loss_pct": round(random.uniform(2.5, 7.0), 1),
            "take_profit_pct": round(random.uniform(6.0, 18.0), 1),
            "max_positions": random.randint(2, 4),
            "trailing_stop": True
        },
        "update_interval_seconds": 60 if tf in ["1m", "5m"] else 300
    }

def generate_btc_correlation_strategy(strategy_id: int, variation: int) -> Dict[str, Any]:
    """Generate BTC correlation strategies"""
    timeframes = ["1h", "4h"]
    correlation_types = ["positive", "negative", "divergence", "stable"]
    
    tf = random.choice(timeframes)
    corr_type = random.choice(correlation_types)
    
    if corr_type == "positive":
        corr_threshold = round(random.uniform(0.6, 0.9), 2)
        symbols = random.sample(["ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "MATICUSDT"], random.randint(4, 5))
    elif corr_type == "negative":
        corr_threshold = round(random.uniform(-0.7, -0.3), 2)
        symbols = random.sample(ALL_SYMBOLS, random.randint(3, 6))
    elif corr_type == "divergence":
        corr_threshold = round(random.uniform(-0.2, 0.6), 2)
        symbols = random.sample(ALTCOIN_SYMBOLS, random.randint(4, 7))
    else:  # stable
        corr_threshold = round(random.uniform(0.5, 0.8), 2)
        symbols = random.sample(STABLE_SYMBOLS, random.randint(4, 6))
    
    return {
        "id": f"btc_corr_{strategy_id}_{variation}",
        "name": f"BTC Correlation {strategy_id} - {corr_type.title()}",
        "type": "btc_correlation",
        "status": "INACTIVE",
        "symbols": symbols,
        "timeframe": tf,
        "parameters": {
            "correlation_type": corr_type,
            "correlation_threshold": corr_threshold,
            "correlation_window": random.choice([7, 14, 30]),
            "btc_momentum_threshold": round(random.uniform(0.5, 2.0), 2),
            "divergence_threshold": round(random.uniform(1.0, 3.0), 2) if corr_type == "divergence" else 0
        },
        "entry_signals": [
            {"type": "btc_correlation", "operator": "meets_threshold"},
            {"type": "btc_momentum", "operator": "gt", "threshold": 0.5}
        ],
        "exit_signals": [
            {"type": "btc_correlation", "operator": "breaks_threshold"},
            {"type": "profit_target_hit"}
        ],
        "risk_parameters": {
            "position_size": round(random.uniform(0.015, 0.04), 3),
            "stop_loss_pct": round(random.uniform(2.5, 8.0), 1),
            "take_profit_pct": round(random.uniform(5.0, 15.0), 1),
            "max_positions": random.randint(2, 5),
            "trailing_stop": random.choice([True, False])
        },
        "update_interval_seconds": 600
    }

def generate_volume_strategy(strategy_id: int, variation: int) -> Dict[str, Any]:
    """Generate volume-based strategies"""
    timeframes = ["5m", "15m", "1h"]
    
    tf = random.choice(timeframes)
    symbols = random.sample(HIGH_VOLUME_SYMBOLS, random.randint(4, 6))
    
    return {
        "id": f"volume_{strategy_id}_{variation}",
        "name": f"Volume Strategy {strategy_id} - {tf}",
        "type": "volume_based",
        "status": "INACTIVE",
        "symbols": symbols,
        "timeframe": tf,
        "parameters": {
            "volume_ma_period": random.choice([10, 20, 30]),
            "volume_spike_multiplier": round(random.uniform(2.0, 5.0), 2),
            "price_change_threshold": round(random.uniform(0.5, 2.5), 2),
            "obv_period": random.choice([10, 14, 20]),
            "accumulation_threshold": round(random.uniform(1.0, 3.0), 2)
        },
        "entry_signals": [
            {"type": "volume_spike", "multiplier": random.uniform(2.0, 4.0)},
            {"type": "price_momentum", "operator": "gt", "threshold": 0.5},
            {"type": "obv", "operator": "increasing"}
        ],
        "exit_signals": [
            {"type": "volume", "operator": "lt", "threshold": 1.0},
            {"type": "price_momentum", "operator": "lt", "threshold": 0}
        ],
        "risk_parameters": {
            "position_size": round(random.uniform(0.02, 0.045), 3),
            "stop_loss_pct": round(random.uniform(2.0, 6.0), 1),
            "take_profit_pct": round(random.uniform(4.0, 12.0), 1),
            "max_positions": random.randint(2, 5),
            "trailing_stop": random.choice([True, False])
        },
        "update_interval_seconds": 60 if tf == "5m" else 300
    }

def generate_volatility_strategy(strategy_id: int, variation: int) -> Dict[str, Any]:
    """Generate volatility-based strategies"""
    timeframes = ["15m", "1h", "4h"]
    
    tf = random.choice(timeframes)
    symbols = random.sample(VOLATILE_SYMBOLS, random.randint(3, 6))
    
    return {
        "id": f"volatility_{strategy_id}_{variation}",
        "name": f"Volatility {strategy_id} - ATR {tf}",
        "type": "volatility",
        "status": "INACTIVE",
        "symbols": symbols,
        "timeframe": tf,
        "parameters": {
            "atr_period": random.choice([10, 14, 20, 30]),
            "atr_multiplier": round(random.uniform(1.0, 3.0), 2),
            "volatility_threshold": round(random.uniform(0.5, 2.5), 2),
            "bb_period": random.choice([14, 20, 30]),
            "bb_std_dev": round(random.uniform(1.5, 3.0), 2),
            "expansion_threshold": round(random.uniform(1.2, 2.0), 2)
        },
        "entry_signals": [
            {"type": "atr", "operator": "gt", "threshold": random.uniform(1.5, 2.5)},
            {"type": "bb_width", "operator": "expanding"},
            {"type": "price_momentum", "operator": "strong"}
        ],
        "exit_signals": [
            {"type": "atr", "operator": "lt", "threshold": 1.0},
            {"type": "bb_width", "operator": "contracting"}
        ],
        "risk_parameters": {
            "position_size": round(random.uniform(0.015, 0.04), 3),
            "stop_loss_pct": round(random.uniform(3.0, 9.0), 1),
            "take_profit_pct": round(random.uniform(6.0, 18.0), 1),
            "max_positions": random.randint(2, 4),
            "trailing_stop": True
        },
        "update_interval_seconds": 300
    }

def generate_macd_strategy(strategy_id: int, variation: int) -> Dict[str, Any]:
    """Generate MACD-based strategies"""
    timeframes = ["15m", "1h", "4h"]
    
    tf = random.choice(timeframes)
    fast_period = random.choice([8, 12, 15])
    slow_period = random.choice([21, 26, 30])
    signal_period = random.choice([7, 9, 11])
    symbols = random.sample(ALL_SYMBOLS, random.randint(4, 7))
    
    return {
        "id": f"macd_{strategy_id}_{variation}",
        "name": f"MACD {strategy_id} - {fast_period}/{slow_period}/{signal_period}",
        "type": "macd",
        "status": "INACTIVE",
        "symbols": symbols,
        "timeframe": tf,
        "parameters": {
            "fast_period": fast_period,
            "slow_period": slow_period,
            "signal_period": signal_period,
            "histogram_threshold": round(random.uniform(0.0, 0.5), 3),
            "use_divergence": random.choice([True, False])
        },
        "entry_signals": [
            {"type": "macd_cross", "direction": "bullish"},
            {"type": "macd_histogram", "operator": "gt", "threshold": 0}
        ],
        "exit_signals": [
            {"type": "macd_cross", "direction": "bearish"},
            {"type": "macd_histogram", "operator": "lt", "threshold": 0}
        ],
        "risk_parameters": {
            "position_size": round(random.uniform(0.02, 0.04), 3),
            "stop_loss_pct": round(random.uniform(2.5, 7.0), 1),
            "take_profit_pct": round(random.uniform(5.0, 14.0), 1),
            "max_positions": random.randint(2, 5),
            "trailing_stop": random.choice([True, False])
        },
        "update_interval_seconds": 300
    }

def generate_hybrid_strategy(strategy_id: int, variation: int) -> Dict[str, Any]:
    """Generate hybrid strategies combining multiple indicators"""
    timeframes = ["15m", "1h", "4h"]
    
    tf = random.choice(timeframes)
    symbols = random.sample(ALL_SYMBOLS, random.randint(3, 6))
    
    indicators = random.sample(["rsi", "macd", "bb", "volume", "atr", "ema"], 3)
    
    return {
        "id": f"hybrid_{strategy_id}_{variation}",
        "name": f"Hybrid {strategy_id} - {'+'.join(indicators).upper()}",
        "type": "hybrid",
        "status": "INACTIVE",
        "symbols": symbols,
        "timeframe": tf,
        "parameters": {
            "primary_indicator": indicators[0],
            "secondary_indicator": indicators[1],
            "filter_indicator": indicators[2],
            "rsi_period": random.randint(10, 20),
            "ema_fast": random.choice([9, 12, 15]),
            "ema_slow": random.choice([21, 26, 30]),
            "bb_period": random.choice([14, 20, 30]),
            "volume_threshold": round(random.uniform(1.2, 2.5), 2)
        },
        "entry_signals": [
            {"type": indicators[0], "operator": "bullish"},
            {"type": indicators[1], "operator": "confirms"},
            {"type": indicators[2], "operator": "filter_pass"}
        ],
        "exit_signals": [
            {"type": indicators[0], "operator": "bearish"},
            {"type": "profit_target_hit"}
        ],
        "risk_parameters": {
            "position_size": round(random.uniform(0.015, 0.035), 3),
            "stop_loss_pct": round(random.uniform(2.5, 8.0), 1),
            "take_profit_pct": round(random.uniform(5.0, 16.0), 1),
            "max_positions": random.randint(2, 5),
            "trailing_stop": random.choice([True, False])
        },
        "update_interval_seconds": 300
    }

def generate_scalping_strategy(strategy_id: int, variation: int) -> Dict[str, Any]:
    """Generate scalping strategies for quick profits"""
    timeframes = ["1m", "5m"]
    
    tf = random.choice(timeframes)
    symbols = random.sample(HIGH_VOLUME_SYMBOLS, random.randint(2, 4))
    
    return {
        "id": f"scalp_{strategy_id}_{variation}",
        "name": f"Scalper {strategy_id} - {tf} Quick",
        "type": "scalping",
        "status": "INACTIVE",
        "symbols": symbols,
        "timeframe": tf,
        "parameters": {
            "ema_fast": random.choice([5, 8, 10]),
            "ema_slow": random.choice([13, 15, 20]),
            "profit_target": round(random.uniform(0.3, 1.5), 2),
            "quick_exit": True,
            "min_spread": round(random.uniform(0.05, 0.15), 3)
        },
        "entry_signals": [
            {"type": "ema_cross", "direction": "bullish"},
            {"type": "volume", "operator": "high"},
            {"type": "spread", "operator": "acceptable"}
        ],
        "exit_signals": [
            {"type": "profit_target", "threshold": random.uniform(0.5, 1.5)},
            {"type": "time_exit", "seconds": random.randint(60, 300)},
            {"type": "ema_cross", "direction": "bearish"}
        ],
        "risk_parameters": {
            "position_size": round(random.uniform(0.03, 0.06), 3),
            "stop_loss_pct": round(random.uniform(0.5, 2.0), 2),
            "take_profit_pct": round(random.uniform(0.8, 3.0), 2),
            "max_positions": random.randint(1, 3),
            "trailing_stop": False
        },
        "update_interval_seconds": 30
    }

def generate_swing_strategy(strategy_id: int, variation: int) -> Dict[str, Any]:
    """Generate swing trading strategies"""
    timeframes = ["4h", "1d"]
    
    tf = random.choice(timeframes)
    symbols = random.sample(ALL_SYMBOLS, random.randint(4, 8))
    
    return {
        "id": f"swing_{strategy_id}_{variation}",
        "name": f"Swing {strategy_id} - {tf} Trend",
        "type": "swing",
        "status": "INACTIVE",
        "symbols": symbols,
        "timeframe": tf,
        "parameters": {
            "ema_short": random.choice([20, 30, 50]),
            "ema_long": random.choice([100, 150, 200]),
            "rsi_period": random.choice([14, 21, 30]),
            "trend_strength": round(random.uniform(0.5, 2.0), 2),
            "hold_time_min": random.randint(12, 48)  # hours
        },
        "entry_signals": [
            {"type": "ema_trend", "direction": "bullish"},
            {"type": "rsi", "operator": "between", "low": 40, "high": 60},
            {"type": "trend_confirmation"}
        ],
        "exit_signals": [
            {"type": "ema_cross", "direction": "bearish"},
            {"type": "rsi", "operator": "overbought"},
            {"type": "trend_weakening"}
        ],
        "risk_parameters": {
            "position_size": round(random.uniform(0.02, 0.05), 3),
            "stop_loss_pct": round(random.uniform(5.0, 12.0), 1),
            "take_profit_pct": round(random.uniform(10.0, 30.0), 1),
            "max_positions": random.randint(3, 6),
            "trailing_stop": True
        },
        "update_interval_seconds": 3600
    }

def generate_all_strategies() -> List[Dict[str, Any]]:
    """Generate all 1000 strategies with diverse types"""
    strategies = []
    strategy_id = 1
    
    # Strategy type distribution (totaling 1000)
    strategy_types = [
        (generate_momentum_strategy, 150),      # 150 momentum strategies
        (generate_mean_reversion_strategy, 140), # 140 mean reversion
        (generate_breakout_strategy, 120),       # 120 breakout
        (generate_btc_correlation_strategy, 110), # 110 BTC correlation
        (generate_volume_strategy, 100),         # 100 volume-based
        (generate_volatility_strategy, 90),      # 90 volatility
        (generate_macd_strategy, 90),            # 90 MACD
        (generate_hybrid_strategy, 100),         # 100 hybrid
        (generate_scalping_strategy, 50),        # 50 scalping
        (generate_swing_strategy, 50),           # 50 swing trading
    ]
    
    for generator_func, count in strategy_types:
        for i in range(count):
            try:
                strategy = generator_func(strategy_id, i)
                strategies.append(strategy)
                strategy_id += 1
            except Exception as e:
                print(f"Error generating strategy {strategy_id}: {e}")
                continue
    
    return strategies

def main():
    """Main execution"""
    print("=" * 80)
    print("GENERATING 1000 TRADING STRATEGIES")
    print("=" * 80)
    
    strategies = generate_all_strategies()
    
    print(f"\n✓ Generated {len(strategies)} strategies")
    
    # Create output structure
    output = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "total_count": len(strategies),
            "strategy_types": {
                "momentum": len([s for s in strategies if s["type"] == "momentum"]),
                "mean_reversion": len([s for s in strategies if s["type"] == "mean_reversion"]),
                "breakout": len([s for s in strategies if s["type"] == "breakout"]),
                "btc_correlation": len([s for s in strategies if s["type"] == "btc_correlation"]),
                "volume_based": len([s for s in strategies if s["type"] == "volume_based"]),
                "volatility": len([s for s in strategies if s["type"] == "volatility"]),
                "macd": len([s for s in strategies if s["type"] == "macd"]),
                "hybrid": len([s for s in strategies if s["type"] == "hybrid"]),
                "scalping": len([s for s in strategies if s["type"] == "scalping"]),
                "swing": len([s for s in strategies if s["type"] == "swing"])
            },
            "status": "ready_for_backtest"
        },
        "strategies": strategies
    }
    
    # Save to JSON file
    output_file = "strategies_1000.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"✓ Saved to {output_file}")
    print(f"\nStrategy Type Distribution:")
    for strategy_type, count in output["metadata"]["strategy_types"].items():
        print(f"  {strategy_type:20s}: {count:4d} strategies")
    
    print("\n" + "=" * 80)
    print("GENERATION COMPLETE")
    print("=" * 80)
    print(f"\nNext step: Run backtesting engine on {len(strategies)} strategies")

if __name__ == "__main__":
    main()
