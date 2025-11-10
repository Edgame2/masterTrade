"""
Strategy Learning System

This module implements a multi-faceted learning system that analyzes backtest results
and generates improved strategies using:

1. Genetic Algorithm - Combines best strategy features through crossover and mutation
2. Reinforcement Learning - Rewards successful patterns and strategy behaviors
3. Statistical Analysis - Identifies common success factors across strategies

The system continuously learns from backtest results to generate better strategies.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
import numpy as np
import structlog

logger = structlog.get_logger()

try:  # Optional dependency guard to keep unit tests lightweight
    import pandas as _pd
except ModuleNotFoundError:  # pragma: no cover - dependency resolution
    _pd = None

if TYPE_CHECKING:
    import pandas as pd  # type: ignore
elif _pd is None:
    class _PandasUnavailable:
        def __getattr__(self, name):  # pragma: no cover - simple guard
            raise RuntimeError(
                "pandas is required for strategy_service.ml_models.strategy_learner. "
                "Install it via pip install -r strategy_service/requirements.txt before "
                "running the full learning pipeline."
            )

    pd = _PandasUnavailable()
else:
    pd = _pd


class StrategyGenome:
    """
    Represents a strategy as a genome for genetic algorithm
    
    Genes include:
    - Indicators used (RSI, MACD, BB, etc.)
    - Indicator parameters (periods, thresholds)
    - Entry/exit logic
    - Risk management parameters
    """
    
    def __init__(self, strategy_dict: Dict = None):
        if strategy_dict:
            self.from_strategy(strategy_dict)
        else:
            self.randomize()
    
    def from_strategy(self, strategy: Dict):
        """Initialize genome from existing strategy"""
        self.strategy_type = strategy.get('type', 'hybrid')
        self.indicators = strategy.get('indicators', {})
        self.entry_conditions = strategy.get('entry_conditions', {})
        self.exit_conditions = strategy.get('exit_conditions', {})
        self.risk_params = strategy.get('risk_management', {})
        self.timeframe = strategy.get('timeframe', '15m')
        self.symbols = strategy.get('symbols', ['BTCUSDT'])
        self.sentiment_profile = self._normalise_sentiment_profile(
            strategy.get('sentiment_profile') or {}
        )
        self.regime_preferences = self._normalise_regime_preferences(
            strategy.get('regime_preferences') or strategy.get('preferred_regimes')
        )
    
    def randomize(self):
        """Create random genome"""
        self.strategy_type = random.choice(['momentum', 'mean_reversion', 'breakout', 'hybrid'])
        self.indicators = self._random_indicators()
        self.entry_conditions = self._random_entry()
        self.exit_conditions = self._random_exit()
        self.risk_params = self._random_risk()
        self.timeframe = random.choice(['5m', '15m', '1h', '4h'])
        self.symbols = random.sample(['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT'], k=random.randint(1, 2))
        self.sentiment_profile = self._random_sentiment_profile()
        self.regime_preferences = self._random_regime_preferences()
    
    def _random_indicators(self) -> Dict:
        """Generate random indicator configuration"""
        indicators = {}
        
        # RSI
        if random.random() > 0.3:
            indicators['rsi'] = {
                'period': random.choice([7, 14, 21, 28]),
                'overbought': random.randint(65, 85),
                'oversold': random.randint(15, 35)
            }
        
        # MACD
        if random.random() > 0.3:
            indicators['macd'] = {
                'fast': random.choice([8, 12, 16]),
                'slow': random.choice([21, 26, 30]),
                'signal': random.choice([7, 9, 11])
            }
        
        # Bollinger Bands
        if random.random() > 0.3:
            indicators['bollinger'] = {
                'period': random.choice([15, 20, 25]),
                'std_dev': random.uniform(1.5, 2.5)
            }
        
        # Moving Averages
        if random.random() > 0.5:
            indicators['sma'] = {
                'fast': random.choice([5, 10, 20]),
                'slow': random.choice([50, 100, 200])
            }
        
        # Volume
        if random.random() > 0.4:
            indicators['volume'] = {
                'period': random.choice([10, 20, 30]),
                'threshold': random.uniform(1.2, 2.0)
            }
        
        return indicators
    
    def _random_entry(self) -> Dict:
        """Generate random entry conditions"""
        return {
            'min_confidence': random.uniform(0.6, 0.9),
            'require_volume': random.choice([True, False]),
            'trend_alignment': random.choice([True, False]),
            'price_prediction_weight': random.uniform(0.2, 0.5)
        }
    
    def _random_exit(self) -> Dict:
        """Generate random exit conditions"""
        return {
            'take_profit_pct': random.uniform(1.0, 5.0),
            'stop_loss_pct': random.uniform(0.5, 2.5),
            'trailing_stop': random.choice([True, False]),
            'trailing_stop_pct': random.uniform(0.5, 2.0) if random.choice([True, False]) else None,
            'time_exit_hours': random.choice([None, 24, 48, 72])
        }
    
    def _random_risk(self) -> Dict:
        """Generate random risk management parameters"""
        return {
            'max_position_size': random.uniform(0.02, 0.1),
            'max_leverage': random.choice([1, 2, 3]),
            'risk_per_trade': random.uniform(0.01, 0.03)
        }

    @staticmethod
    def _random_sentiment_profile() -> Dict:
        """Generate sentiment handling configuration for the strategy."""
        bias = random.choice(['risk_on', 'fear_buy', 'contrarian', 'balanced'])
        symbol_weight = random.uniform(0.45, 0.8)
        global_weight = random.uniform(0.2, 0.55)
        total_weight = symbol_weight + global_weight
        if total_weight == 0:
            symbol_weight = 0.6
            global_weight = 0.4
            total_weight = 1.0
        symbol_weight /= total_weight
        global_weight /= total_weight
        return {
            'bias': bias,
            'min_alignment': round(random.uniform(0.4, 0.65), 3),
            'negative_buy_threshold': round(random.uniform(0.45, 0.65), 3),
            'extreme_threshold': round(random.uniform(0.55, 0.75), 3),
            'symbol_weight': round(symbol_weight, 3),
            'global_weight': round(global_weight, 3),
            'allow_missing': random.choice([True, False])
        }

    @staticmethod
    def _random_regime_preferences() -> List[str]:
        """Select regime preferences strategy performs best in."""
        regimes = ['bull_trend', 'bear_trend', 'ranging', 'high_volatility', 'low_volatility']
        selection = random.sample(regimes, k=random.randint(1, 3))
        return sorted(selection)

    @staticmethod
    def _normalise_sentiment_profile(profile: Dict) -> Dict:
        if not isinstance(profile, dict):
            profile = {}
        defaults = {
            'bias': 'balanced',
            'min_alignment': 0.5,
            'negative_buy_threshold': 0.55,
            'extreme_threshold': 0.65,
            'symbol_weight': 0.6,
            'global_weight': 0.4,
            'allow_missing': True
        }
        merged = {**defaults, **{k: v for k, v in profile.items() if v is not None}}
        total_weight = merged['symbol_weight'] + merged['global_weight']
        if total_weight <= 0:
            merged['symbol_weight'], merged['global_weight'] = 0.6, 0.4
        else:
            merged['symbol_weight'] = round(merged['symbol_weight'] / total_weight, 3)
            merged['global_weight'] = round(merged['global_weight'] / total_weight, 3)
        return merged

    @staticmethod
    def _normalise_regime_preferences(preferences: Optional[Any]) -> List[str]:
        if preferences is None:
            return []
        if isinstance(preferences, str):
            preferences = [preferences]
        normalised = sorted({str(pref) for pref in preferences if pref})
        return normalised

    def _blend_sentiment_profiles(self, left: Dict, right: Dict) -> Dict:
        profile = {}
        for key in ['bias', 'allow_missing']:
            profile[key] = random.choice([left.get(key), right.get(key)])
        for key in ['min_alignment', 'negative_buy_threshold', 'extreme_threshold']:
            profile[key] = round((left.get(key, 0.5) + right.get(key, 0.5)) / 2, 3)
        for key in ['symbol_weight', 'global_weight']:
            profile[key] = round((left.get(key, 0.5) + right.get(key, 0.5)) / 2, 3)
        total_weight = profile['symbol_weight'] + profile['global_weight']
        if total_weight > 0:
            profile['symbol_weight'] = round(profile['symbol_weight'] / total_weight, 3)
            profile['global_weight'] = round(profile['global_weight'] / total_weight, 3)
        else:
            profile['symbol_weight'], profile['global_weight'] = 0.6, 0.4
        return profile

    def _mutate_sentiment_profile(self, profile: Dict, rate: float):
        if random.random() < rate:
            profile['bias'] = random.choice(['risk_on', 'fear_buy', 'contrarian', 'balanced'])
        for key in ['min_alignment', 'negative_buy_threshold', 'extreme_threshold']:
            if random.random() < rate:
                delta = random.uniform(-0.05, 0.05)
                profile[key] = round(min(0.9, max(0.2, profile[key] + delta)), 3)
        if random.random() < rate:
            symbol_weight = min(0.9, max(0.1, profile['symbol_weight'] + random.uniform(-0.1, 0.1)))
            global_weight = 1.0 - symbol_weight
            profile['symbol_weight'] = round(symbol_weight, 3)
            profile['global_weight'] = round(global_weight, 3)
        if random.random() < rate:
            profile['allow_missing'] = not profile['allow_missing']

    def _mutate_regime_preferences(self, rate: float):
        regimes = ['bull_trend', 'bear_trend', 'ranging', 'high_volatility', 'low_volatility']
        current = set(self.regime_preferences)
        if random.random() < rate and current:
            current.discard(random.choice(tuple(current)))
        if random.random() < rate:
            current.add(random.choice(regimes))
        if not current:
            current.add(random.choice(regimes))
        self.regime_preferences = sorted(current)
    
    def to_strategy(self, strategy_id: str = None) -> Dict:
        """Convert genome to strategy dictionary"""
        return {
            'id': strategy_id or f"gen_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000,9999)}",
            'name': f"Generated {self.strategy_type.title()} Strategy",
            'type': self.strategy_type,
            'indicators': self.indicators,
            'entry_conditions': self.entry_conditions,
            'exit_conditions': self.exit_conditions,
            'risk_management': self.risk_params,
            'timeframe': self.timeframe,
            'symbols': self.symbols,
            'sentiment_profile': self.sentiment_profile,
            'regime_preferences': self.regime_preferences,
            'preferred_regimes': self.regime_preferences,
            'status': 'pending_backtest',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'generation_method': 'genetic_algorithm'
        }
    
    def crossover(self, other: 'StrategyGenome') -> 'StrategyGenome':
        """
        Perform crossover with another genome
        
        Creates offspring by combining genes from both parents
        """
        child = StrategyGenome()
        
        # Inherit type from fitter parent
        child.strategy_type = random.choice([self.strategy_type, other.strategy_type])
        
        # Crossover indicators
        child.indicators = {}
        all_indicator_types = set(self.indicators.keys()) | set(other.indicators.keys())
        for ind_type in all_indicator_types:
            if ind_type in self.indicators and ind_type in other.indicators:
                # Both have it - combine parameters
                child.indicators[ind_type] = self._combine_params(
                    self.indicators[ind_type],
                    other.indicators[ind_type]
                )
            elif random.random() > 0.5:
                # Inherit from one parent
                if ind_type in self.indicators:
                    child.indicators[ind_type] = self.indicators[ind_type].copy()
                else:
                    child.indicators[ind_type] = other.indicators[ind_type].copy()
        
        # Crossover entry/exit conditions
        child.entry_conditions = self._combine_params(self.entry_conditions, other.entry_conditions)
        child.exit_conditions = self._combine_params(self.exit_conditions, other.exit_conditions)
        child.risk_params = self._combine_params(self.risk_params, other.risk_params)
        
        # Inherit timeframe and symbols
        child.timeframe = random.choice([self.timeframe, other.timeframe])
        child.symbols = list(set(self.symbols + other.symbols))[:2]  # Max 2 symbols
        child.sentiment_profile = self._blend_sentiment_profiles(
            getattr(self, 'sentiment_profile', self._random_sentiment_profile()),
            getattr(other, 'sentiment_profile', other._random_sentiment_profile())
        )
        combined_regimes = list({*getattr(self, 'regime_preferences', []), *getattr(other, 'regime_preferences', [])})
        if not combined_regimes:
            combined_regimes = self._random_regime_preferences()
        random.shuffle(combined_regimes)
        child.regime_preferences = sorted(combined_regimes[:3])
        
        return child
    
    def _combine_params(self, params1: Dict, params2: Dict) -> Dict:
        """Combine parameters from two dicts"""
        combined = {}
        all_keys = set(params1.keys()) | set(params2.keys())
        
        for key in all_keys:
            if key in params1 and key in params2:
                # Both have this parameter
                val1, val2 = params1[key], params2[key]
                
                if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                    # Average numeric values
                    combined[key] = (val1 + val2) / 2
                else:
                    # Randomly choose for non-numeric
                    combined[key] = random.choice([val1, val2])
            elif key in params1:
                combined[key] = params1[key]
            else:
                combined[key] = params2[key]
        
        return combined
    
    def mutate(self, mutation_rate: float = 0.1):
        """
        Mutate the genome
        
        Randomly modifies genes based on mutation rate
        """
        # Mutate indicator parameters
        for ind_type, params in self.indicators.items():
            for param_key, param_value in params.items():
                if random.random() < mutation_rate:
                    if isinstance(param_value, int):
                        params[param_key] = max(1, param_value + random.randint(-5, 5))
                    elif isinstance(param_value, float):
                        params[param_key] = max(0.1, param_value * random.uniform(0.8, 1.2))
        
        # Mutate entry/exit conditions
        for condition_dict in [self.entry_conditions, self.exit_conditions]:
            for key, value in condition_dict.items():
                if random.random() < mutation_rate:
                    if isinstance(value, float):
                        condition_dict[key] = max(0.1, value * random.uniform(0.8, 1.2))
                    elif isinstance(value, bool):
                        condition_dict[key] = not value
        
        # Mutate risk parameters
        for key, value in self.risk_params.items():
            if random.random() < mutation_rate and isinstance(value, (int, float)):
                self.risk_params[key] = max(0.01, value * random.uniform(0.8, 1.2))
        
        # Mutate timeframe
        if random.random() < mutation_rate:
            self.timeframe = random.choice(['5m', '15m', '1h', '4h'])
        self._mutate_sentiment_profile(self.sentiment_profile, mutation_rate)
        self._mutate_regime_preferences(mutation_rate)


class StrategyLearner:
    """
    Multi-faceted strategy learning system
    
    Combines:
    - Genetic Algorithm for strategy evolution
    - Reinforcement Learning for pattern recognition
    - Statistical Analysis for success factor identification
    """
    
    def __init__(self, database):
        self.database = database
        
        # Genetic Algorithm parameters
        self.population_size = 100
        self.elite_size = 10  # Top performers to keep
        self.mutation_rate = 0.15
        self.crossover_rate = 0.7
        
        # Learning data
        self.backtest_history = []
        self.success_patterns = defaultdict(float)
        self.failure_patterns = defaultdict(float)
        self.sentiment_mode_scores = defaultdict(float)
        self.regime_preference_scores = defaultdict(float)
        
        # Performance thresholds
        self.min_sharpe = 0.5
        self.min_win_rate = 0.45
        self.min_profit_factor = 1.2
        
        logger.info("Strategy Learner initialized with genetic algorithm + RL + statistical analysis")
    
    async def learn_from_backtests(self, backtest_results: List[Dict]) -> Dict:
        """
        Learn from backtest results using all three methods
        
        Returns insights and recommendations for future strategy generation
        """
        logger.info(f"Learning from {len(backtest_results)} backtest results")
        
        for result in backtest_results:
            metrics_payload = result.get('metrics')
            if isinstance(metrics_payload, dict):
                result.setdefault('sentiment_metrics', metrics_payload.get('sentiment'))
                result.setdefault('regime_metrics', metrics_payload.get('regime'))
                core_metrics = metrics_payload.get('core') or {}
                if 'win_rate' in core_metrics and 'win_rate' not in result:
                    result['win_rate'] = core_metrics['win_rate']

        # Store backtest history
        self.backtest_history.extend(backtest_results)
        
        # 1. Statistical Analysis
        statistical_insights = await self._statistical_analysis(backtest_results)
        
        # 2. Pattern Recognition (RL-inspired)
        pattern_insights = await self._pattern_recognition(backtest_results)
        
        # 3. Success Factor Identification
        success_factors = await self._identify_success_factors(backtest_results)
        
        return {
            'statistical_insights': statistical_insights,
            'pattern_insights': pattern_insights,
            'success_factors': success_factors,
            'learning_timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    async def _statistical_analysis(self, results: List[Dict]) -> Dict:
        """Perform statistical analysis on backtest results"""
        if not results:
            return {}
        
        df = pd.DataFrame(results)
        
        analysis = {
            'total_strategies': len(results),
            'profitable_count': len(df[df['total_return'] > 0]),
            'avg_sharpe': df['sharpe_ratio'].mean(),
            'avg_win_rate': df['win_rate'].mean(),
            'avg_profit_factor': df['profit_factor'].mean(),
            'best_strategy_types': {},
            'best_timeframes': {},
            'best_indicators': {}
        }
        
        # Analyze by strategy type
        if 'strategy_type' in df.columns:
            type_performance = df.groupby('strategy_type').agg({
                'sharpe_ratio': 'mean',
                'total_return': 'mean',
                'win_rate': 'mean'
            }).to_dict()
            analysis['best_strategy_types'] = type_performance
        
        # Analyze by timeframe
        if 'timeframe' in df.columns:
            timeframe_performance = df.groupby('timeframe').agg({
                'sharpe_ratio': 'mean',
                'total_return': 'mean'
            }).to_dict()
            analysis['best_timeframes'] = timeframe_performance
        
        # Analyze indicator effectiveness
        indicator_scores = defaultdict(list)
        for result in results:
            indicators = result.get('strategy_config', {}).get('indicators', {})
            sharpe = result.get('sharpe_ratio', 0)
            
            for indicator_name in indicators.keys():
                indicator_scores[indicator_name].append(sharpe)
        
        analysis['best_indicators'] = {
            ind: np.mean(scores) for ind, scores in indicator_scores.items()
        }
        
        return analysis
    
    async def _pattern_recognition(self, results: List[Dict]) -> Dict:
        """
        Recognize patterns in successful vs unsuccessful strategies
        
        Uses RL-inspired reward system to identify winning patterns
        """
        successful = [r for r in results if r.get('sharpe_ratio', 0) > self.min_sharpe]
        unsuccessful = [r for r in results if r.get('sharpe_ratio', 0) < 0]
        
        # Update pattern scores
        for result in successful:
            config = result.get('strategy_config', {})
            pattern_key = self._extract_pattern_key(config)
            reward = result.get('sharpe_ratio', 0) * result.get('total_return', 0)
            self.success_patterns[pattern_key] += reward
            profile = result.get('sentiment_profile') or config.get('sentiment_profile')
            if isinstance(profile, dict):
                bias = profile.get('bias', 'balanced')
                self.sentiment_mode_scores[bias] += reward
            regimes = config.get('regime_preferences') or []
            for regime in regimes:
                self.regime_preference_scores[str(regime)] += reward
        
        for result in unsuccessful:
            config = result.get('strategy_config', {})
            pattern_key = self._extract_pattern_key(config)
            penalty = abs(result.get('total_return', 0))
            self.failure_patterns[pattern_key] += penalty
            profile = result.get('sentiment_profile') or config.get('sentiment_profile')
            if isinstance(profile, dict):
                bias = profile.get('bias', 'balanced')
                self.sentiment_mode_scores[bias] -= penalty
            regimes = config.get('regime_preferences') or []
            for regime in regimes:
                self.regime_preference_scores[str(regime)] -= penalty
        
        # Identify top patterns
        top_success_patterns = sorted(
            self.success_patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        top_failure_patterns = sorted(
            self.failure_patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            'top_success_patterns': [{'pattern': p[0], 'score': p[1]} for p in top_success_patterns],
            'top_failure_patterns': [{'pattern': p[0], 'score': p[1]} for p in top_failure_patterns],
            'pattern_count': len(self.success_patterns)
        }
    
    def _extract_pattern_key(self, config: Dict) -> str:
        """Extract a pattern signature from strategy config"""
        indicators = sorted(config.get('indicators', {}).keys())
        strategy_type = config.get('type', 'unknown')
        timeframe = config.get('timeframe', '15m')
        
        return f"{strategy_type}_{timeframe}_{'_'.join(indicators)}"
    
    async def _identify_success_factors(self, results: List[Dict]) -> Dict:
        """
        Identify common factors among successful strategies
        
        Uses correlation analysis to find what makes strategies work
        """
        if len(results) < 20:
            return {'status': 'insufficient_data'}
        
        df = pd.DataFrame(results)
        
        # Separate high performers
        high_performers = df[df['sharpe_ratio'] > df['sharpe_ratio'].quantile(0.75)]
        
        success_factors = {
            'common_indicators': {},
            'optimal_parameters': {},
            'risk_profiles': {}
        }
        
        # Find common indicators in high performers
        indicator_frequency = defaultdict(int)
        for _, row in high_performers.iterrows():
            config = row.get('strategy_config', {})
            indicators = config.get('indicators', {})
            for ind in indicators.keys():
                indicator_frequency[ind] += 1
        
        success_factors['common_indicators'] = dict(sorted(
            indicator_frequency.items(),
            key=lambda x: x[1],
            reverse=True
        ))
        
        # Find optimal parameter ranges
        if len(high_performers) > 5:
            for col in ['win_rate', 'max_drawdown', 'avg_trade_pnl']:
                if col in high_performers.columns:
                    success_factors['optimal_parameters'][col] = {
                        'mean': high_performers[col].mean(),
                        'std': high_performers[col].std(),
                        'min': high_performers[col].min(),
                        'max': high_performers[col].max()
                    }

        sentiment_records = [r.get('sentiment_metrics') for r in results if r.get('sentiment_metrics')]
        if sentiment_records:
            sentiment_df = pd.json_normalize(sentiment_records)
            success_factors['sentiment_trends'] = {
                'avg_alignment': float(sentiment_df.get('average_alignment', pd.Series([0])).mean()),
                'positive_trigger_ratio': float(sentiment_df.get('positive_triggers', pd.Series([0])).sum() / max(1, sentiment_df.get('total_checks', pd.Series([0])).sum())),
                'negative_trigger_ratio': float(sentiment_df.get('negative_triggers', pd.Series([0])).sum() / max(1, sentiment_df.get('total_checks', pd.Series([0])).sum())),
                'dominant_bias_count': sentiment_df.get('dominant_bias', pd.Series(dtype=str)).value_counts().to_dict(),
            }

        regime_records = [r.get('regime_metrics') for r in results if r.get('regime_metrics')]
        if regime_records:
            regime_df = pd.json_normalize(regime_records)
            win_map_series = regime_df.get('win_rate_by_regime')
            if win_map_series is not None:
                aggregated = defaultdict(list)
                for entry in win_map_series.dropna().tolist():
                    for regime, value in entry.items():
                        aggregated[regime].append(value)
                success_factors['regime_performance'] = {
                    regime: float(np.mean(values))
                    for regime, values in aggregated.items()
                }
        
        return success_factors
    
    async def generate_improved_strategies(self, 
                                          count: int = 500,
                                          use_genetic: bool = True,
                                          use_learning: bool = True) -> List[Dict]:
        """
        Generate improved strategies using learned insights
        
        Args:
            count: Number of strategies to generate
            use_genetic: Use genetic algorithm for evolution
            use_learning: Use learned patterns and insights
        
        Returns:
            List of strategy dictionaries
        """
        logger.info(f"Generating {count} improved strategies")
        
        generated_strategies = []
        
        if use_genetic and len(self.backtest_history) > 10:
            # Get top performers for genetic algorithm
            sorted_history = sorted(
                self.backtest_history,
                key=lambda x: x.get('sharpe_ratio', 0),
                reverse=True
            )[:self.population_size]
            
            # Create genomes from top performers
            parent_genomes = [
                StrategyGenome(result['strategy_config']) 
                for result in sorted_history[:self.elite_size]
            ]
            
            # Generate offspring through crossover and mutation
            while len(generated_strategies) < count * 0.7:  # 70% from genetic algorithm
                parent1, parent2 = random.sample(parent_genomes, 2)
                
                if random.random() < self.crossover_rate:
                    child = parent1.crossover(parent2)
                    child.mutate(self.mutation_rate)
                    generated_strategies.append(child.to_strategy())
        
        # Fill remaining with learned patterns
        if use_learning:
            while len(generated_strategies) < count:
                strategy = await self._generate_from_patterns()
                generated_strategies.append(strategy)
        
        # Fill any remaining with random strategies
        while len(generated_strategies) < count:
            genome = StrategyGenome()
            generated_strategies.append(genome.to_strategy())
        
        logger.info(f"Generated {len(generated_strategies)} strategies using genetic algorithm and learning")
        
        return generated_strategies[:count]
    
    async def _generate_from_patterns(self) -> Dict:
        """Generate a strategy based on learned successful patterns"""
        # Get best performing patterns
        if self.success_patterns:
            top_patterns = sorted(
                self.success_patterns.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            
            # Parse a top pattern
            pattern = random.choice(top_patterns)[0]
            parts = pattern.split('_')
            
            if len(parts) >= 2:
                strategy_type = parts[0]
                timeframe = parts[1]
                indicators = parts[2:] if len(parts) > 2 else []
                
                # Create strategy with these characteristics
                genome = StrategyGenome()
                genome.strategy_type = strategy_type
                genome.timeframe = timeframe
                
                # Add indicators from pattern
                genome.indicators = {}
                for ind in indicators:
                    if ind == 'rsi':
                        genome.indicators['rsi'] = {'period': 14, 'overbought': 70, 'oversold': 30}
                    elif ind == 'macd':
                        genome.indicators['macd'] = {'fast': 12, 'slow': 26, 'signal': 9}
                    elif ind == 'bollinger':
                        genome.indicators['bollinger'] = {'period': 20, 'std_dev': 2.0}
                genome.sentiment_profile = self._choose_sentiment_profile()
                genome.regime_preferences = self._choose_regime_preferences()
                
                return genome.to_strategy()
        
        # Fallback to random
        genome = StrategyGenome()
        return genome.to_strategy()

    def _choose_sentiment_profile(self) -> Dict:
        if not self.sentiment_mode_scores:
            return StrategyGenome._random_sentiment_profile()
        best_bias, _ = max(self.sentiment_mode_scores.items(), key=lambda item: item[1])
        profile = StrategyGenome._random_sentiment_profile()
        profile['bias'] = best_bias
        if best_bias == 'fear_buy':
            profile['negative_buy_threshold'] = max(0.35, profile['negative_buy_threshold'] - 0.1)
        return StrategyGenome._normalise_sentiment_profile(profile)

    def _choose_regime_preferences(self) -> List[str]:
        if not self.regime_preference_scores:
            return StrategyGenome._random_regime_preferences()
        sorted_regimes = sorted(self.regime_preference_scores.items(), key=lambda item: item[1], reverse=True)
        preferred = [regime for regime, score in sorted_regimes if score > 0][:3]
        if not preferred:
            preferred = [sorted_regimes[0][0]]
        return StrategyGenome._normalise_regime_preferences(preferred)
    
    def get_generation_stats(self) -> Dict:
        """Get statistics about strategy generation and learning"""
        return {
            'total_backtests_analyzed': len(self.backtest_history),
            'success_patterns_identified': len(self.success_patterns),
            'failure_patterns_identified': len(self.failure_patterns),
            'genetic_algorithm_config': {
                'population_size': self.population_size,
                'elite_size': self.elite_size,
                'mutation_rate': self.mutation_rate,
                'crossover_rate': self.crossover_rate
            }
        }
