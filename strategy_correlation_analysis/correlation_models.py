"""
Advanced Correlation Models

Sophisticated correlation modeling and forecasting including:
- Dynamic Conditional Correlation (DCC) models
- GARCH-DCC framework
- Exponentially Weighted Moving Average (EWMA) correlation
- Shrinkage correlation estimators
- Correlation forecasting with prediction intervals
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import warnings

# Suppress warnings for cleaner output
with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    from sklearn.covariance import LedoitWolf, ShrunkCovariance
    from arch import arch_model
    from arch.univariate import GARCH, ConstantMean
    from scipy import linalg
    from scipy.optimize import minimize
    import scipy.stats as stats

logger = logging.getLogger(__name__)


class CorrelationModelType(Enum):
    """Types of correlation models"""
    STATIC_PEARSON = "static_pearson"
    EWMA = "ewma"
    GARCH_DCC = "garch_dcc"
    SHRINKAGE = "shrinkage"
    DYNAMIC_CONDITIONAL = "dynamic_conditional"
    ROLLING_WINDOW = "rolling_window"


class ForecastHorizon(Enum):
    """Forecast horizons for correlation prediction"""
    ONE_DAY = 1
    ONE_WEEK = 7
    TWO_WEEKS = 14
    ONE_MONTH = 30
    THREE_MONTHS = 90


@dataclass
class CorrelationForecast:
    """Correlation forecast with confidence intervals"""
    strategy_pair: Tuple[str, str]
    forecast_date: datetime
    horizon_days: int
    forecasted_correlation: float
    confidence_interval: Tuple[float, float]
    prediction_variance: float
    model_type: CorrelationModelType
    model_confidence: float
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "strategy_pair": self.strategy_pair,
            "forecast_date": self.forecast_date.isoformat(),
            "horizon_days": self.horizon_days,
            "forecasted_correlation": self.forecasted_correlation,
            "confidence_interval": self.confidence_interval,
            "prediction_variance": self.prediction_variance,
            "model_type": self.model_type.value,
            "model_confidence": self.model_confidence
        }


class CorrelationModel(ABC):
    """
    Abstract base class for correlation models
    """
    
    def __init__(self, model_type: CorrelationModelType):
        self.model_type = model_type
        self.is_fitted = False
        self.parameters = {}
        self.fit_statistics = {}
    
    @abstractmethod
    def fit(self, returns_data: pd.DataFrame) -> 'CorrelationModel':
        """Fit the correlation model to returns data"""
        pass
    
    @abstractmethod
    def predict_correlation(
        self,
        strategy1: str,
        strategy2: str,
        horizon: int = 1
    ) -> CorrelationForecast:
        """Predict correlation for a strategy pair"""
        pass
    
    @abstractmethod
    def get_correlation_matrix(self, date: Optional[datetime] = None) -> pd.DataFrame:
        """Get correlation matrix at specified date"""
        pass
    
    def get_model_info(self) -> Dict:
        """Get model information and statistics"""
        return {
            "model_type": self.model_type.value,
            "is_fitted": self.is_fitted,
            "parameters": self.parameters,
            "fit_statistics": self.fit_statistics
        }


class EWMACorrelationModel(CorrelationModel):
    """
    Exponentially Weighted Moving Average Correlation Model
    
    Uses exponentially weighted covariance estimation for dynamic correlations.
    """
    
    def __init__(self, decay_factor: float = 0.94):
        super().__init__(CorrelationModelType.EWMA)
        self.decay_factor = decay_factor
        self.returns_data = None
        self.ewma_covariance = None
        self.ewma_correlation = None
    
    def fit(self, returns_data: pd.DataFrame) -> 'EWMACorrelationModel':
        """Fit EWMA correlation model"""
        self.returns_data = returns_data.dropna()
        
        if len(self.returns_data) < 10:
            raise ValueError("Insufficient data for EWMA correlation model")
        
        # Calculate exponentially weighted covariance
        self.ewma_covariance = self.returns_data.ewm(
            alpha=1-self.decay_factor,
            min_periods=5
        ).cov().iloc[-len(self.returns_data.columns):, :]
        
        # Convert covariance to correlation
        variances = np.diag(self.ewma_covariance)
        std_devs = np.sqrt(variances)
        
        self.ewma_correlation = self.ewma_covariance.copy()
        for i in range(len(std_devs)):
            for j in range(len(std_devs)):
                if std_devs[i] > 0 and std_devs[j] > 0:
                    self.ewma_correlation.iloc[i, j] = (
                        self.ewma_covariance.iloc[i, j] / (std_devs[i] * std_devs[j])
                    )
        
        # Store model parameters
        self.parameters = {
            "decay_factor": self.decay_factor,
            "effective_window": int(1 / (1 - self.decay_factor))
        }
        
        # Calculate fit statistics
        self._calculate_fit_statistics()
        
        self.is_fitted = True
        return self
    
    def _calculate_fit_statistics(self):
        """Calculate model fit statistics"""
        if self.returns_data is None or len(self.returns_data) < 20:
            return
        
        # Calculate rolling correlations for comparison
        window = 20
        rolling_correlations = {}
        
        strategies = list(self.returns_data.columns)
        for i, strategy1 in enumerate(strategies):
            for j, strategy2 in enumerate(strategies[i+1:], i+1):
                rolling_corr = self.returns_data[strategy1].rolling(window).corr(
                    self.returns_data[strategy2]
                ).dropna()
                
                if len(rolling_corr) > 0:
                    rolling_correlations[(strategy1, strategy2)] = rolling_corr
        
        # Compare EWMA vs rolling correlations (simplified)
        if rolling_correlations:
            total_mae = 0
            total_pairs = 0
            
            for (s1, s2), rolling_corr in rolling_correlations.items():
                if s1 in self.ewma_correlation.index and s2 in self.ewma_correlation.columns:
                    ewma_corr_value = self.ewma_correlation.loc[s1, s2]
                    mae = np.mean(np.abs(rolling_corr.iloc[-10:] - ewma_corr_value))
                    total_mae += mae
                    total_pairs += 1
            
            avg_mae = total_mae / total_pairs if total_pairs > 0 else 0
            
            self.fit_statistics = {
                "average_mae_vs_rolling": avg_mae,
                "comparison_pairs": total_pairs,
                "model_complexity": "low"
            }
    
    def predict_correlation(
        self,
        strategy1: str,
        strategy2: str,
        horizon: int = 1
    ) -> CorrelationForecast:
        """Predict correlation using EWMA persistence"""
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction")
        
        if strategy1 not in self.ewma_correlation.index or strategy2 not in self.ewma_correlation.columns:
            raise ValueError(f"Strategies {strategy1}, {strategy2} not found in fitted data")
        
        # EWMA assumes correlation persistence
        current_correlation = self.ewma_correlation.loc[strategy1, strategy2]
        
        # Simple persistence model with decay
        persistence_decay = 0.95 ** horizon  # Decay over time
        forecasted_correlation = current_correlation * persistence_decay
        
        # Estimate prediction variance (increases with horizon)
        base_variance = 0.01  # Base uncertainty
        horizon_variance = base_variance * (1 + 0.1 * np.sqrt(horizon))
        
        # Confidence interval (95%)
        z_score = 1.96
        margin_error = z_score * np.sqrt(horizon_variance)
        
        confidence_interval = (
            max(-1, forecasted_correlation - margin_error),
            min(1, forecasted_correlation + margin_error)
        )
        
        return CorrelationForecast(
            strategy_pair=(strategy1, strategy2),
            forecast_date=datetime.utcnow(),
            horizon_days=horizon,
            forecasted_correlation=forecasted_correlation,
            confidence_interval=confidence_interval,
            prediction_variance=horizon_variance,
            model_type=self.model_type,
            model_confidence=max(0.5, 1 - 0.1 * np.sqrt(horizon))
        )
    
    def get_correlation_matrix(self, date: Optional[datetime] = None) -> pd.DataFrame:
        """Get EWMA correlation matrix"""
        if not self.is_fitted:
            raise ValueError("Model must be fitted first")
        
        return self.ewma_correlation.copy()


class GARCHDCCModel(CorrelationModel):
    """
    GARCH Dynamic Conditional Correlation Model
    
    Implements Engle's DCC-GARCH model for time-varying correlations.
    """
    
    def __init__(self, alpha: float = 0.01, beta: float = 0.95):
        super().__init__(CorrelationModelType.GARCH_DCC)
        self.alpha = alpha  # DCC short-term parameter
        self.beta = beta    # DCC long-term parameter
        self.returns_data = None
        self.garch_models = {}
        self.standardized_residuals = None
        self.dynamic_correlations = None
        self.unconditional_correlation = None
    
    def fit(self, returns_data: pd.DataFrame) -> 'GARCHDCCModel':
        """Fit GARCH-DCC model"""
        self.returns_data = returns_data.dropna()
        
        if len(self.returns_data) < 50:
            raise ValueError("Insufficient data for GARCH-DCC model (minimum 50 observations)")
        
        strategies = list(self.returns_data.columns)
        
        try:
            # Step 1: Fit univariate GARCH models
            self.garch_models = {}
            self.standardized_residuals = pd.DataFrame(
                index=self.returns_data.index,
                columns=strategies
            )
            
            for strategy in strategies:
                try:
                    # Fit GARCH(1,1) model
                    returns_series = self.returns_data[strategy] * 100  # Scale for numerical stability
                    
                    garch_model = arch_model(
                        returns_series,
                        mean='Constant',
                        vol='GARCH',
                        p=1, q=1
                    )
                    
                    fitted_model = garch_model.fit(disp='off', show_warning=False)
                    self.garch_models[strategy] = fitted_model
                    
                    # Get standardized residuals
                    standardized_resid = fitted_model.resid / fitted_model.conditional_volatility
                    self.standardized_residuals[strategy] = standardized_resid
                
                except Exception as e:
                    logger.warning(f"GARCH fitting failed for {strategy}: {e}")
                    # Fallback to simple standardization
                    std_returns = self.returns_data[strategy] / self.returns_data[strategy].std()
                    self.standardized_residuals[strategy] = std_returns
            
            # Step 2: Estimate DCC parameters and dynamic correlations
            self._estimate_dcc_correlations()
            
            # Store model parameters
            self.parameters = {
                "alpha": self.alpha,
                "beta": self.beta,
                "n_strategies": len(strategies),
                "garch_specifications": {
                    strategy: str(model.model) if strategy in self.garch_models else "fallback"
                    for strategy in strategies
                }
            }
            
            # Calculate fit statistics
            self._calculate_dcc_fit_statistics()
            
            self.is_fitted = True
            
        except Exception as e:
            logger.error(f"GARCH-DCC model fitting failed: {e}")
            # Fallback to simple correlation
            self._fallback_to_simple_correlation()
        
        return self
    
    def _estimate_dcc_correlations(self):
        """Estimate dynamic conditional correlations"""
        
        # Get standardized residuals matrix
        residuals_matrix = self.standardized_residuals.dropna()
        
        if len(residuals_matrix) < 10:
            raise ValueError("Insufficient standardized residuals for DCC estimation")
        
        # Unconditional correlation matrix
        self.unconditional_correlation = residuals_matrix.corr()
        
        # Initialize dynamic correlation matrices
        n_obs, n_assets = residuals_matrix.shape
        self.dynamic_correlations = []
        
        # Initialize Q matrix (correlation proxy)
        Q = self.unconditional_correlation.values.copy()
        
        # DCC estimation
        for t in range(n_obs):
            if t > 0:
                # Get residual vector
                resid_t = residuals_matrix.iloc[t].values.reshape(-1, 1)
                resid_t_prev = residuals_matrix.iloc[t-1].values.reshape(-1, 1)
                
                # Update Q matrix: Q_t = (1-α-β)*Q̄ + α*ε_{t-1}ε'_{t-1} + β*Q_{t-1}
                Q = ((1 - self.alpha - self.beta) * self.unconditional_correlation.values +
                     self.alpha * np.outer(resid_t_prev.flatten(), resid_t_prev.flatten()) +
                     self.beta * Q)
            
            # Convert Q to correlation matrix
            diag_sqrt_Q = np.sqrt(np.diag(Q))
            R = Q / np.outer(diag_sqrt_Q, diag_sqrt_Q)
            
            # Ensure correlation matrix properties
            R = np.clip(R, -0.99, 0.99)
            np.fill_diagonal(R, 1.0)
            
            # Store correlation matrix
            corr_df = pd.DataFrame(
                R,
                index=residuals_matrix.columns,
                columns=residuals_matrix.columns
            )
            self.dynamic_correlations.append(corr_df)
    
    def _fallback_to_simple_correlation(self):
        """Fallback to simple correlation if DCC fails"""
        logger.warning("Using simple correlation fallback for GARCH-DCC")
        
        simple_corr = self.returns_data.corr()
        self.dynamic_correlations = [simple_corr] * len(self.returns_data)
        self.unconditional_correlation = simple_corr
        
        self.parameters = {
            "alpha": self.alpha,
            "beta": self.beta,
            "model_status": "fallback_simple_correlation"
        }
        
        self.fit_statistics = {
            "model_type": "fallback",
            "correlation_range": "static"
        }
        
        self.is_fitted = True
    
    def _calculate_dcc_fit_statistics(self):
        """Calculate DCC model fit statistics"""
        
        if not self.dynamic_correlations or len(self.dynamic_correlations) < 2:
            self.fit_statistics = {"status": "insufficient_data"}
            return
        
        try:
            # Calculate correlation volatility (time-varying nature)
            correlation_volatilities = {}
            strategies = list(self.dynamic_correlations[0].columns)
            
            for i, strategy1 in enumerate(strategies):
                for j, strategy2 in enumerate(strategies[i+1:], i+1):
                    correlations_over_time = [
                        corr_matrix.loc[strategy1, strategy2]
                        for corr_matrix in self.dynamic_correlations
                    ]
                    
                    correlation_volatilities[(strategy1, strategy2)] = np.std(correlations_over_time)
            
            avg_correlation_volatility = np.mean(list(correlation_volatilities.values()))
            
            self.fit_statistics = {
                "average_correlation_volatility": avg_correlation_volatility,
                "dynamic_correlation_pairs": len(correlation_volatilities),
                "model_complexity": "high",
                "dcc_persistence": self.alpha + self.beta
            }
        
        except Exception as e:
            logger.warning(f"DCC fit statistics calculation failed: {e}")
            self.fit_statistics = {"status": "statistics_calculation_failed"}
    
    def predict_correlation(
        self,
        strategy1: str,
        strategy2: str,
        horizon: int = 1
    ) -> CorrelationForecast:
        """Predict correlation using DCC dynamics"""
        
        if not self.is_fitted or not self.dynamic_correlations:
            raise ValueError("Model must be fitted before prediction")
        
        # Get latest correlation
        latest_correlation_matrix = self.dynamic_correlations[-1]
        
        if strategy1 not in latest_correlation_matrix.index or strategy2 not in latest_correlation_matrix.columns:
            raise ValueError(f"Strategies {strategy1}, {strategy2} not found in fitted data")
        
        current_correlation = latest_correlation_matrix.loc[strategy1, strategy2]
        unconditional_corr = self.unconditional_correlation.loc[strategy1, strategy2]
        
        # DCC forecast: correlation mean-reverts to unconditional correlation
        persistence = (self.alpha + self.beta) ** horizon
        forecasted_correlation = (
            persistence * current_correlation +
            (1 - persistence) * unconditional_corr
        )
        
        # Prediction variance increases with horizon
        base_variance = 0.005  # Base DCC prediction uncertainty
        horizon_variance = base_variance * (1 - persistence**2) / (1 - (self.alpha + self.beta)**2)
        
        # Confidence interval
        z_score = 1.96
        margin_error = z_score * np.sqrt(horizon_variance)
        
        confidence_interval = (
            max(-1, forecasted_correlation - margin_error),
            min(1, forecasted_correlation + margin_error)
        )
        
        # Model confidence decreases with horizon
        model_confidence = max(0.3, 0.9 - 0.05 * np.sqrt(horizon))
        
        return CorrelationForecast(
            strategy_pair=(strategy1, strategy2),
            forecast_date=datetime.utcnow(),
            horizon_days=horizon,
            forecasted_correlation=forecasted_correlation,
            confidence_interval=confidence_interval,
            prediction_variance=horizon_variance,
            model_type=self.model_type,
            model_confidence=model_confidence
        )
    
    def get_correlation_matrix(self, date: Optional[datetime] = None) -> pd.DataFrame:
        """Get correlation matrix at specified date"""
        
        if not self.is_fitted or not self.dynamic_correlations:
            raise ValueError("Model must be fitted first")
        
        if date is None:
            # Return latest correlation matrix
            return self.dynamic_correlations[-1].copy()
        
        # For simplicity, return latest (time-series indexing would require date alignment)
        return self.dynamic_correlations[-1].copy()


class ShrinkageCorrelationModel(CorrelationModel):
    """
    Shrinkage Correlation Model
    
    Uses Ledoit-Wolf shrinkage estimation for robust correlation matrices.
    """
    
    def __init__(self, shrinkage_target: str = "identity"):
        super().__init__(CorrelationModelType.SHRINKAGE)
        self.shrinkage_target = shrinkage_target  # "identity" or "constant_correlation"
        self.returns_data = None
        self.shrinkage_correlation = None
        self.shrinkage_intensity = None
    
    def fit(self, returns_data: pd.DataFrame) -> 'ShrinkageCorrelationModel':
        """Fit shrinkage correlation model"""
        
        self.returns_data = returns_data.dropna()
        
        if len(self.returns_data) < 20:
            raise ValueError("Insufficient data for shrinkage correlation model")
        
        try:
            # Apply Ledoit-Wolf shrinkage
            if self.shrinkage_target == "identity":
                estimator = LedoitWolf()
            else:
                estimator = ShrunkCovariance()
            
            # Fit shrinkage estimator
            estimator.fit(self.returns_data.values)
            
            # Get shrinkage covariance
            shrinkage_cov = estimator.covariance_
            
            # Convert to correlation matrix
            diag_sqrt = np.sqrt(np.diag(shrinkage_cov))
            correlation_matrix = shrinkage_cov / np.outer(diag_sqrt, diag_sqrt)
            
            # Create DataFrame
            self.shrinkage_correlation = pd.DataFrame(
                correlation_matrix,
                index=self.returns_data.columns,
                columns=self.returns_data.columns
            )
            
            # Store shrinkage intensity
            if hasattr(estimator, 'shrinkage_'):
                self.shrinkage_intensity = estimator.shrinkage_
            else:
                self.shrinkage_intensity = 0.1  # Default estimate
            
            # Model parameters
            self.parameters = {
                "shrinkage_target": self.shrinkage_target,
                "shrinkage_intensity": self.shrinkage_intensity,
                "n_observations": len(self.returns_data),
                "n_assets": len(self.returns_data.columns)
            }
            
            # Fit statistics
            self._calculate_shrinkage_fit_statistics()
            
            self.is_fitted = True
        
        except Exception as e:
            logger.error(f"Shrinkage correlation model fitting failed: {e}")
            # Fallback to sample correlation
            self.shrinkage_correlation = self.returns_data.corr()
            self.shrinkage_intensity = 0.0
            self.parameters = {"model_status": "fallback_sample_correlation"}
            self.is_fitted = True
        
        return self
    
    def _calculate_shrinkage_fit_statistics(self):
        """Calculate shrinkage model fit statistics"""
        
        # Compare with sample correlation
        sample_correlation = self.returns_data.corr()
        
        # Calculate differences
        correlation_differences = (self.shrinkage_correlation - sample_correlation).values
        
        # Remove diagonal elements
        off_diagonal_mask = ~np.eye(correlation_differences.shape[0], dtype=bool)
        off_diagonal_diffs = correlation_differences[off_diagonal_mask]
        
        self.fit_statistics = {
            "shrinkage_intensity": self.shrinkage_intensity,
            "mean_absolute_difference": np.mean(np.abs(off_diagonal_diffs)),
            "max_absolute_difference": np.max(np.abs(off_diagonal_diffs)),
            "correlation_adjustment_std": np.std(off_diagonal_diffs)
        }
    
    def predict_correlation(
        self,
        strategy1: str,
        strategy2: str,
        horizon: int = 1
    ) -> CorrelationForecast:
        """Predict correlation using shrinkage estimate (static prediction)"""
        
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction")
        
        if strategy1 not in self.shrinkage_correlation.index or strategy2 not in self.shrinkage_correlation.columns:
            raise ValueError(f"Strategies {strategy1}, {strategy2} not found in fitted data")
        
        # Shrinkage provides static correlation estimate
        forecasted_correlation = self.shrinkage_correlation.loc[strategy1, strategy2]
        
        # Prediction uncertainty increases with horizon
        base_variance = 0.02 * self.shrinkage_intensity  # Higher shrinkage = lower uncertainty
        horizon_variance = base_variance * (1 + 0.1 * np.log(1 + horizon))
        
        # Confidence interval
        z_score = 1.96
        margin_error = z_score * np.sqrt(horizon_variance)
        
        confidence_interval = (
            max(-1, forecasted_correlation - margin_error),
            min(1, forecasted_correlation + margin_error)
        )
        
        # Higher shrinkage intensity = higher confidence in stable correlation
        model_confidence = max(0.4, 0.8 + 0.2 * self.shrinkage_intensity - 0.02 * horizon)
        
        return CorrelationForecast(
            strategy_pair=(strategy1, strategy2),
            forecast_date=datetime.utcnow(),
            horizon_days=horizon,
            forecasted_correlation=forecasted_correlation,
            confidence_interval=confidence_interval,
            prediction_variance=horizon_variance,
            model_type=self.model_type,
            model_confidence=model_confidence
        )
    
    def get_correlation_matrix(self, date: Optional[datetime] = None) -> pd.DataFrame:
        """Get shrinkage correlation matrix"""
        
        if not self.is_fitted:
            raise ValueError("Model must be fitted first")
        
        return self.shrinkage_correlation.copy()


class DynamicCorrelationModel(CorrelationModel):
    """
    Dynamic Correlation Model Factory
    
    Combines multiple correlation models for robust estimation and forecasting.
    """
    
    def __init__(self, models: List[CorrelationModel] = None):
        super().__init__(CorrelationModelType.DYNAMIC_CONDITIONAL)
        
        if models is None:
            # Default model ensemble
            self.models = [
                EWMACorrelationModel(decay_factor=0.94),
                ShrinkageCorrelationModel(),
                GARCHDCCModel()
            ]
        else:
            self.models = models
        
        self.model_weights = None
        self.ensemble_correlation = None
    
    def fit(self, returns_data: pd.DataFrame) -> 'DynamicCorrelationModel':
        """Fit all models in ensemble"""
        
        fitted_models = []
        model_scores = []
        
        for model in self.models:
            try:
                model.fit(returns_data)
                fitted_models.append(model)
                
                # Simple scoring based on model complexity and fit
                if model.fit_statistics:
                    score = 1.0  # Default score
                    
                    # Adjust score based on model characteristics
                    if model.model_type == CorrelationModelType.SHRINKAGE:
                        score = 0.8 + 0.2 * model.shrinkage_intensity
                    elif model.model_type == CorrelationModelType.GARCH_DCC:
                        score = 0.7  # Complex but potentially overfitting
                    elif model.model_type == CorrelationModelType.EWMA:
                        score = 0.9  # Good balance
                    
                    model_scores.append(score)
                else:
                    model_scores.append(0.5)  # Low score for failed fits
            
            except Exception as e:
                logger.warning(f"Model {model.model_type.value} failed to fit: {e}")
        
        if not fitted_models:
            raise ValueError("No models successfully fitted")
        
        # Calculate ensemble weights (normalized scores)
        total_score = sum(model_scores)
        self.model_weights = [score / total_score for score in model_scores] if total_score > 0 else [1/len(fitted_models)] * len(fitted_models)
        
        self.models = fitted_models
        
        # Create ensemble correlation matrix
        self._create_ensemble_correlation()
        
        # Store parameters
        self.parameters = {
            "n_models": len(self.models),
            "model_types": [model.model_type.value for model in self.models],
            "model_weights": self.model_weights
        }
        
        self.fit_statistics = {
            "ensemble_size": len(self.models),
            "successful_fits": len(fitted_models),
            "weight_distribution": dict(zip([m.model_type.value for m in self.models], self.model_weights))
        }
        
        self.is_fitted = True
        return self
    
    def _create_ensemble_correlation(self):
        """Create weighted ensemble correlation matrix"""
        
        if not self.models or not self.model_weights:
            return
        
        # Get correlation matrices from all models
        correlation_matrices = []
        for model in self.models:
            try:
                corr_matrix = model.get_correlation_matrix()
                correlation_matrices.append(corr_matrix)
            except Exception as e:
                logger.warning(f"Failed to get correlation matrix from {model.model_type.value}: {e}")
        
        if not correlation_matrices:
            return
        
        # Weighted average of correlation matrices
        strategies = correlation_matrices[0].index
        weighted_correlation = pd.DataFrame(
            np.zeros((len(strategies), len(strategies))),
            index=strategies,
            columns=strategies
        )
        
        for i, corr_matrix in enumerate(correlation_matrices):
            weight = self.model_weights[i]
            weighted_correlation += weight * corr_matrix
        
        self.ensemble_correlation = weighted_correlation
    
    def predict_correlation(
        self,
        strategy1: str,
        strategy2: str,
        horizon: int = 1
    ) -> CorrelationForecast:
        """Ensemble correlation prediction"""
        
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction")
        
        # Get predictions from all models
        model_forecasts = []
        for model in self.models:
            try:
                forecast = model.predict_correlation(strategy1, strategy2, horizon)
                model_forecasts.append(forecast)
            except Exception as e:
                logger.warning(f"Prediction failed for {model.model_type.value}: {e}")
        
        if not model_forecasts:
            raise ValueError("No models produced valid forecasts")
        
        # Weighted ensemble prediction
        weighted_correlation = 0.0
        weighted_variance = 0.0
        total_weight = 0.0
        
        for i, forecast in enumerate(model_forecasts):
            if i < len(self.model_weights):
                weight = self.model_weights[i] * forecast.model_confidence
                weighted_correlation += weight * forecast.forecasted_correlation
                weighted_variance += weight**2 * forecast.prediction_variance
                total_weight += weight
        
        if total_weight > 0:
            ensemble_correlation = weighted_correlation / total_weight
            ensemble_variance = weighted_variance / (total_weight**2)
        else:
            ensemble_correlation = model_forecasts[0].forecasted_correlation
            ensemble_variance = model_forecasts[0].prediction_variance
        
        # Ensemble confidence interval
        z_score = 1.96
        margin_error = z_score * np.sqrt(ensemble_variance)
        
        confidence_interval = (
            max(-1, ensemble_correlation - margin_error),
            min(1, ensemble_correlation + margin_error)
        )
        
        # Ensemble confidence (weighted average)
        ensemble_confidence = sum(
            self.model_weights[i] * forecast.model_confidence
            for i, forecast in enumerate(model_forecasts)
            if i < len(self.model_weights)
        ) / sum(self.model_weights)
        
        return CorrelationForecast(
            strategy_pair=(strategy1, strategy2),
            forecast_date=datetime.utcnow(),
            horizon_days=horizon,
            forecasted_correlation=ensemble_correlation,
            confidence_interval=confidence_interval,
            prediction_variance=ensemble_variance,
            model_type=self.model_type,
            model_confidence=ensemble_confidence
        )
    
    def get_correlation_matrix(self, date: Optional[datetime] = None) -> pd.DataFrame:
        """Get ensemble correlation matrix"""
        
        if not self.is_fitted:
            raise ValueError("Model must be fitted first")
        
        if self.ensemble_correlation is not None:
            return self.ensemble_correlation.copy()
        
        # Fallback to first available model
        for model in self.models:
            try:
                return model.get_correlation_matrix(date)
            except Exception:
                continue
        
        raise ValueError("No models available for correlation matrix")
    
    def get_model_comparison(self) -> Dict[str, Dict]:
        """Compare performance of different models in ensemble"""
        
        if not self.is_fitted:
            return {}
        
        comparison = {}
        for i, model in enumerate(self.models):
            comparison[model.model_type.value] = {
                "weight": self.model_weights[i] if i < len(self.model_weights) else 0,
                "model_info": model.get_model_info(),
                "is_primary": i == 0
            }
        
        return comparison


def create_correlation_model(
    model_type: CorrelationModelType,
    **kwargs
) -> CorrelationModel:
    """Factory function to create correlation models"""
    
    if model_type == CorrelationModelType.EWMA:
        return EWMACorrelationModel(**kwargs)
    elif model_type == CorrelationModelType.GARCH_DCC:
        return GARCHDCCModel(**kwargs)
    elif model_type == CorrelationModelType.SHRINKAGE:
        return ShrinkageCorrelationModel(**kwargs)
    elif model_type == CorrelationModelType.DYNAMIC_CONDITIONAL:
        return DynamicCorrelationModel(**kwargs)
    else:
        raise ValueError(f"Unsupported correlation model type: {model_type}")


def compare_correlation_models(
    returns_data: pd.DataFrame,
    models: List[CorrelationModel] = None,
    test_strategies: List[Tuple[str, str]] = None
) -> Dict[str, Dict]:
    """
    Compare multiple correlation models on the same dataset
    """
    
    if models is None:
        models = [
            EWMACorrelationModel(),
            ShrinkageCorrelationModel(),
            GARCHDCCModel()
        ]
    
    if test_strategies is None and len(returns_data.columns) >= 2:
        # Use first few strategy pairs for testing
        strategies = list(returns_data.columns)
        test_strategies = [(strategies[i], strategies[j]) for i in range(min(3, len(strategies))) for j in range(i+1, min(3, len(strategies)))]
    
    comparison_results = {}
    
    for model in models:
        model_name = model.model_type.value
        comparison_results[model_name] = {
            "model_info": {},
            "fit_success": False,
            "prediction_examples": []
        }
        
        try:
            # Fit model
            model.fit(returns_data)
            comparison_results[model_name]["model_info"] = model.get_model_info()
            comparison_results[model_name]["fit_success"] = True
            
            # Test predictions if test strategies provided
            if test_strategies:
                for strategy1, strategy2 in test_strategies[:3]:  # Test up to 3 pairs
                    try:
                        forecast = model.predict_correlation(strategy1, strategy2, horizon=7)
                        comparison_results[model_name]["prediction_examples"].append({
                            "pair": f"{strategy1}-{strategy2}",
                            "forecast": forecast.to_dict()
                        })
                    except Exception as e:
                        logger.warning(f"Prediction failed for {model_name} on {strategy1}-{strategy2}: {e}")
        
        except Exception as e:
            comparison_results[model_name]["error"] = str(e)
            logger.error(f"Model {model_name} fitting failed: {e}")
    
    return comparison_results