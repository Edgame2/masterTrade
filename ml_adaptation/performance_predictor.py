"""
Performance Predictor

Predicts future strategy performance using ML:
- Time series forecasting
- Classification (will strategy be profitable?)
- Feature importance analysis
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np
import logging

logger = logging.getLogger(__name__)


class PredictionModel(Enum):
    """Types of prediction models"""
    LINEAR_REGRESSION = "linear_regression"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    LSTM = "lstm"
    TRANSFORMER = "transformer"


@dataclass
class PerformancePrediction:
    """Prediction result"""
    strategy_id: str
    predicted_return: float
    confidence: float  # 0-1
    prediction_horizon: int  # trades ahead
    
    # Classification
    will_be_profitable: bool
    profit_probability: float
    
    # Feature importance
    important_features: Dict[str, float] = field(default_factory=dict)
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "predicted_return": self.predicted_return,
            "confidence": self.confidence,
            "prediction_horizon": self.prediction_horizon,
            "will_be_profitable": self.will_be_profitable,
            "profit_probability": self.profit_probability,
            "important_features": self.important_features,
            "timestamp": self.timestamp.isoformat(),
        }


class TimeSeriesPredictor:
    """
    Time series forecasting for strategy returns.
    
    Uses historical returns and features to predict future performance.
    """
    
    def __init__(
        self,
        model_type: PredictionModel = PredictionModel.LINEAR_REGRESSION,
        lookback_window: int = 50,
        prediction_horizon: int = 10,
    ):
        self.model_type = model_type
        self.lookback_window = lookback_window
        self.prediction_horizon = prediction_horizon
        
        self.model = None
        self.is_fitted = False
        
        logger.info(f"TimeSeriesPredictor initialized with {model_type.value}")
    
    def fit(
        self,
        historical_returns: np.ndarray,
        historical_features: Optional[np.ndarray] = None,
    ):
        """
        Fit prediction model.
        
        Args:
            historical_returns: Array of historical returns
            historical_features: Optional features (regime, volatility, etc.)
        """
        if len(historical_returns) < self.lookback_window + self.prediction_horizon:
            logger.warning("Insufficient data for training")
            return
        
        # Create training data
        X, y = self._create_sequences(historical_returns, historical_features)
        
        try:
            if self.model_type == PredictionModel.LINEAR_REGRESSION:
                from sklearn.linear_model import LinearRegression
                self.model = LinearRegression()
                self.model.fit(X, y)
            
            elif self.model_type == PredictionModel.RANDOM_FOREST:
                from sklearn.ensemble import RandomForestRegressor
                self.model = RandomForestRegressor(n_estimators=100, random_state=42)
                self.model.fit(X, y)
            
            elif self.model_type == PredictionModel.GRADIENT_BOOSTING:
                from sklearn.ensemble import GradientBoostingRegressor
                self.model = GradientBoostingRegressor(n_estimators=100, random_state=42)
                self.model.fit(X, y)
            
            else:
                logger.warning(f"Model type {self.model_type.value} not implemented, using linear regression")
                from sklearn.linear_model import LinearRegression
                self.model = LinearRegression()
                self.model.fit(X, y)
            
            self.is_fitted = True
            logger.info(f"Model fitted with {len(X)} samples")
            
        except ImportError:
            logger.error("scikit-learn not installed. Install with: pip install scikit-learn")
        except Exception as e:
            logger.error(f"Error fitting model: {e}")
    
    def _create_sequences(
        self,
        returns: np.ndarray,
        features: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Create input sequences and targets"""
        X, y = [], []
        
        for i in range(len(returns) - self.lookback_window - self.prediction_horizon):
            # Input: lookback window of returns
            x_window = returns[i:i + self.lookback_window]
            
            # Add features if available
            if features is not None:
                feature_window = features[i:i + self.lookback_window]
                x_window = np.concatenate([x_window, feature_window.flatten()])
            
            # Target: average return over prediction horizon
            y_window = returns[i + self.lookback_window:i + self.lookback_window + self.prediction_horizon]
            y_value = np.mean(y_window)
            
            X.append(x_window)
            y.append(y_value)
        
        return np.array(X), np.array(y)
    
    def predict(
        self,
        recent_returns: np.ndarray,
        recent_features: Optional[np.ndarray] = None,
    ) -> float:
        """
        Predict future return.
        
        Args:
            recent_returns: Recent returns (length = lookback_window)
            recent_features: Optional recent features
            
        Returns:
            Predicted return
        """
        if not self.is_fitted:
            logger.warning("Model not fitted, returning 0")
            return 0.0
        
        # Prepare input
        x = recent_returns[-self.lookback_window:]
        
        if recent_features is not None:
            feature_window = recent_features[-self.lookback_window:]
            x = np.concatenate([x, feature_window.flatten()])
        
        x = x.reshape(1, -1)
        
        # Predict
        prediction = self.model.predict(x)[0]
        
        return prediction
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance (for tree-based models)"""
        if not self.is_fitted:
            return {}
        
        try:
            if hasattr(self.model, 'feature_importances_'):
                importances = self.model.feature_importances_
                feature_names = [f"lag_{i}" for i in range(len(importances))]
                return dict(zip(feature_names, importances))
        except Exception as e:
            logger.error(f"Error getting feature importance: {e}")
        
        return {}


class ClassificationPredictor:
    """
    Classifies whether strategy will be profitable.
    
    Binary classification: profitable vs unprofitable
    """
    
    def __init__(
        self,
        model_type: PredictionModel = PredictionModel.RANDOM_FOREST,
        lookback_window: int = 20,
        profit_threshold: float = 0.0,
    ):
        self.model_type = model_type
        self.lookback_window = lookback_window
        self.profit_threshold = profit_threshold
        
        self.model = None
        self.is_fitted = False
        
        logger.info(f"ClassificationPredictor initialized")
    
    def fit(
        self,
        historical_returns: np.ndarray,
        historical_features: Optional[np.ndarray] = None,
    ):
        """Fit classification model"""
        if len(historical_returns) < self.lookback_window + 1:
            logger.warning("Insufficient data for training")
            return
        
        # Create training data
        X, y = self._create_classification_data(historical_returns, historical_features)
        
        try:
            if self.model_type == PredictionModel.RANDOM_FOREST:
                from sklearn.ensemble import RandomForestClassifier
                self.model = RandomForestClassifier(n_estimators=100, random_state=42)
                self.model.fit(X, y)
            
            elif self.model_type == PredictionModel.GRADIENT_BOOSTING:
                from sklearn.ensemble import GradientBoostingClassifier
                self.model = GradientBoostingClassifier(n_estimators=100, random_state=42)
                self.model.fit(X, y)
            
            else:
                from sklearn.ensemble import RandomForestClassifier
                self.model = RandomForestClassifier(n_estimators=100, random_state=42)
                self.model.fit(X, y)
            
            self.is_fitted = True
            logger.info(f"Classification model fitted with {len(X)} samples")
            
        except ImportError:
            logger.error("scikit-learn not installed")
        except Exception as e:
            logger.error(f"Error fitting classification model: {e}")
    
    def _create_classification_data(
        self,
        returns: np.ndarray,
        features: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Create classification training data"""
        X, y = [], []
        
        for i in range(len(returns) - self.lookback_window - 1):
            # Input: lookback window
            x_window = returns[i:i + self.lookback_window]
            
            if features is not None:
                feature_window = features[i:i + self.lookback_window]
                x_window = np.concatenate([x_window, feature_window.flatten()])
            
            # Target: is next return profitable?
            next_return = returns[i + self.lookback_window]
            is_profitable = 1 if next_return > self.profit_threshold else 0
            
            X.append(x_window)
            y.append(is_profitable)
        
        return np.array(X), np.array(y)
    
    def predict(
        self,
        recent_returns: np.ndarray,
        recent_features: Optional[np.ndarray] = None,
    ) -> Tuple[bool, float]:
        """
        Predict profitability.
        
        Returns:
            (is_profitable, probability)
        """
        if not self.is_fitted:
            return False, 0.5
        
        # Prepare input
        x = recent_returns[-self.lookback_window:]
        
        if recent_features is not None:
            feature_window = recent_features[-self.lookback_window:]
            x = np.concatenate([x, feature_window.flatten()])
        
        x = x.reshape(1, -1)
        
        # Predict
        prediction = self.model.predict(x)[0]
        probability = self.model.predict_proba(x)[0][1]  # Probability of profitable
        
        is_profitable = prediction == 1
        
        return is_profitable, probability


