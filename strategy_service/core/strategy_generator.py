"""
Advanced Strategy Generator - Automated generation of trading strategies

This module implements sophisticated algorithms for generating trading strategies
using genetic programming, machine learning, and systematic approaches.
Capable of generating thousands of strategies with diverse characteristics.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
import pandas as pd
import random
from itertools import combinations, product
import json
import uuid

# Fixed imports
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from postgres_database import Database as StrategyDatabase
except ImportError:
    class StrategyDatabase:  # type: ignore[override]
        async def connect(self):
            pass

        async def disconnect(self):
            pass

try:
    from config import settings as Config
except ImportError:
    class Config:
        pass

logger = logging.getLogger(__name__)

class StrategyType(Enum):
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion" 
    VOLATILITY = "volatility"
    CROSS_ASSET = "cross_asset"
    SENTIMENT = "sentiment"
    ARBITRAGE = "arbitrage"
    ENSEMBLE = "ensemble"

class IndicatorFamily(Enum):
    TREND = "trend"
    MOMENTUM = "momentum" 
    VOLATILITY = "volatility"
    VOLUME = "volume"
    SENTIMENT = "sentiment"
    MACRO = "macro"

@dataclass
class IndicatorConfig:
    name: str
    family: IndicatorFamily
    parameters: Dict[str, Any]
    timeframes: List[str]
    optimization_ranges: Dict[str, Tuple[float, float]]

class AdvancedStrategyGenerator:
    """
    Advanced strategy generator using multiple generation algorithms
    
    Implements various approaches for generating trading strategies:
    1. Genetic Programming - Evolutionary approach with crossover and mutation
    2. ML-Driven Generation - Using trained models to suggest configurations  
    3. Systematic Generation - Exhaustive parameter space exploration
    4. Ensemble Methods - Combining successful strategy patterns
    """
    
    def __init__(self, config: Config, database: StrategyDatabase):
        self.config = config
        self.db = database
        
        # Define available indicators with their parameter ranges
        self.indicators = self._initialize_indicators()
        
        # Strategy templates for different market conditions
        self.strategy_templates = self._initialize_strategy_templates()
        
        # Genetic programming parameters
        self.population_size = config.GP_POPULATION_SIZE
        self.mutation_rate = config.GP_MUTATION_RATE
        self.crossover_rate = config.GP_CROSSOVER_RATE
        
        logger.info("Advanced Strategy Generator initialized")

    def _initialize_indicators(self) -> Dict[str, IndicatorConfig]:
        """Initialize comprehensive indicator library"""
        indicators = {}
        
        # Trend indicators
        indicators['sma'] = IndicatorConfig(
            name='Simple Moving Average',
            family=IndicatorFamily.TREND,
            parameters={'period': 20},
            timeframes=['5m', '15m', '1h', '4h', '1d'],
            optimization_ranges={'period': (5, 200)}
        )
        
        indicators['ema'] = IndicatorConfig(
            name='Exponential Moving Average',
            family=IndicatorFamily.TREND,
            parameters={'period': 20},
            timeframes=['5m', '15m', '1h', '4h', '1d'],
            optimization_ranges={'period': (5, 200)}
        )
        
        indicators['macd'] = IndicatorConfig(
            name='MACD',
            family=IndicatorFamily.MOMENTUM,
            parameters={'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
            timeframes=['15m', '1h', '4h', '1d'],
            optimization_ranges={
                'fast_period': (8, 20),
                'slow_period': (20, 40), 
                'signal_period': (6, 15)
            }
        )
        
        indicators['rsi'] = IndicatorConfig(
            name='RSI',
            family=IndicatorFamily.MOMENTUM,
            parameters={'period': 14, 'overbought': 70, 'oversold': 30},
            timeframes=['5m', '15m', '1h', '4h', '1d'],
            optimization_ranges={
                'period': (8, 25),
                'overbought': (65, 85),
                'oversold': (15, 35)
            }
        )
        
        indicators['bollinger_bands'] = IndicatorConfig(
            name='Bollinger Bands',
            family=IndicatorFamily.VOLATILITY,
            parameters={'period': 20, 'std_dev': 2.0},
            timeframes=['15m', '1h', '4h', '1d'],
            optimization_ranges={
                'period': (10, 50),
                'std_dev': (1.5, 3.0)
            }
        )
        
        indicators['atr'] = IndicatorConfig(
            name='Average True Range',
            family=IndicatorFamily.VOLATILITY,
            parameters={'period': 14},
            timeframes=['15m', '1h', '4h', '1d'],
            optimization_ranges={'period': (7, 30)}
        )
        
        indicators['stochastic'] = IndicatorConfig(
            name='Stochastic Oscillator',
            family=IndicatorFamily.MOMENTUM,
            parameters={'k_period': 14, 'd_period': 3, 'smooth_k': 1},
            timeframes=['5m', '15m', '1h', '4h'],
            optimization_ranges={
                'k_period': (8, 25),
                'd_period': (2, 8),
                'smooth_k': (1, 5)
            }
        )
        
        indicators['williams_r'] = IndicatorConfig(
            name='Williams %R',
            family=IndicatorFamily.MOMENTUM,
            parameters={'period': 14},
            timeframes=['5m', '15m', '1h', '4h'],
            optimization_ranges={'period': (8, 25)}
        )
        
        indicators['cci'] = IndicatorConfig(
            name='Commodity Channel Index',
            family=IndicatorFamily.MOMENTUM,
            parameters={'period': 20},
            timeframes=['15m', '1h', '4h', '1d'],
            optimization_ranges={'period': (10, 40)}
        )
        
        indicators['adx'] = IndicatorConfig(
            name='Average Directional Index',
            family=IndicatorFamily.TREND,
            parameters={'period': 14},
            timeframes=['1h', '4h', '1d'],
            optimization_ranges={'period': (8, 25)}
        )
        
        # Volume indicators
        indicators['obv'] = IndicatorConfig(
            name='On Balance Volume',
            family=IndicatorFamily.VOLUME,
            parameters={},
            timeframes=['15m', '1h', '4h', '1d'],
            optimization_ranges={}
        )
        
        indicators['volume_sma'] = IndicatorConfig(
            name='Volume Simple Moving Average',
            family=IndicatorFamily.VOLUME,
            parameters={'period': 20},
            timeframes=['15m', '1h', '4h', '1d'],
            optimization_ranges={'period': (10, 50)}
        )
        
        # Custom composite indicators
        indicators['price_volume_trend'] = IndicatorConfig(
            name='Price Volume Trend',
            family=IndicatorFamily.VOLUME,
            parameters={'smoothing': 14},
            timeframes=['1h', '4h', '1d'],
            optimization_ranges={'smoothing': (5, 30)}
        )
        
        return indicators

    def _initialize_strategy_templates(self) -> Dict[StrategyType, Dict]:
        """Initialize strategy templates for different types"""
        templates = {}
        
        templates[StrategyType.MOMENTUM] = {
            'primary_indicators': ['macd', 'rsi', 'adx'],
            'secondary_indicators': ['ema', 'atr'],
            'volume_confirmation': True,
            'multi_timeframe': True,
            'stop_loss_type': 'trailing',
            'position_sizing': 'volatility_based'
        }
        
        templates[StrategyType.MEAN_REVERSION] = {
            'primary_indicators': ['rsi', 'bollinger_bands', 'stochastic'],
            'secondary_indicators': ['williams_r', 'cci'],
            'volume_confirmation': True,
            'multi_timeframe': False,
            'stop_loss_type': 'fixed_percentage',
            'position_sizing': 'equal_weight'
        }
        
        templates[StrategyType.VOLATILITY] = {
            'primary_indicators': ['bollinger_bands', 'atr'],
            'secondary_indicators': ['rsi', 'volume_sma'],
            'volume_confirmation': True,
            'multi_timeframe': True,
            'stop_loss_type': 'volatility_based',
            'position_sizing': 'inverse_volatility'
        }
        
        templates[StrategyType.CROSS_ASSET] = {
            'primary_indicators': ['ema', 'rsi'],
            'secondary_indicators': ['macd', 'adx'],
            'volume_confirmation': True,
            'multi_timeframe': True,
            'correlation_assets': ['BTC', 'ETH', 'SPY'],
            'stop_loss_type': 'correlation_based',
            'position_sizing': 'correlation_adjusted'
        }
        
        templates[StrategyType.SENTIMENT] = {
            'primary_indicators': ['rsi', 'ema'],
            'secondary_indicators': ['macd'],
            'sentiment_sources': ['social_media', 'news', 'fear_greed_index'],
            'volume_confirmation': True,
            'multi_timeframe': False,
            'stop_loss_type': 'sentiment_based',
            'position_sizing': 'sentiment_weighted'
        }
        
        return templates

    async def generate_genetic_strategies(self, count: int, market_regime: str, 
                                        market_data: Dict) -> List[str]:
        """
        Generate strategies using genetic programming approach
        
        Args:
            count: Number of strategies to generate
            market_regime: Current market regime
            market_data: Current market context data
            
        Returns:
            List of generated strategy IDs
        """
        try:
            logger.info(f"Generating {count} strategies using genetic programming")
            
            # Initialize random population
            population = []
            for _ in range(self.population_size):
                individual = await self._create_random_individual()
                population.append(individual)
            
            # Evolve population over multiple generations
            generations = self.config.GP_GENERATIONS
            for generation in range(generations):
                # Evaluate fitness of current population
                fitness_scores = await self._evaluate_population_fitness(population)
                
                # Select parents based on fitness
                parents = self._selection(population, fitness_scores)
                
                # Create next generation through crossover and mutation
                next_generation = []
                while len(next_generation) < self.population_size:
                    parent1, parent2 = random.sample(parents, 2)
                    
                    if random.random() < self.crossover_rate:
                        child1, child2 = self._crossover(parent1, parent2)
                    else:
                        child1, child2 = parent1.copy(), parent2.copy()
                    
                    if random.random() < self.mutation_rate:
                        child1 = self._mutate(child1)
                    if random.random() < self.mutation_rate:
                        child2 = self._mutate(child2)
                    
                    next_generation.extend([child1, child2])
                
                population = next_generation[:self.population_size]
            
            # Select best individuals from final population
            final_fitness = await self._evaluate_population_fitness(population)
            best_individuals = sorted(
                zip(population, final_fitness), 
                key=lambda x: x[1], 
                reverse=True
            )[:count]
            
            # Convert to strategy configurations and save
            strategy_ids = []
            for individual, fitness in best_individuals:
                strategy_id = await self._save_strategy_from_individual(individual)
                strategy_ids.append(strategy_id)
            
            logger.info(f"Generated {len(strategy_ids)} genetic strategies")
            return strategy_ids
            
        except Exception as e:
            logger.error(f"Error generating genetic strategies: {e}")
            return []

    async def generate_ml_strategies(self, count: int, model_ensemble) -> List[str]:
        """Generate strategies using ML model suggestions"""
        try:
            logger.info(f"Generating {count} ML-driven strategies")
            
            strategy_ids = []
            
            # Get recent market data for ML analysis
            market_features = await self._extract_market_features()
            
            for _ in range(count):
                # Use ML models to suggest strategy parameters
                strategy_suggestion = await model_ensemble.suggest_strategy_config(
                    market_features=market_features,
                    strategy_type=random.choice(list(StrategyType))
                )
                
                # Create strategy from ML suggestion
                strategy_config = await self._create_strategy_from_ml_suggestion(
                    strategy_suggestion
                )
                
                strategy_id = await self._save_strategy_config(strategy_config)
                strategy_ids.append(strategy_id)
            
            logger.info(f"Generated {len(strategy_ids)} ML-driven strategies")
            return strategy_ids
            
        except Exception as e:
            logger.error(f"Error generating ML strategies: {e}")
            return []

    async def generate_systematic_strategies(self, count: int, 
                                           strategy_types: Optional[List[str]] = None) -> List[str]:
        """Generate strategies through systematic parameter space exploration"""
        try:
            logger.info(f"Generating {count} systematic strategies")
            
            if strategy_types is None:
                strategy_types = [t.value for t in StrategyType]
            
            strategy_ids = []
            strategies_per_type = count // len(strategy_types)
            
            for strategy_type in strategy_types:
                type_enum = StrategyType(strategy_type)
                template = self.strategy_templates[type_enum]
                
                # Generate parameter combinations
                param_combinations = self._generate_parameter_combinations(
                    template, strategies_per_type
                )
                
                for params in param_combinations:
                    strategy_config = await self._create_systematic_strategy(
                        type_enum, template, params
                    )
                    
                    strategy_id = await self._save_strategy_config(strategy_config)
                    strategy_ids.append(strategy_id)
            
            logger.info(f"Generated {len(strategy_ids)} systematic strategies")
            return strategy_ids
            
        except Exception as e:
            logger.error(f"Error generating systematic strategies: {e}")
            return []

    async def generate_ensemble_strategies(self, count: int, 
                                         top_performers: List[Dict]) -> List[str]:
        """Generate ensemble strategies by combining top performers"""
        try:
            logger.info(f"Generating {count} ensemble strategies")
            
            strategy_ids = []
            
            if len(top_performers) < 2:
                logger.warning("Not enough top performers for ensemble generation")
                return []
            
            for _ in range(count):
                # Select 2-4 strategies to combine
                ensemble_size = random.randint(2, min(4, len(top_performers)))
                selected_strategies = random.sample(top_performers, ensemble_size)
                
                # Create ensemble configuration
                ensemble_config = await self._create_ensemble_config(selected_strategies)
                
                strategy_id = await self._save_strategy_config(ensemble_config)
                strategy_ids.append(strategy_id)
            
            logger.info(f"Generated {len(strategy_ids)} ensemble strategies")
            return strategy_ids
            
        except Exception as e:
            logger.error(f"Error generating ensemble strategies: {e}")
            return []

    # Genetic Programming Helper Methods
    async def _create_random_individual(self) -> Dict:
        """Create a random strategy individual for genetic programming"""
        individual = {
            'strategy_type': random.choice(list(StrategyType)).value,
            'indicators': {},
            'timeframes': random.sample(
                ['5m', '15m', '1h', '4h', '1d'], 
                random.randint(1, 3)
            ),
            'risk_parameters': {
                'stop_loss_pct': random.uniform(0.01, 0.05),
                'take_profit_pct': random.uniform(0.02, 0.10),
                'position_size_pct': random.uniform(0.05, 0.25)
            },
            'entry_conditions': [],
            'exit_conditions': []
        }
        
        # Add random indicators
        num_indicators = random.randint(2, 5)
        selected_indicators = random.sample(list(self.indicators.keys()), num_indicators)
        
        for indicator_name in selected_indicators:
            indicator_config = self.indicators[indicator_name]
            params = {}
            
            # Generate random parameters within optimization ranges
            for param_name, (min_val, max_val) in indicator_config.optimization_ranges.items():
                if isinstance(min_val, int):
                    params[param_name] = random.randint(int(min_val), int(max_val))
                else:
                    params[param_name] = random.uniform(min_val, max_val)
            
            individual['indicators'][indicator_name] = params
        
        return individual

    async def _evaluate_population_fitness(self, population: List[Dict]) -> List[float]:
        """Evaluate fitness of entire population using backtesting"""
        fitness_scores = []
        
        # Run quick backtests for fitness evaluation
        for individual in population:
            try:
                # Convert individual to strategy config
                strategy_config = await self._individual_to_strategy_config(individual)
                
                # Run simplified backtest (shorter period for speed)
                fitness_score = await self._quick_backtest_fitness(strategy_config)
                fitness_scores.append(fitness_score)
                
            except Exception as e:
                logger.error(f"Error evaluating fitness: {e}")
                fitness_scores.append(0.0)  # Assign low fitness for errors
        
        return fitness_scores

    def _selection(self, population: List[Dict], fitness_scores: List[float]) -> List[Dict]:
        """Tournament selection for genetic programming"""
        parents = []
        tournament_size = 3
        
        for _ in range(len(population) // 2):
            # Tournament selection
            tournament_indices = random.sample(range(len(population)), tournament_size)
            tournament_fitness = [fitness_scores[i] for i in tournament_indices]
            winner_idx = tournament_indices[tournament_fitness.index(max(tournament_fitness))]
            parents.append(population[winner_idx])
        
        return parents

    def _crossover(self, parent1: Dict, parent2: Dict) -> Tuple[Dict, Dict]:
        """Crossover operation for genetic programming"""
        child1 = parent1.copy()
        child2 = parent2.copy()
        
        # Crossover indicators
        p1_indicators = list(parent1['indicators'].keys())
        p2_indicators = list(parent2['indicators'].keys())
        
        # Exchange some indicators between parents
        if p1_indicators and p2_indicators:
            crossover_point = random.randint(1, min(len(p1_indicators), len(p2_indicators)))
            
            child1['indicators'] = {}
            child2['indicators'] = {}
            
            # First part from parent1, second part from parent2
            for i, indicator in enumerate(p1_indicators):
                if i < crossover_point:
                    child1['indicators'][indicator] = parent1['indicators'][indicator]
                else:
                    if indicator in parent2['indicators']:
                        child1['indicators'][indicator] = parent2['indicators'][indicator]
            
            for i, indicator in enumerate(p2_indicators):
                if i < crossover_point:
                    child2['indicators'][indicator] = parent2['indicators'][indicator]
                else:
                    if indicator in parent1['indicators']:
                        child2['indicators'][indicator] = parent1['indicators'][indicator]
        
        # Crossover risk parameters
        for param in child1['risk_parameters']:
            if random.random() < 0.5:
                child1['risk_parameters'][param], child2['risk_parameters'][param] = \
                    child2['risk_parameters'][param], child1['risk_parameters'][param]
        
        return child1, child2

    def _mutate(self, individual: Dict) -> Dict:
        """Mutation operation for genetic programming"""
        mutated = individual.copy()
        
        # Mutate indicator parameters
        for indicator_name, params in mutated['indicators'].items():
            if indicator_name in self.indicators:
                indicator_config = self.indicators[indicator_name]
                
                for param_name, current_value in params.items():
                    if (param_name in indicator_config.optimization_ranges and 
                        random.random() < 0.1):  # 10% mutation chance per parameter
                        
                        min_val, max_val = indicator_config.optimization_ranges[param_name]
                        if isinstance(current_value, int):
                            mutated['indicators'][indicator_name][param_name] = \
                                random.randint(int(min_val), int(max_val))
                        else:
                            mutated['indicators'][indicator_name][param_name] = \
                                random.uniform(min_val, max_val)
        
        # Mutate risk parameters
        for param_name in mutated['risk_parameters']:
            if random.random() < 0.1:
                current_value = mutated['risk_parameters'][param_name]
                mutation_factor = random.uniform(0.8, 1.2)  # ±20% mutation
                mutated['risk_parameters'][param_name] = current_value * mutation_factor
        
        return mutated

    # Helper methods for strategy creation and saving
    async def _save_strategy_from_individual(self, individual: Dict) -> str:
        """Save a genetic programming individual as a strategy"""
        strategy_id = str(uuid.uuid4())
        
        strategy_doc = {
            'id': strategy_id,
            'name': f"Genetic_Strategy_{strategy_id[:8]}",
            'strategy_type': individual['strategy_type'],
            'generation_method': 'genetic_programming',
            'indicators': individual['indicators'],
            'timeframes': individual['timeframes'],
            'risk_parameters': individual['risk_parameters'],
            'status': 'testing',
            'created_at': datetime.now().isoformat(),
            'last_optimized': datetime.now().isoformat()
        }
        
        await self.db.create_strategy(strategy_doc)
        return strategy_id

    async def _save_strategy_config(self, strategy_config: Dict) -> str:
        """Save a strategy configuration to the database"""
        strategy_id = str(uuid.uuid4())
        strategy_config['id'] = strategy_id
        strategy_config['created_at'] = datetime.now().isoformat()
        strategy_config['last_optimized'] = datetime.now().isoformat()
        strategy_config['status'] = 'testing'
        
        await self.db.create_strategy(strategy_config)
        return strategy_id

    async def _individual_to_strategy_config(self, individual: Dict) -> Dict:
        """Convert genetic programming individual to strategy configuration"""
        return individual

    async def _quick_backtest_fitness(self, strategy_config: Dict) -> float:
        """Run quick backtest to evaluate strategy fitness"""
        # Simplified fitness calculation based on strategy configuration
        # In real implementation, this would run actual backtesting
        
        # For now, return a random fitness score
        # This should be replaced with actual backtest results
        return random.uniform(0.0, 2.0)  # Sharpe ratio range

    async def _extract_market_features(self) -> Dict:
        """Extract current market features for ML analysis"""
        # Implementation would extract features from current market data
        return {
            'volatility': 0.025,
            'trend_strength': 0.65,
            'volume_trend': 0.82,
            'sentiment_score': 0.45
        }

    async def _create_strategy_from_ml_suggestion(self, suggestion: Dict) -> Dict:
        """Create strategy configuration from ML model suggestion"""
        # Implementation would convert ML suggestion to strategy config
        return suggestion

    def _generate_parameter_combinations(self, template: Dict, count: int) -> List[Dict]:
        """Generate systematic parameter combinations for strategy template"""
        combinations = []
        
        # Implementation would generate systematic parameter combinations
        # For now, return random combinations
        for _ in range(count):
            combinations.append({
                'param_set': random.randint(1, 100),
                'variation': random.choice(['A', 'B', 'C'])
            })
        
        return combinations

    async def _create_systematic_strategy(self, strategy_type: StrategyType, 
                                        template: Dict, params: Dict) -> Dict:
        """Create systematic strategy from template and parameters"""
        # Implementation would create detailed strategy config
        return {
            'name': f"Systematic_{strategy_type.value}_{params.get('param_set', 0)}",
            'strategy_type': strategy_type.value,
            'generation_method': 'systematic',
            'template': template,
            'parameters': params
        }

    async def _create_ensemble_config(self, selected_strategies: List[Dict]) -> Dict:
        """Create ensemble strategy configuration"""
        ensemble_id = str(uuid.uuid4())[:8]
        
        return {
            'name': f"Ensemble_Strategy_{ensemble_id}",
            'strategy_type': 'ensemble',
            'generation_method': 'ensemble',
            'component_strategies': [s['id'] for s in selected_strategies],
            'weighting_method': 'performance_based',
            'rebalance_frequency': 'daily'
        }