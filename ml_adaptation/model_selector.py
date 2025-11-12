"""
Model Selector for Automated ML Model Selection

This module implements automated model selection using Optuna to find the best
model architecture and hyperparameters for trading signal prediction.

Supported Models:
- XGBoost: Gradient boosting for tabular data
- LightGBM: Fast gradient boosting
- Neural Networks: Deep learning models for complex patterns
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import structlog

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False

try:
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

logger = structlog.get_logger()


class TradingNeuralNetwork(nn.Module):
    """
    Feedforward neural network for trading signal prediction
    """
    
    def __init__(
        self,
        input_size: int,
        hidden_sizes: List[int],
        output_size: int = 3,  # BUY, SELL, HOLD
        dropout: float = 0.3
    ):
        super(TradingNeuralNetwork, self).__init__()
        
        layers = []
        prev_size = input_size
        
        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(prev_size, hidden_size))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
            prev_size = hidden_size
        
        layers.append(nn.Linear(prev_size, output_size))
        layers.append(nn.Softmax(dim=1))
        
        self.network = nn.Sequential(*layers)
    
    def forward(self, x):
        return self.network(x)


class ModelSelector:
    """
    Automated model selection using Optuna
    
    Compares XGBoost, LightGBM, and Neural Networks to find best model
    for trading signal prediction.
    """
    
    def __init__(
        self,
        database_url: str,
        feature_store=None,
        random_state: int = 42
    ):
        """
        Initialize model selector
        
        Args:
            database_url: PostgreSQL connection URL
            feature_store: FeatureStore instance for data retrieval
            random_state: Random seed for reproducibility
        """
        self.database_url = database_url
        self.feature_store = feature_store
        self.random_state = random_state
        
        # Check available libraries
        self.available_models = []
        if XGBOOST_AVAILABLE:
            self.available_models.append('xgboost')
        if LIGHTGBM_AVAILABLE:
            self.available_models.append('lightgbm')
        if PYTORCH_AVAILABLE:
            self.available_models.append('neural_network')
        
        if not self.available_models:
            raise ImportError(
                "No ML libraries available. Install xgboost, lightgbm, or pytorch"
            )
        
        logger.info(
            "model_selector_initialized",
            available_models=self.available_models
        )
    
    async def select_best_model(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        n_trials_per_model: int = 50,
        metric: str = 'f1_weighted'
    ) -> Dict[str, Any]:
        """
        Select best model by comparing all available models
        
        Args:
            X_train: Training features
            y_train: Training labels (0=SELL, 1=HOLD, 2=BUY)
            X_val: Validation features
            y_val: Validation labels
            n_trials_per_model: Number of Optuna trials per model type
            metric: Metric to optimize ('accuracy', 'f1_weighted', 'precision', 'recall')
            
        Returns:
            Dict with best model type, hyperparameters, and performance
        """
        logger.info(
            "starting_model_selection",
            n_samples_train=len(X_train),
            n_samples_val=len(X_val),
            n_features=X_train.shape[1],
            n_trials_per_model=n_trials_per_model
        )
        
        results = {}
        
        # Try each available model
        for model_type in self.available_models:
            logger.info(f"evaluating_{model_type}")
            
            try:
                if model_type == 'xgboost':
                    result = await self._optimize_xgboost(
                        X_train, y_train, X_val, y_val, n_trials_per_model, metric
                    )
                elif model_type == 'lightgbm':
                    result = await self._optimize_lightgbm(
                        X_train, y_train, X_val, y_val, n_trials_per_model, metric
                    )
                elif model_type == 'neural_network':
                    result = await self._optimize_neural_network(
                        X_train, y_train, X_val, y_val, n_trials_per_model, metric
                    )
                
                results[model_type] = result
                
            except Exception as e:
                logger.error(
                    f"{model_type}_optimization_failed",
                    error=str(e)
                )
                results[model_type] = {
                    'score': -999.0,
                    'error': str(e)
                }
        
        # Select best model
        best_model = max(
            results.items(),
            key=lambda x: x[1].get('score', -999.0)
        )
        
        best_model_type = best_model[0]
        best_result = best_model[1]
        
        logger.info(
            "model_selection_completed",
            best_model=best_model_type,
            best_score=best_result.get('score'),
            all_scores={k: v.get('score') for k, v in results.items()}
        )
        
        return {
            'best_model_type': best_model_type,
            'best_hyperparameters': best_result.get('hyperparameters', {}),
            'best_score': best_result.get('score'),
            'metric': metric,
            'all_results': results,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    async def _optimize_xgboost(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        n_trials: int,
        metric: str
    ) -> Dict[str, Any]:
        """Optimize XGBoost model"""
        import optuna
        
        def objective(trial):
            params = {
                'objective': 'multi:softmax',
                'num_class': 3,
                'n_estimators': trial.suggest_int('n_estimators', 50, 500),
                'max_depth': trial.suggest_int('max_depth', 3, 12),
                'learning_rate': trial.suggest_float('learning_rate', 0.001, 0.3, log=True),
                'subsample': trial.suggest_float('subsample', 0.5, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
                'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
                'gamma': trial.suggest_float('gamma', 0.0, 5.0),
                'reg_alpha': trial.suggest_float('reg_alpha', 0.0, 2.0),
                'reg_lambda': trial.suggest_float('reg_lambda', 0.0, 2.0),
                'random_state': self.random_state,
                'verbosity': 0
            }
            
            model = xgb.XGBClassifier(**params)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False
            )
            
            y_pred = model.predict(X_val)
            score = self._calculate_metric(y_val, y_pred, metric)
            
            return score
        
        study = optuna.create_study(
            direction='maximize',
            sampler=optuna.samplers.TPESampler(seed=self.random_state)
        )
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        
        # Train final model with best params
        best_params = study.best_params
        best_params.update({
            'objective': 'multi:softmax',
            'num_class': 3,
            'random_state': self.random_state,
            'verbosity': 0
        })
        
        final_model = xgb.XGBClassifier(**best_params)
        final_model.fit(X_train, y_train)
        
        y_pred = final_model.predict(X_val)
        final_score = self._calculate_metric(y_val, y_pred, metric)
        
        return {
            'hyperparameters': best_params,
            'score': final_score,
            'n_trials': n_trials,
            'model': final_model
        }
    
    async def _optimize_lightgbm(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        n_trials: int,
        metric: str
    ) -> Dict[str, Any]:
        """Optimize LightGBM model"""
        import optuna
        
        def objective(trial):
            params = {
                'objective': 'multiclass',
                'num_class': 3,
                'metric': 'multi_logloss',
                'n_estimators': trial.suggest_int('n_estimators', 50, 500),
                'max_depth': trial.suggest_int('max_depth', 3, 12),
                'learning_rate': trial.suggest_float('learning_rate', 0.001, 0.3, log=True),
                'num_leaves': trial.suggest_int('num_leaves', 20, 150),
                'subsample': trial.suggest_float('subsample', 0.5, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
                'min_child_samples': trial.suggest_int('min_child_samples', 5, 100),
                'reg_alpha': trial.suggest_float('reg_alpha', 0.0, 2.0),
                'reg_lambda': trial.suggest_float('reg_lambda', 0.0, 2.0),
                'random_state': self.random_state,
                'verbosity': -1
            }
            
            model = lgb.LGBMClassifier(**params)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)]
            )
            
            y_pred = model.predict(X_val)
            score = self._calculate_metric(y_val, y_pred, metric)
            
            return score
        
        study = optuna.create_study(
            direction='maximize',
            sampler=optuna.samplers.TPESampler(seed=self.random_state)
        )
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        
        # Train final model
        best_params = study.best_params
        best_params.update({
            'objective': 'multiclass',
            'num_class': 3,
            'metric': 'multi_logloss',
            'random_state': self.random_state,
            'verbosity': -1
        })
        
        final_model = lgb.LGBMClassifier(**best_params)
        final_model.fit(X_train, y_train)
        
        y_pred = final_model.predict(X_val)
        final_score = self._calculate_metric(y_val, y_pred, metric)
        
        return {
            'hyperparameters': best_params,
            'score': final_score,
            'n_trials': n_trials,
            'model': final_model
        }
    
    async def _optimize_neural_network(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        n_trials: int,
        metric: str
    ) -> Dict[str, Any]:
        """Optimize Neural Network model"""
        import optuna
        
        # Standardize features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)
        
        def objective(trial):
            # Architecture hyperparameters
            n_layers = trial.suggest_int('n_layers', 1, 4)
            hidden_sizes = [
                trial.suggest_int(f'hidden_size_{i}', 32, 512)
                for i in range(n_layers)
            ]
            dropout = trial.suggest_float('dropout', 0.1, 0.5)
            learning_rate = trial.suggest_float('learning_rate', 0.0001, 0.01, log=True)
            batch_size = trial.suggest_categorical('batch_size', [32, 64, 128, 256])
            
            # Create model
            input_size = X_train.shape[1]
            model = TradingNeuralNetwork(
                input_size=input_size,
                hidden_sizes=hidden_sizes,
                output_size=3,
                dropout=dropout
            )
            
            # Training setup
            criterion = nn.CrossEntropyLoss()
            optimizer = optim.Adam(model.parameters(), lr=learning_rate)
            
            # Convert to tensors
            X_train_tensor = torch.FloatTensor(X_train_scaled)
            y_train_tensor = torch.LongTensor(y_train)
            X_val_tensor = torch.FloatTensor(X_val_scaled)
            
            # Training loop
            n_epochs = 50
            for epoch in range(n_epochs):
                model.train()
                
                # Mini-batch training
                for i in range(0, len(X_train_tensor), batch_size):
                    batch_X = X_train_tensor[i:i+batch_size]
                    batch_y = y_train_tensor[i:i+batch_size]
                    
                    optimizer.zero_grad()
                    outputs = model(batch_X)
                    loss = criterion(outputs, batch_y)
                    loss.backward()
                    optimizer.step()
            
            # Evaluate
            model.eval()
            with torch.no_grad():
                outputs = model(X_val_tensor)
                y_pred = outputs.argmax(dim=1).numpy()
            
            score = self._calculate_metric(y_val, y_pred, metric)
            return score
        
        study = optuna.create_study(
            direction='maximize',
            sampler=optuna.samplers.TPESampler(seed=self.random_state)
        )
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        
        # Train final model with best params
        best_params = study.best_params
        n_layers = best_params['n_layers']
        hidden_sizes = [best_params[f'hidden_size_{i}'] for i in range(n_layers)]
        
        final_model = TradingNeuralNetwork(
            input_size=X_train.shape[1],
            hidden_sizes=hidden_sizes,
            output_size=3,
            dropout=best_params['dropout']
        )
        
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(final_model.parameters(), lr=best_params['learning_rate'])
        
        X_train_tensor = torch.FloatTensor(X_train_scaled)
        y_train_tensor = torch.LongTensor(y_train)
        X_val_tensor = torch.FloatTensor(X_val_scaled)
        
        # Train final model
        for epoch in range(100):
            final_model.train()
            for i in range(0, len(X_train_tensor), best_params['batch_size']):
                batch_X = X_train_tensor[i:i+best_params['batch_size']]
                batch_y = y_train_tensor[i:i+best_params['batch_size']]
                
                optimizer.zero_grad()
                outputs = final_model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
        
        # Final evaluation
        final_model.eval()
        with torch.no_grad():
            outputs = final_model(X_val_tensor)
            y_pred = outputs.argmax(dim=1).numpy()
        
        final_score = self._calculate_metric(y_val, y_pred, metric)
        
        return {
            'hyperparameters': best_params,
            'score': final_score,
            'n_trials': n_trials,
            'model': final_model,
            'scaler': scaler
        }
    
    def _calculate_metric(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        metric: str
    ) -> float:
        """Calculate specified metric"""
        if metric == 'accuracy':
            return accuracy_score(y_true, y_pred)
        elif metric == 'f1_weighted':
            return f1_score(y_true, y_pred, average='weighted')
        elif metric == 'precision':
            return precision_score(y_true, y_pred, average='weighted', zero_division=0)
        elif metric == 'recall':
            return recall_score(y_true, y_pred, average='weighted', zero_division=0)
        else:
            raise ValueError(f"Unknown metric: {metric}")
    
    def save_model(
        self,
        model: Any,
        model_type: str,
        hyperparameters: Dict[str, Any],
        filepath: str
    ) -> None:
        """
        Save trained model to disk
        
        Args:
            model: Trained model object
            model_type: Type of model ('xgboost', 'lightgbm', 'neural_network')
            hyperparameters: Model hyperparameters
            filepath: Path to save model
        """
        metadata = {
            'model_type': model_type,
            'hyperparameters': hyperparameters,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if model_type == 'xgboost':
            model.save_model(filepath)
            with open(f"{filepath}.meta", 'w') as f:
                json.dump(metadata, f, indent=2)
                
        elif model_type == 'lightgbm':
            model.booster_.save_model(filepath)
            with open(f"{filepath}.meta", 'w') as f:
                json.dump(metadata, f, indent=2)
                
        elif model_type == 'neural_network':
            torch.save({
                'model_state_dict': model.state_dict(),
                'metadata': metadata
            }, filepath)
        
        logger.info(
            "model_saved",
            model_type=model_type,
            filepath=filepath
        )