class PerformancePredictor:
    """
    Main performance prediction system.
    
    Combines time series forecasting and classification to predict strategy performance.
    """
    
    def __init__(
        self,
        lookback_window: int = 50,
        prediction_horizon: int = 10,
    ):
        self.lookback_window = lookback_window
        self.prediction_horizon = prediction_horizon
        
        # Predictors
        self.ts_predictor = TimeSeriesPredictor(
            model_type=PredictionModel.RANDOM_FOREST,
            lookback_window=lookback_window,
            prediction_horizon=prediction_horizon,
        )
        
        self.class_predictor = ClassificationPredictor(
            lookback_window=lookback_window,
        )
        
        # Performance history
        self.strategy_histories: Dict[str, List[float]] = {}
        
        logger.info("PerformancePredictor initialized")
    
    def train(self, strategy_id: str, historical_returns: np.ndarray):
        """Train predictors for a strategy"""
        if len(historical_returns) < self.lookback_window + self.prediction_horizon:
            logger.warning(f"Insufficient data for {strategy_id}")
            return
        
        # Train both predictors
        self.ts_predictor.fit(historical_returns)
        self.class_predictor.fit(historical_returns)
        
        # Store history
        self.strategy_histories[strategy_id] = historical_returns.tolist()
        
        logger.info(f"Trained predictors for {strategy_id}")
    
    def predict(self, strategy_id: str, recent_returns: Optional[np.ndarray] = None) -> PerformancePrediction:
        """
        Predict strategy performance.
        
        Args:
            strategy_id: Strategy to predict
            recent_returns: Optional recent returns (uses history if not provided)
            
        Returns:
            PerformancePrediction
        """
        # Get recent returns
        if recent_returns is None:
            if strategy_id not in self.strategy_histories:
                logger.warning(f"No history for {strategy_id}")
                return self._default_prediction(strategy_id)
            
            recent_returns = np.array(self.strategy_histories[strategy_id][-self.lookback_window:])
        
        # Time series prediction
        predicted_return = self.ts_predictor.predict(recent_returns)
        
        # Classification prediction
        will_be_profitable, profit_probability = self.class_predictor.predict(recent_returns)
        
        # Estimate confidence based on historical accuracy
        confidence = 0.7  # Simplified - would track actual prediction accuracy
        
        # Get feature importance
        important_features = self.ts_predictor.get_feature_importance()
        
        prediction = PerformancePrediction(
            strategy_id=strategy_id,
            predicted_return=predicted_return,
            confidence=confidence,
            prediction_horizon=self.prediction_horizon,
            will_be_profitable=will_be_profitable,
            profit_probability=profit_probability,
            important_features=important_features,
        )
        
        logger.debug(f"Predicted for {strategy_id}: return={predicted_return:.4f}, profitable={will_be_profitable}")
        
        return prediction
    
    def _default_prediction(self, strategy_id: str) -> PerformancePrediction:
        """Return default prediction when no data available"""
        return PerformancePrediction(
            strategy_id=strategy_id,
            predicted_return=0.0,
            confidence=0.0,
            prediction_horizon=self.prediction_horizon,
            will_be_profitable=False,
            profit_probability=0.5,
        )
    
    def update_history(self, strategy_id: str, new_return: float):
        """Update strategy history with new return"""
        if strategy_id not in self.strategy_histories:
            self.strategy_histories[strategy_id] = []
        
        self.strategy_histories[strategy_id].append(new_return)
        
        # Keep limited history
        max_history = 1000
        if len(self.strategy_histories[strategy_id]) > max_history:
            self.strategy_histories[strategy_id] = self.strategy_histories[strategy_id][-max_history:]
    
    def get_prediction_accuracy(self, strategy_id: str) -> Dict[str, float]:
        """Calculate prediction accuracy (would track predictions vs actuals)"""
        # Simplified - in production would track actual prediction accuracy
        return {
            "mae": 0.0,  # Mean Absolute Error
            "rmse": 0.0,  # Root Mean Squared Error
            "accuracy": 0.0,  # Classification accuracy
        }
