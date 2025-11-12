"""
AutoML Optimizer using Optuna

This module implements automated hyperparameter optimization for trading strategies
using Optuna with PostgreSQL as the storage backend.

Features:
- Strategy parameter optimization
- Model architecture selection
- Multi-objective optimization (Sharpe, return, drawdown)
- Distributed optimization support
- Automatic pruning of unpromising trials
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable, Tuple
import structlog

try:
    import optuna
    from optuna.storages import RDBStorage
    from optuna.pruners import MedianPruner
    from optuna.samplers import TPESampler
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    optuna = None

logger = structlog.get_logger()


class AutoMLOptimizer:
    """
    AutoML optimizer using Optuna for hyperparameter tuning
    
    Integrates with existing backtest engine to find optimal strategy parameters.
    Stores optimization history in PostgreSQL for analysis and reproducibility.
    """
    
    def __init__(
        self,
        database_url: str,
        study_name: str = "strategy_optimization",
        direction: str = "maximize",
        n_jobs: int = 1,
        storage_timeout: int = 300
    ):
        """
        Initialize AutoML optimizer
        
        Args:
            database_url: PostgreSQL connection URL
            study_name: Name of the optimization study
            direction: 'maximize' or 'minimize' the objective
            n_jobs: Number of parallel jobs
            storage_timeout: Database connection timeout in seconds
        """
        if not OPTUNA_AVAILABLE:
            raise ImportError(
                "Optuna is required for AutoML optimization. "
                "Install it via: pip install optuna"
            )
        
        self.database_url = database_url
        self.study_name = study_name
        self.direction = direction
        self.n_jobs = n_jobs
        
        # Create storage backend
        self.storage = RDBStorage(
            url=database_url,
            engine_kwargs={
                "pool_size": 20,
                "max_overflow": 0,
                "connect_args": {"connect_timeout": storage_timeout}
            }
        )
        
        # Create or load study
        self.study = optuna.create_study(
            study_name=study_name,
            storage=self.storage,
            load_if_exists=True,
            direction=direction,
            sampler=TPESampler(seed=42),  # Tree-structured Parzen Estimator
            pruner=MedianPruner(n_startup_trials=5, n_warmup_steps=10)
        )
        
        logger.info(
            "automl_optimizer_initialized",
            study_name=study_name,
            direction=direction,
            n_jobs=n_jobs
        )
    
    async def optimize_strategy_parameters(
        self,
        strategy_type: str,
        backtest_func: Callable,
        symbol: str = "BTCUSDC",
        n_trials: int = 100,
        timeout: Optional[int] = None,
        parameter_space: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Optimize strategy parameters using Optuna
        
        Args:
            strategy_type: Type of strategy (e.g., 'momentum', 'mean_reversion')
            backtest_func: Async function that backtests strategy and returns metrics
            symbol: Trading symbol
            n_trials: Number of optimization trials
            timeout: Maximum optimization time in seconds
            parameter_space: Custom parameter space definition
            
        Returns:
            Dict with best parameters and performance metrics
        """
        logger.info(
            "starting_strategy_optimization",
            strategy_type=strategy_type,
            symbol=symbol,
            n_trials=n_trials
        )
        
        # Define default parameter space if not provided
        if parameter_space is None:
            parameter_space = self._get_default_parameter_space(strategy_type)
        
        def objective(trial: optuna.Trial) -> float:
            """Objective function for Optuna"""
            # Suggest parameters
            params = {}
            for param_name, param_config in parameter_space.items():
                if param_config['type'] == 'int':
                    params[param_name] = trial.suggest_int(
                        param_name,
                        param_config['low'],
                        param_config['high']
                    )
                elif param_config['type'] == 'float':
                    params[param_name] = trial.suggest_float(
                        param_name,
                        param_config['low'],
                        param_config['high'],
                        log=param_config.get('log', False)
                    )
                elif param_config['type'] == 'categorical':
                    params[param_name] = trial.suggest_categorical(
                        param_name,
                        param_config['choices']
                    )
            
            # Run backtest (convert async to sync for Optuna)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Create new event loop for nested async call
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            backtest_func(strategy_type, params, symbol)
                        )
                        results = future.result(timeout=300)
                else:
                    results = loop.run_until_complete(
                        backtest_func(strategy_type, params, symbol)
                    )
                
                # Extract objective metric (Sharpe ratio by default)
                sharpe = results.get('sharpe_ratio', 0.0)
                
                # Report intermediate values for pruning
                trial.report(sharpe, step=0)
                
                # Check if trial should be pruned
                if trial.should_prune():
                    raise optuna.TrialPruned()
                
                return sharpe
                
            except Exception as e:
                logger.error(
                    "backtest_failed_in_optimization",
                    error=str(e),
                    params=params
                )
                return -999.0  # Penalty for failed trials
        
        # Run optimization
        try:
            self.study.optimize(
                objective,
                n_trials=n_trials,
                timeout=timeout,
                n_jobs=self.n_jobs,
                show_progress_bar=False
            )
            
            best_params = self.study.best_params
            best_value = self.study.best_value
            
            logger.info(
                "optimization_completed",
                strategy_type=strategy_type,
                best_sharpe=best_value,
                best_params=best_params,
                n_trials=len(self.study.trials)
            )
            
            return {
                'best_parameters': best_params,
                'best_sharpe_ratio': best_value,
                'n_trials': len(self.study.trials),
                'optimization_time': sum(
                    t.duration.total_seconds()
                    for t in self.study.trials
                    if t.duration
                ),
                'study_name': self.study_name
            }
            
        except Exception as e:
            logger.error(
                "optimization_failed",
                error=str(e),
                strategy_type=strategy_type
            )
            raise
    
    async def optimize_model_architecture(
        self,
        model_type: str,
        train_func: Callable,
        n_trials: int = 50,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Optimize ML model architecture and hyperparameters
        
        Args:
            model_type: Type of model ('xgboost', 'lightgbm', 'neural_network')
            train_func: Function that trains model and returns validation score
            n_trials: Number of trials
            timeout: Time limit in seconds
            
        Returns:
            Best architecture configuration
        """
        logger.info(
            "starting_architecture_optimization",
            model_type=model_type,
            n_trials=n_trials
        )
        
        def objective(trial: optuna.Trial) -> float:
            """Objective for architecture search"""
            if model_type == 'xgboost':
                config = {
                    'n_estimators': trial.suggest_int('n_estimators', 50, 500),
                    'max_depth': trial.suggest_int('max_depth', 3, 12),
                    'learning_rate': trial.suggest_float('learning_rate', 0.001, 0.3, log=True),
                    'subsample': trial.suggest_float('subsample', 0.5, 1.0),
                    'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
                    'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
                    'gamma': trial.suggest_float('gamma', 0.0, 5.0),
                }
            elif model_type == 'lightgbm':
                config = {
                    'n_estimators': trial.suggest_int('n_estimators', 50, 500),
                    'max_depth': trial.suggest_int('max_depth', 3, 12),
                    'learning_rate': trial.suggest_float('learning_rate', 0.001, 0.3, log=True),
                    'num_leaves': trial.suggest_int('num_leaves', 20, 100),
                    'subsample': trial.suggest_float('subsample', 0.5, 1.0),
                    'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
                    'min_child_samples': trial.suggest_int('min_child_samples', 5, 100),
                }
            elif model_type == 'neural_network':
                config = {
                    'n_layers': trial.suggest_int('n_layers', 1, 5),
                    'hidden_size': trial.suggest_int('hidden_size', 32, 512),
                    'dropout': trial.suggest_float('dropout', 0.1, 0.5),
                    'learning_rate': trial.suggest_float('learning_rate', 0.0001, 0.01, log=True),
                    'batch_size': trial.suggest_categorical('batch_size', [32, 64, 128, 256]),
                }
            else:
                raise ValueError(f"Unknown model type: {model_type}")
            
            # Train model
            try:
                score = train_func(config)
                return score
            except Exception as e:
                logger.error("training_failed", error=str(e), config=config)
                return -999.0
        
        # Run optimization
        study = optuna.create_study(
            study_name=f"{self.study_name}_{model_type}_architecture",
            storage=self.storage,
            load_if_exists=True,
            direction="maximize",
            sampler=TPESampler(seed=42),
            pruner=MedianPruner()
        )
        
        study.optimize(
            objective,
            n_trials=n_trials,
            timeout=timeout,
            n_jobs=self.n_jobs
        )
        
        logger.info(
            "architecture_optimization_completed",
            model_type=model_type,
            best_score=study.best_value,
            best_config=study.best_params
        )
        
        return {
            'model_type': model_type,
            'best_config': study.best_params,
            'best_score': study.best_value,
            'n_trials': len(study.trials)
        }
    
    def get_optimization_history(
        self,
        study_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get optimization history for analysis
        
        Args:
            study_name: Specific study name (default: current study)
            
        Returns:
            List of trial results
        """
        target_study = self.study
        if study_name:
            target_study = optuna.load_study(
                study_name=study_name,
                storage=self.storage
            )
        
        trials = []
        for trial in target_study.trials:
            trials.append({
                'number': trial.number,
                'value': trial.value,
                'params': trial.params,
                'state': trial.state.name,
                'datetime_start': trial.datetime_start.isoformat() if trial.datetime_start else None,
                'datetime_complete': trial.datetime_complete.isoformat() if trial.datetime_complete else None,
                'duration': trial.duration.total_seconds() if trial.duration else None
            })
        
        return trials
    
    def get_best_trials(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get top N best trials"""
        trials = sorted(
            self.study.trials,
            key=lambda t: t.value if t.value else -float('inf'),
            reverse=(self.direction == 'maximize')
        )
        
        return [
            {
                'number': t.number,
                'value': t.value,
                'params': t.params,
                'state': t.state.name
            }
            for t in trials[:n]
        ]
    
    def _get_default_parameter_space(
        self,
        strategy_type: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get default parameter space for strategy type
        
        Args:
            strategy_type: Strategy type
            
        Returns:
            Parameter space definition
        """
        # Common parameters for all strategies
        base_params = {
            'position_size': {
                'type': 'float',
                'low': 0.01,
                'high': 0.2
            },
            'stop_loss_pct': {
                'type': 'float',
                'low': 0.01,
                'high': 0.05
            },
            'take_profit_pct': {
                'type': 'float',
                'low': 0.02,
                'high': 0.10
            }
        }
        
        # Strategy-specific parameters
        if strategy_type == 'momentum':
            strategy_params = {
                'lookback_period': {
                    'type': 'int',
                    'low': 5,
                    'high': 50
                },
                'momentum_threshold': {
                    'type': 'float',
                    'low': 0.01,
                    'high': 0.10
                }
            }
        elif strategy_type == 'mean_reversion':
            strategy_params = {
                'lookback_period': {
                    'type': 'int',
                    'low': 10,
                    'high': 100
                },
                'std_threshold': {
                    'type': 'float',
                    'low': 1.0,
                    'high': 3.0
                }
            }
        elif strategy_type == 'breakout':
            strategy_params = {
                'lookback_period': {
                    'type': 'int',
                    'low': 10,
                    'high': 50
                },
                'breakout_threshold': {
                    'type': 'float',
                    'low': 0.01,
                    'high': 0.05
                }
            }
        else:
            # Generic parameters
            strategy_params = {
                'lookback_period': {
                    'type': 'int',
                    'low': 5,
                    'high': 100
                },
                'threshold': {
                    'type': 'float',
                    'low': 0.01,
                    'high': 0.10
                }
            }
        
        return {**base_params, **strategy_params}


class MultiObjectiveOptimizer(AutoMLOptimizer):
    """
    Multi-objective optimization for trading strategies
    
    Optimizes multiple metrics simultaneously (Sharpe, return, drawdown)
    """
    
    def __init__(self, database_url: str, study_name: str = "multi_objective_opt"):
        """Initialize multi-objective optimizer"""
        if not OPTUNA_AVAILABLE:
            raise ImportError("Optuna required for multi-objective optimization")
        
        self.database_url = database_url
        self.study_name = study_name
        
        # Create storage
        self.storage = RDBStorage(url=database_url)
        
        # Create multi-objective study
        self.study = optuna.create_study(
            study_name=study_name,
            storage=self.storage,
            load_if_exists=True,
            directions=["maximize", "maximize", "minimize"],  # Sharpe, Return, Drawdown
            sampler=TPESampler(seed=42)
        )
        
        logger.info("multi_objective_optimizer_initialized", study_name=study_name)
    
    async def optimize_multi_objective(
        self,
        strategy_type: str,
        backtest_func: Callable,
        symbol: str = "BTCUSDC",
        n_trials: int = 100,
        parameter_space: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Optimize multiple objectives simultaneously
        
        Returns Pareto-optimal solutions
        """
        if parameter_space is None:
            parameter_space = self._get_default_parameter_space(strategy_type)
        
        def objective(trial: optuna.Trial) -> Tuple[float, float, float]:
            """Multi-objective function"""
            params = {}
            for param_name, param_config in parameter_space.items():
                if param_config['type'] == 'int':
                    params[param_name] = trial.suggest_int(
                        param_name, param_config['low'], param_config['high']
                    )
                elif param_config['type'] == 'float':
                    params[param_name] = trial.suggest_float(
                        param_name, param_config['low'], param_config['high']
                    )
            
            try:
                loop = asyncio.get_event_loop()
                results = loop.run_until_complete(
                    backtest_func(strategy_type, params, symbol)
                )
                
                sharpe = results.get('sharpe_ratio', 0.0)
                cagr = results.get('cagr', 0.0)
                max_dd = abs(results.get('max_drawdown', 100.0))
                
                return sharpe, cagr, max_dd
                
            except Exception as e:
                logger.error("multi_objective_backtest_failed", error=str(e))
                return -999.0, -999.0, 999.0
        
        self.study.optimize(objective, n_trials=n_trials, n_jobs=self.n_jobs)
        
        # Get Pareto front
        pareto_trials = [
            t for t in self.study.best_trials
        ]
        
        logger.info(
            "multi_objective_completed",
            n_pareto_solutions=len(pareto_trials),
            n_trials=len(self.study.trials)
        )
        
        return {
            'pareto_solutions': [
                {
                    'params': t.params,
                    'sharpe': t.values[0],
                    'cagr': t.values[1],
                    'max_drawdown': t.values[2]
                }
                for t in pareto_trials
            ],
            'n_trials': len(self.study.trials)
        }
