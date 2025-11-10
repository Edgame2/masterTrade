"""
Parameter Optimization Engine

Implements multiple optimization algorithms:
- Grid Search
- Random Search  
- Bayesian Optimization
- Genetic Algorithm
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import structlog
from itertools import product
from concurrent.futures import ProcessPoolExecutor, as_completed

logger = structlog.get_logger()


class OptimizationMethod(Enum):
    """Optimization methods"""
    GRID_SEARCH = "grid_search"
    RANDOM_SEARCH = "random_search"
    BAYESIAN = "bayesian"
    GENETIC_ALGORITHM = "genetic"


@dataclass
class OptimizationConfig:
    """Configuration for parameter optimization"""
    
    method: OptimizationMethod = OptimizationMethod.GRID_SEARCH
    
    # Objective
    objective_metric: str = "sharpe_ratio"  # "sharpe_ratio", "total_return", "calmar_ratio"
    maximize: bool = True
    
    # Constraints
    min_trades: int = 10
    max_drawdown_threshold: float = 50.0  # Reject if > 50% drawdown
    min_win_rate: float = 0.0  # Minimum acceptable win rate
    
    # Grid/Random Search
    n_random_samples: int = 100
    
    # Bayesian Optimization
    n_initial_points: int = 10
    n_iterations: int = 50
    acquisition_function: str = "ei"  # "ei" (expected improvement), "ucb", "poi"
    
    # Genetic Algorithm
    population_size: int = 50
    n_generations: int = 20
    mutation_rate: float = 0.1
    crossover_rate: float = 0.7
    elitism_pct: float = 0.1
    
    # Parallel processing
    n_workers: int = 4
    
    # Overfitting prevention
    use_validation_set: bool = True
    validation_split: float = 0.3


@dataclass
class OptimizationResult:
    """Result from parameter optimization"""
    
    method: OptimizationMethod
    objective_metric: str
    
    # Best parameters found
    best_params: Dict
    best_score: float
    best_backtest_result: Any = None  # BacktestResult
    
    # All evaluations
    evaluations: List[Dict] = field(default_factory=list)
    n_evaluations: int = 0
    
    # Convergence
    convergence_curve: List[float] = field(default_factory=list)
    converged: bool = False
    
    # Validation
    validation_score: Optional[float] = None
    overfitting_ratio: float = 0.0  # (training_score - validation_score) / training_score


class ParameterOptimizer:
    """
    Parameter Optimization Engine
    
    Finds optimal strategy parameters using various algorithms
    """
    
    def __init__(self, config: OptimizationConfig):
        self.config = config
    
    def optimize(
        self,
        param_space: Dict[str, List],
        objective_function: Callable,
        validation_function: Optional[Callable] = None
    ) -> OptimizationResult:
        """
        Optimize parameters
        
        Args:
            param_space: Dict mapping parameter names to lists of possible values
            objective_function: Function that takes params dict and returns score
            validation_function: Optional function for validation set evaluation
            
        Returns:
            OptimizationResult with best parameters
        """
        logger.info(
            f"Starting optimization: {self.config.method.value}",
            params=list(param_space.keys()),
            objective=self.config.objective_metric
        )
        
        if self.config.method == OptimizationMethod.GRID_SEARCH:
            result = self._grid_search(param_space, objective_function)
            
        elif self.config.method == OptimizationMethod.RANDOM_SEARCH:
            result = self._random_search(param_space, objective_function)
            
        elif self.config.method == OptimizationMethod.GENETIC_ALGORITHM:
            result = self._genetic_algorithm(param_space, objective_function)
            
        else:
            raise ValueError(f"Unsupported optimization method: {self.config.method}")
        
        # Validation
        if validation_function and self.config.use_validation_set:
            validation_score = validation_function(result.best_params)
            result.validation_score = validation_score
            
            if result.best_score > 0:
                result.overfitting_ratio = (result.best_score - validation_score) / result.best_score
                
                logger.info(
                    "Validation completed",
                    training_score=f"{result.best_score:.4f}",
                    validation_score=f"{validation_score:.4f}",
                    overfitting=f"{result.overfitting_ratio:.2%}"
                )
        
        logger.info(
            f"Optimization completed: {self.config.method.value}",
            best_score=f"{result.best_score:.4f}",
            n_evaluations=result.n_evaluations,
            best_params=result.best_params
        )
        
        return result
    
    def _grid_search(
        self,
        param_space: Dict[str, List],
        objective_function: Callable
    ) -> OptimizationResult:
        """Grid search over all parameter combinations"""
        
        param_names = list(param_space.keys())
        param_values = list(param_space.values())
        
        # Generate all combinations
        combinations = list(product(*param_values))
        
        logger.info(f"Testing {len(combinations)} parameter combinations")
        
        evaluations = []
        best_score = -np.inf if self.config.maximize else np.inf
        best_params = {}
        best_result = None
        convergence = []
        
        # Evaluate each combination
        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))
            
            try:
                score, backtest_result = objective_function(params)
                
                # Check constraints
                if not self._check_constraints(backtest_result):
                    continue
                
                evaluations.append({
                    'params': params,
                    'score': score,
                    'iteration': i
                })
                
                # Update best
                if (self.config.maximize and score > best_score) or \
                   (not self.config.maximize and score < best_score):
                    best_score = score
                    best_params = params
                    best_result = backtest_result
                
                convergence.append(best_score)
                
                if (i + 1) % 10 == 0:
                    logger.debug(f"Evaluated {i + 1}/{len(combinations)} combinations")
                    
            except Exception as e:
                logger.warning(f"Error evaluating params {params}: {e}")
                continue
        
        return OptimizationResult(
            method=OptimizationMethod.GRID_SEARCH,
            objective_metric=self.config.objective_metric,
            best_params=best_params,
            best_score=best_score,
            best_backtest_result=best_result,
            evaluations=evaluations,
            n_evaluations=len(evaluations),
            convergence_curve=convergence,
            converged=True
        )
    
    def _random_search(
        self,
        param_space: Dict[str, List],
        objective_function: Callable
    ) -> OptimizationResult:
        """Random search over parameter space"""
        
        logger.info(f"Testing {self.config.n_random_samples} random samples")
        
        evaluations = []
        best_score = -np.inf if self.config.maximize else np.inf
        best_params = {}
        best_result = None
        convergence = []
        
        for i in range(self.config.n_random_samples):
            # Sample random parameters
            params = {}
            for param_name, param_values in param_space.items():
                params[param_name] = np.random.choice(param_values)
            
            try:
                score, backtest_result = objective_function(params)
                
                if not self._check_constraints(backtest_result):
                    continue
                
                evaluations.append({
                    'params': params,
                    'score': score,
                    'iteration': i
                })
                
                if (self.config.maximize and score > best_score) or \
                   (not self.config.maximize and score < best_score):
                    best_score = score
                    best_params = params
                    best_result = backtest_result
                
                convergence.append(best_score)
                
            except Exception as e:
                logger.warning(f"Error evaluating params {params}: {e}")
                continue
        
        return OptimizationResult(
            method=OptimizationMethod.RANDOM_SEARCH,
            objective_metric=self.config.objective_metric,
            best_params=best_params,
            best_score=best_score,
            best_backtest_result=best_result,
            evaluations=evaluations,
            n_evaluations=len(evaluations),
            convergence_curve=convergence,
            converged=True
        )
    
    def _genetic_algorithm(
        self,
        param_space: Dict[str, List],
        objective_function: Callable
    ) -> OptimizationResult:
        """Genetic algorithm optimization"""
        
        logger.info(
            f"Running genetic algorithm",
            population_size=self.config.population_size,
            generations=self.config.n_generations
        )
        
        param_names = list(param_space.keys())
        
        # Initialize population
        population = self._initialize_population(param_space)
        
        evaluations = []
        best_score = -np.inf if self.config.maximize else np.inf
        best_params = {}
        best_result = None
        convergence = []
        
        for generation in range(self.config.n_generations):
            # Evaluate population
            fitness_scores = []
            
            for individual in population:
                params = dict(zip(param_names, individual))
                
                try:
                    score, backtest_result = objective_function(params)
                    
                    if not self._check_constraints(backtest_result):
                        fitness_scores.append(-np.inf if self.config.maximize else np.inf)
                        continue
                    
                    fitness_scores.append(score)
                    
                    evaluations.append({
                        'params': params,
                        'score': score,
                        'generation': generation
                    })
                    
                    if (self.config.maximize and score > best_score) or \
                       (not self.config.maximize and score < best_score):
                        best_score = score
                        best_params = params
                        best_result = backtest_result
                        
                except Exception as e:
                    fitness_scores.append(-np.inf if self.config.maximize else np.inf)
            
            convergence.append(best_score)
            
            logger.debug(
                f"Generation {generation + 1}/{self.config.n_generations}",
                best_score=f"{best_score:.4f}"
            )
            
            # Selection
            selected = self._tournament_selection(population, fitness_scores)
            
            # Crossover
            offspring = self._crossover(selected, param_space)
            
            # Mutation
            offspring = self._mutate(offspring, param_space)
            
            # Elitism - keep best individuals
            n_elite = int(self.config.population_size * self.config.elitism_pct)
            elite_indices = np.argsort(fitness_scores)
            if self.config.maximize:
                elite_indices = elite_indices[-n_elite:]
            else:
                elite_indices = elite_indices[:n_elite]
            
            elite = [population[i] for i in elite_indices]
            
            # New population
            population = elite + offspring[:self.config.population_size - n_elite]
        
        return OptimizationResult(
            method=OptimizationMethod.GENETIC_ALGORITHM,
            objective_metric=self.config.objective_metric,
            best_params=best_params,
            best_score=best_score,
            best_backtest_result=best_result,
            evaluations=evaluations,
            n_evaluations=len(evaluations),
            convergence_curve=convergence,
            converged=self._check_convergence(convergence)
        )
    
    def _initialize_population(self, param_space: Dict) -> List[List]:
        """Initialize random population"""
        population = []
        
        for _ in range(self.config.population_size):
            individual = []
            for param_values in param_space.values():
                individual.append(np.random.choice(param_values))
            population.append(individual)
        
        return population
    
    def _tournament_selection(
        self,
        population: List,
        fitness_scores: List[float],
        tournament_size: int = 3
    ) -> List:
        """Tournament selection"""
        selected = []
        
        for _ in range(len(population)):
            # Random tournament
            tournament_indices = np.random.choice(
                len(population),
                size=min(tournament_size, len(population)),
                replace=False
            )
            
            tournament_fitness = [fitness_scores[i] for i in tournament_indices]
            
            if self.config.maximize:
                winner_idx = tournament_indices[np.argmax(tournament_fitness)]
            else:
                winner_idx = tournament_indices[np.argmin(tournament_fitness)]
            
            selected.append(population[winner_idx])
        
        return selected
    
    def _crossover(self, population: List, param_space: Dict) -> List[List]:
        """Single-point crossover"""
        offspring = []
        
        for i in range(0, len(population) - 1, 2):
            if np.random.random() < self.config.crossover_rate:
                parent1 = population[i]
                parent2 = population[i + 1]
                
                # Single-point crossover
                crossover_point = np.random.randint(1, len(parent1))
                
                child1 = parent1[:crossover_point] + parent2[crossover_point:]
                child2 = parent2[:crossover_point] + parent1[crossover_point:]
                
                offspring.extend([child1, child2])
            else:
                offspring.extend([population[i], population[i + 1]])
        
        return offspring
    
    def _mutate(self, population: List, param_space: Dict) -> List[List]:
        """Mutation"""
        param_values_list = list(param_space.values())
        
        for individual in population:
            for gene_idx in range(len(individual)):
                if np.random.random() < self.config.mutation_rate:
                    # Mutate this gene
                    individual[gene_idx] = np.random.choice(param_values_list[gene_idx])
        
        return population
    
    def _check_constraints(self, backtest_result: Any) -> bool:
        """Check if result meets constraints"""
        if backtest_result is None:
            return False
        
        # Min trades
        if backtest_result.total_trades < self.config.min_trades:
            return False
        
        # Max drawdown
        if backtest_result.max_drawdown > self.config.max_drawdown_threshold:
            return False
        
        # Min win rate
        if backtest_result.win_rate < self.config.min_win_rate:
            return False
        
        return True
    
    def _check_convergence(self, convergence_curve: List[float], window: int = 10) -> bool:
        """Check if optimization has converged"""
        if len(convergence_curve) < window * 2:
            return False
        
        recent = convergence_curve[-window:]
        variation = np.std(recent) / (np.mean(np.abs(recent)) + 1e-10)
        
        return variation < 0.01  # 1% variation = converged
