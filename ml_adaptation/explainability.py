"""
Model Explainability using SHAP

This module implements model explainability for trading decisions using SHAP
(SHapley Additive exPlanations) values to understand which features drove
each trading signal.

Features:
- SHAP value computation for individual predictions
- Feature importance tracking
- Decision explanation storage in database
- Visualization support for monitoring UI
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
import numpy as np
import structlog

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

logger = structlog.get_logger()


class ModelExplainer:
    """
    Model explainability using SHAP values
    
    Generates explanations for trading decisions to understand which features
    drove the model's predictions.
    """
    
    def __init__(
        self,
        model: Any,
        model_type: str,
        feature_names: List[str],
        database_manager=None
    ):
        """
        Initialize explainer
        
        Args:
            model: Trained model (XGBoost, LightGBM, or Neural Network)
            model_type: Type of model ('xgboost', 'lightgbm', 'neural_network')
            feature_names: List of feature names
            database_manager: Database manager for storing explanations
        """
        if not SHAP_AVAILABLE:
            raise ImportError(
                "SHAP is required for model explainability. "
                "Install it via: pip install shap"
            )
        
        self.model = model
        self.model_type = model_type
        self.feature_names = feature_names
        self.database_manager = database_manager
        
        # Initialize appropriate explainer
        self.explainer = None
        self._initialize_explainer()
        
        logger.info(
            "explainer_initialized",
            model_type=model_type,
            n_features=len(feature_names)
        )
    
    def _initialize_explainer(self):
        """Initialize SHAP explainer based on model type"""
        if self.model_type in ['xgboost', 'lightgbm']:
            # Tree-based explainer for gradient boosting models
            self.explainer = shap.TreeExplainer(self.model)
            
        elif self.model_type == 'neural_network':
            # Deep explainer for neural networks
            # Note: Requires background data for proper initialization
            logger.warning(
                "neural_network_explainer_requires_background_data",
                message="Deep SHAP requires background data. "
                        "Call initialize_deep_explainer() with background dataset."
            )
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")
    
    def initialize_deep_explainer(self, background_data: np.ndarray):
        """
        Initialize Deep SHAP explainer with background data
        
        Args:
            background_data: Representative sample of training data (e.g., 100 samples)
        """
        if self.model_type != 'neural_network':
            logger.warning(
                "deep_explainer_not_needed",
                model_type=self.model_type
            )
            return
        
        import torch
        background_tensor = torch.FloatTensor(background_data)
        self.explainer = shap.DeepExplainer(self.model, background_tensor)
        
        logger.info(
            "deep_explainer_initialized",
            background_size=len(background_data)
        )
    
    async def explain_prediction(
        self,
        features: Union[np.ndarray, Dict[str, float]],
        prediction: int,
        prediction_proba: Optional[np.ndarray] = None,
        trade_id: Optional[str] = None,
        symbol: Optional[str] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Explain a single prediction using SHAP values
        
        Args:
            features: Feature vector or dict
            prediction: Predicted class (0=SELL, 1=HOLD, 2=BUY)
            prediction_proba: Prediction probabilities [P(SELL), P(HOLD), P(BUY)]
            trade_id: Optional trade ID for tracking
            symbol: Trading symbol
            top_k: Number of top features to return
            
        Returns:
            Dict with SHAP values and feature importances
        """
        # Convert dict to array if needed
        if isinstance(features, dict):
            features_array = np.array([
                features.get(name, 0.0) for name in self.feature_names
            ])
        else:
            features_array = features
        
        # Reshape for single prediction
        features_array = features_array.reshape(1, -1)
        
        # Compute SHAP values
        if self.model_type in ['xgboost', 'lightgbm']:
            shap_values = self.explainer.shap_values(features_array)
            
            # For multi-class, shap_values is a list [class0, class1, class2]
            if isinstance(shap_values, list):
                # Get SHAP values for predicted class
                class_shap_values = shap_values[prediction][0]
            else:
                class_shap_values = shap_values[0]
                
        elif self.model_type == 'neural_network':
            if self.explainer is None:
                raise RuntimeError(
                    "Deep explainer not initialized. "
                    "Call initialize_deep_explainer() first."
                )
            import torch
            features_tensor = torch.FloatTensor(features_array)
            shap_values = self.explainer.shap_values(features_tensor)
            class_shap_values = shap_values[prediction][0]
        
        # Create feature importance ranking
        feature_importances = []
        for i, (name, value, shap_val) in enumerate(
            zip(self.feature_names, features_array[0], class_shap_values)
        ):
            feature_importances.append({
                'feature_name': name,
                'feature_value': float(value),
                'shap_value': float(shap_val),
                'abs_shap_value': float(abs(shap_val)),
                'rank': 0  # Will be set after sorting
            })
        
        # Sort by absolute SHAP value (importance)
        feature_importances.sort(key=lambda x: x['abs_shap_value'], reverse=True)
        
        # Add ranks
        for rank, feature in enumerate(feature_importances, 1):
            feature['rank'] = rank
        
        # Get top K features
        top_features = feature_importances[:top_k]
        
        # Create explanation
        explanation = {
            'trade_id': trade_id,
            'symbol': symbol,
            'prediction': prediction,
            'prediction_label': ['SELL', 'HOLD', 'BUY'][prediction],
            'prediction_proba': prediction_proba.tolist() if prediction_proba is not None else None,
            'top_features': top_features,
            'all_features': feature_importances,
            'base_value': float(self.explainer.expected_value[prediction]) if isinstance(self.explainer.expected_value, (list, np.ndarray)) else float(self.explainer.expected_value),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Store in database if available
        if self.database_manager and trade_id:
            await self._store_explanation(explanation)
        
        logger.info(
            "prediction_explained",
            trade_id=trade_id,
            prediction=explanation['prediction_label'],
            top_feature=top_features[0]['feature_name'] if top_features else None,
            top_shap_value=top_features[0]['shap_value'] if top_features else None
        )
        
        return explanation
    
    async def explain_batch(
        self,
        features: np.ndarray,
        predictions: np.ndarray,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Explain multiple predictions in batch
        
        Args:
            features: Feature matrix (n_samples, n_features)
            predictions: Predicted classes
            top_k: Number of top features per prediction
            
        Returns:
            List of explanation dicts
        """
        logger.info(
            "batch_explanation_started",
            n_samples=len(features)
        )
        
        explanations = []
        
        for i, (feature_vec, pred) in enumerate(zip(features, predictions)):
            explanation = await self.explain_prediction(
                features=feature_vec,
                prediction=pred,
                top_k=top_k
            )
            explanations.append(explanation)
        
        return explanations
    
    def get_global_feature_importance(
        self,
        X: np.ndarray,
        max_samples: int = 1000
    ) -> Dict[str, Any]:
        """
        Compute global feature importance across dataset
        
        Args:
            X: Feature matrix
            max_samples: Maximum samples to use (for performance)
            
        Returns:
            Dict with global feature importances
        """
        # Subsample if needed
        if len(X) > max_samples:
            indices = np.random.choice(len(X), max_samples, replace=False)
            X_sample = X[indices]
        else:
            X_sample = X
        
        # Compute SHAP values
        if self.model_type in ['xgboost', 'lightgbm']:
            shap_values = self.explainer.shap_values(X_sample)
            
            # For multi-class, average across classes
            if isinstance(shap_values, list):
                shap_values_avg = np.mean([np.abs(sv) for sv in shap_values], axis=0)
            else:
                shap_values_avg = np.abs(shap_values)
        else:
            # Neural network
            import torch
            X_tensor = torch.FloatTensor(X_sample)
            shap_values = self.explainer.shap_values(X_tensor)
            shap_values_avg = np.mean([np.abs(sv) for sv in shap_values], axis=0)
        
        # Compute mean absolute SHAP value per feature
        mean_shap = np.mean(shap_values_avg, axis=0)
        
        # Create ranking
        feature_importance = []
        for name, importance in zip(self.feature_names, mean_shap):
            feature_importance.append({
                'feature_name': name,
                'importance': float(importance),
                'rank': 0
            })
        
        # Sort and rank
        feature_importance.sort(key=lambda x: x['importance'], reverse=True)
        for rank, feature in enumerate(feature_importance, 1):
            feature['rank'] = rank
        
        logger.info(
            "global_importance_computed",
            n_samples=len(X_sample),
            top_feature=feature_importance[0]['feature_name']
        )
        
        return {
            'feature_importances': feature_importance,
            'n_samples': len(X_sample),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def create_summary_plot(
        self,
        X: np.ndarray,
        output_path: str,
        max_samples: int = 1000,
        plot_type: str = 'bar'
    ) -> str:
        """
        Create SHAP summary plot
        
        Args:
            X: Feature matrix
            output_path: Path to save plot
            max_samples: Maximum samples to plot
            plot_type: 'bar' or 'dot'
            
        Returns:
            Path to saved plot
        """
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("matplotlib required for plotting")
        
        # Subsample
        if len(X) > max_samples:
            indices = np.random.choice(len(X), max_samples, replace=False)
            X_sample = X[indices]
        else:
            X_sample = X
        
        # Compute SHAP values
        if self.model_type in ['xgboost', 'lightgbm']:
            shap_values = self.explainer.shap_values(X_sample)
        else:
            import torch
            X_tensor = torch.FloatTensor(X_sample)
            shap_values = self.explainer.shap_values(X_tensor)
        
        # Create plot
        plt.figure(figsize=(10, 8))
        
        if plot_type == 'bar':
            shap.summary_plot(
                shap_values,
                X_sample,
                feature_names=self.feature_names,
                plot_type='bar',
                show=False
            )
        else:
            shap.summary_plot(
                shap_values,
                X_sample,
                feature_names=self.feature_names,
                show=False
            )
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info("summary_plot_created", output_path=output_path)
        
        return output_path
    
    async def _store_explanation(self, explanation: Dict[str, Any]):
        """Store explanation in database"""
        if not self.database_manager:
            return
        
        try:
            query = """
                INSERT INTO model_explanations (
                    trade_id, symbol, prediction, prediction_label,
                    prediction_proba, top_features, base_value, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """
            
            await self.database_manager.execute(
                query,
                explanation.get('trade_id'),
                explanation.get('symbol'),
                explanation['prediction'],
                explanation['prediction_label'],
                json.dumps(explanation.get('prediction_proba')),
                json.dumps(explanation['top_features']),
                explanation['base_value'],
                datetime.now(timezone.utc)
            )
            
            logger.debug(
                "explanation_stored",
                trade_id=explanation.get('trade_id')
            )
            
        except Exception as e:
            logger.error(
                "failed_to_store_explanation",
                error=str(e),
                trade_id=explanation.get('trade_id')
            )


async def create_explanation_table(database_manager):
    """
    Create database table for storing explanations
    
    Args:
        database_manager: Database manager instance
    """
    create_table_query = """
        CREATE TABLE IF NOT EXISTS model_explanations (
            id BIGSERIAL PRIMARY KEY,
            trade_id VARCHAR(100),
            symbol VARCHAR(20),
            prediction INTEGER,
            prediction_label VARCHAR(10),
            prediction_proba JSONB,
            top_features JSONB,
            base_value NUMERIC(20, 8),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_explanations_trade_id
            ON model_explanations(trade_id);
        
        CREATE INDEX IF NOT EXISTS idx_explanations_symbol
            ON model_explanations(symbol);
        
        CREATE INDEX IF NOT EXISTS idx_explanations_created_at
            ON model_explanations(created_at DESC);
    """
    
    try:
        await database_manager.execute(create_table_query)
        logger.info("model_explanations_table_created")
    except Exception as e:
        logger.error("failed_to_create_explanations_table", error=str(e))


async def get_explanation_by_trade_id(
    database_manager,
    trade_id: str
) -> Optional[Dict[str, Any]]:
    """
    Retrieve explanation for a specific trade
    
    Args:
        database_manager: Database manager
        trade_id: Trade identifier
        
    Returns:
        Explanation dict or None
    """
    query = """
        SELECT 
            trade_id, symbol, prediction, prediction_label,
            prediction_proba, top_features, base_value, created_at
        FROM model_explanations
        WHERE trade_id = $1
        ORDER BY created_at DESC
        LIMIT 1
    """
    
    try:
        row = await database_manager.fetchrow(query, trade_id)
        
        if row:
            return {
                'trade_id': row['trade_id'],
                'symbol': row['symbol'],
                'prediction': row['prediction'],
                'prediction_label': row['prediction_label'],
                'prediction_proba': json.loads(row['prediction_proba']) if row['prediction_proba'] else None,
                'top_features': json.loads(row['top_features']),
                'base_value': float(row['base_value']),
                'timestamp': row['created_at'].isoformat()
            }
        
        return None
        
    except Exception as e:
        logger.error(
            "failed_to_retrieve_explanation",
            error=str(e),
            trade_id=trade_id
        )
        return None
