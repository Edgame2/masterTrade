"""
Market Regime Detection

Identifies market regimes (bull/bear/sideways) using:
- Hidden Markov Models (HMM)
- Gaussian Mixture Models (GMM)
- Technical indicators and volatility patterns
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Tuple
import numpy as np
import logging

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime types"""
    BULL = "bull"           # Strong uptrend
    BEAR = "bear"           # Strong downtrend
    SIDEWAYS = "sideways"   # Ranging/choppy
    HIGH_VOL = "high_vol"   # High volatility
    LOW_VOL = "low_vol"     # Low volatility
    UNKNOWN = "unknown"


@dataclass
class RegimeFeatures:
    """Features used for regime detection"""
    returns: List[float]
    volatility: float
    trend_strength: float  # 0-1, higher = stronger trend
    volume_ratio: float    # Current volume / average volume
    drawdown: float
    
    # Technical indicators
    rsi: Optional[float] = None
    adx: Optional[float] = None  # Average Directional Index
    atr: Optional[float] = None  # Average True Range
    
    # Higher-order statistics
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None
    
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_array(self) -> np.ndarray:
        """Convert features to numpy array for ML models"""
        features = [
            np.mean(self.returns) if self.returns else 0,
            np.std(self.returns) if self.returns else 0,
            self.volatility,
            self.trend_strength,
            self.volume_ratio,
            self.drawdown,
            self.rsi or 50,
            self.adx or 25,
            self.atr or 0,
            self.skewness or 0,
            self.kurtosis or 3,
        ]
        return np.array(features)


@dataclass
class RegimeDetection:
    """Result of regime detection"""
    regime: MarketRegime
    confidence: float  # 0-1
    probabilities: Dict[MarketRegime, float]  # Probability for each regime
    features: RegimeFeatures
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "confidence": self.confidence,
            "probabilities": {k.value: v for k, v in self.probabilities.items()},
            "volatility": self.features.volatility,
            "trend_strength": self.features.trend_strength,
            "timestamp": self.timestamp.isoformat(),
        }


class RegimeDetector:
    """
    Base class for regime detection.
    
    Detects market regimes to adapt strategy behavior:
    - Bull market: More aggressive, trend-following
    - Bear market: Defensive, short-biased
    - Sideways: Mean-reversion, range trading
    """
    
    def __init__(self, lookback_period: int = 50):
        self.lookback_period = lookback_period
        self.history: List[RegimeDetection] = []
        self.current_regime: Optional[MarketRegime] = None
        
    def detect(self, features: RegimeFeatures) -> RegimeDetection:
        """Detect current market regime"""
        raise NotImplementedError
    
    def get_regime_statistics(self) -> Dict[str, any]:
        """Get regime statistics from history"""
        if not self.history:
            return {}
        
        regime_counts = {}
        for detection in self.history:
            regime = detection.regime.value
            regime_counts[regime] = regime_counts.get(regime, 0) + 1
        
        total = len(self.history)
        regime_percentages = {k: v/total for k, v in regime_counts.items()}
        
        # Average confidence per regime
        regime_confidences = {}
        for regime in MarketRegime:
            regime_detections = [d for d in self.history if d.regime == regime]
            if regime_detections:
                avg_conf = np.mean([d.confidence for d in regime_detections])
                regime_confidences[regime.value] = avg_conf
        
        return {
            "total_detections": total,
            "regime_percentages": regime_percentages,
            "regime_confidences": regime_confidences,
            "current_regime": self.current_regime.value if self.current_regime else None,
        }


class HMMRegimeDetector(RegimeDetector):
    """
    Hidden Markov Model for regime detection.
    
    Uses HMM to model regime transitions:
    - States represent different market regimes
    - Observations are feature vectors
    - Transition matrix captures regime persistence
    """
    
    def __init__(self, n_states: int = 3, lookback_period: int = 50):
        super().__init__(lookback_period)
        self.n_states = n_states
        self.model = None
        self.is_fitted = False
        
        # State to regime mapping
        self.state_to_regime = {
            0: MarketRegime.BEAR,
            1: MarketRegime.SIDEWAYS,
            2: MarketRegime.BULL,
        }
        
        logger.info(f"HMMRegimeDetector initialized with {n_states} states")
    
    def fit(self, historical_features: List[RegimeFeatures]):
        """
        Fit HMM to historical data.
        
        Args:
            historical_features: List of historical feature observations
        """
        try:
            from hmmlearn import hmm
            
            # Convert features to array
            X = np.array([f.to_array() for f in historical_features])
            X = X.reshape(-1, 1) if X.ndim == 1 else X
            
            # Fit Gaussian HMM
            self.model = hmm.GaussianHMM(
                n_components=self.n_states,
                covariance_type="full",
                n_iter=100,
                random_state=42,
            )
            
            self.model.fit(X)
            self.is_fitted = True
            
            logger.info(f"HMM fitted with {len(historical_features)} observations")
            
        except ImportError:
            logger.error("hmmlearn not installed. Install with: pip install hmmlearn")
            raise
        except Exception as e:
            logger.error(f"Error fitting HMM: {e}")
            raise
    
    def detect(self, features: RegimeFeatures) -> RegimeDetection:
        """Detect regime using HMM"""
        if not self.is_fitted:
            # Fallback to rule-based detection
            return self._rule_based_detect(features)
        
        try:
            # Convert to array
            X = features.to_array().reshape(1, -1)
            
            # Predict state
            state = self.model.predict(X)[0]
            
            # Get state probabilities
            log_prob, posteriors = self.model.score_samples(X)
            state_probs = posteriors[0]
            
            # Map state to regime
            regime = self.state_to_regime.get(state, MarketRegime.UNKNOWN)
            confidence = state_probs[state]
            
            # Build probability dict
            probabilities = {
                self.state_to_regime[i]: state_probs[i]
                for i in range(self.n_states)
            }
            
            detection = RegimeDetection(
                regime=regime,
                confidence=confidence,
                probabilities=probabilities,
                features=features,
            )
            
            self.history.append(detection)
            self.current_regime = regime
            
            logger.debug(f"Detected regime: {regime.value} (confidence: {confidence:.2f})")
            
            return detection
            
        except Exception as e:
            logger.error(f"Error in HMM detection: {e}")
            return self._rule_based_detect(features)
    
    def _rule_based_detect(self, features: RegimeFeatures) -> RegimeDetection:
        """Fallback rule-based regime detection"""
        avg_return = np.mean(features.returns) if features.returns else 0
        
        # Simple rules
        if avg_return > 0.005 and features.trend_strength > 0.6:
            regime = MarketRegime.BULL
            confidence = min(features.trend_strength, 0.85)
        elif avg_return < -0.005 and features.trend_strength > 0.6:
            regime = MarketRegime.BEAR
            confidence = min(features.trend_strength, 0.85)
        elif features.volatility > 0.03:
            regime = MarketRegime.HIGH_VOL
            confidence = 0.7
        else:
            regime = MarketRegime.SIDEWAYS
            confidence = 0.6
        
        probabilities = {regime: confidence}
        
        detection = RegimeDetection(
            regime=regime,
            confidence=confidence,
            probabilities=probabilities,
            features=features,
        )
        
        self.history.append(detection)
        self.current_regime = regime
        
        return detection


class GMMRegimeDetector(RegimeDetector):
    """
    Gaussian Mixture Model for regime detection.
    
    Uses GMM to cluster market states:
    - Each component represents a regime
    - Soft clustering gives regime probabilities
    """
    
    def __init__(self, n_components: int = 3, lookback_period: int = 50):
        super().__init__(lookback_period)
        self.n_components = n_components
        self.model = None
        self.is_fitted = False
        
        # Component to regime mapping (determined after fitting)
        self.component_to_regime = {}
        
        logger.info(f"GMMRegimeDetector initialized with {n_components} components")
    
    def fit(self, historical_features: List[RegimeFeatures]):
        """
        Fit GMM to historical data.
        
        Args:
            historical_features: List of historical feature observations
        """
        try:
            from sklearn.mixture import GaussianMixture
            
            # Convert features to array
            X = np.array([f.to_array() for f in historical_features])
            
            # Fit GMM
            self.model = GaussianMixture(
                n_components=self.n_components,
                covariance_type='full',
                random_state=42,
                max_iter=100,
            )
            
            self.model.fit(X)
            
            # Determine component to regime mapping based on mean returns
            labels = self.model.predict(X)
            mean_returns_by_component = {}
            
            for i in range(self.n_components):
                component_features = [f for f, l in zip(historical_features, labels) if l == i]
                if component_features:
                    mean_return = np.mean([np.mean(f.returns) for f in component_features])
                    mean_returns_by_component[i] = mean_return
            
            # Sort components by mean return
            sorted_components = sorted(mean_returns_by_component.items(), key=lambda x: x[1])
            
            if len(sorted_components) >= 3:
                self.component_to_regime[sorted_components[0][0]] = MarketRegime.BEAR
                self.component_to_regime[sorted_components[1][0]] = MarketRegime.SIDEWAYS
                self.component_to_regime[sorted_components[2][0]] = MarketRegime.BULL
            
            self.is_fitted = True
            logger.info(f"GMM fitted with {len(historical_features)} observations")
            
        except ImportError:
            logger.error("scikit-learn not installed. Install with: pip install scikit-learn")
            raise
        except Exception as e:
            logger.error(f"Error fitting GMM: {e}")
            raise
    
    def detect(self, features: RegimeFeatures) -> RegimeDetection:
        """Detect regime using GMM"""
        if not self.is_fitted:
            # Use HMM fallback
            hmm_detector = HMMRegimeDetector()
            return hmm_detector._rule_based_detect(features)
        
        try:
            # Convert to array
            X = features.to_array().reshape(1, -1)
            
            # Predict component
            component = self.model.predict(X)[0]
            
            # Get component probabilities
            probabilities_array = self.model.predict_proba(X)[0]
            
            # Map component to regime
            regime = self.component_to_regime.get(component, MarketRegime.UNKNOWN)
            confidence = probabilities_array[component]
            
            # Build probability dict
            probabilities = {}
            for comp_idx, prob in enumerate(probabilities_array):
                regime_for_comp = self.component_to_regime.get(comp_idx, MarketRegime.UNKNOWN)
                if regime_for_comp in probabilities:
                    probabilities[regime_for_comp] += prob
                else:
                    probabilities[regime_for_comp] = prob
            
            detection = RegimeDetection(
                regime=regime,
                confidence=confidence,
                probabilities=probabilities,
                features=features,
            )
            
            self.history.append(detection)
            self.current_regime = regime
            
            logger.debug(f"Detected regime: {regime.value} (confidence: {confidence:.2f})")
            
            return detection
            
        except Exception as e:
            logger.error(f"Error in GMM detection: {e}")
            hmm_detector = HMMRegimeDetector()
            return hmm_detector._rule_based_detect(features)


def calculate_regime_features(
    prices: np.ndarray,
    volumes: Optional[np.ndarray] = None,
    lookback: int = 20,
) -> RegimeFeatures:
    """
    Calculate regime features from price data.
    
    Args:
        prices: Array of prices
        volumes: Optional array of volumes
        lookback: Lookback period for calculations
        
    Returns:
        RegimeFeatures object
    """
    if len(prices) < lookback:
        lookback = len(prices)
    
    recent_prices = prices[-lookback:]
    
    # Returns
    returns = np.diff(recent_prices) / recent_prices[:-1]
    
    # Volatility (std of returns)
    volatility = np.std(returns)
    
    # Trend strength (using linear regression R²)
    x = np.arange(len(recent_prices))
    coeffs = np.polyfit(x, recent_prices, 1)
    y_pred = np.poly1d(coeffs)(x)
    ss_res = np.sum((recent_prices - y_pred) ** 2)
    ss_tot = np.sum((recent_prices - np.mean(recent_prices)) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    trend_strength = max(0, min(1, r_squared))
    
    # Volume ratio
    volume_ratio = 1.0
    if volumes is not None and len(volumes) >= lookback:
        recent_volumes = volumes[-lookback:]
        current_volume = volumes[-1]
        avg_volume = np.mean(recent_volumes[:-1])
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
    
    # Drawdown
    running_max = np.maximum.accumulate(recent_prices)
    drawdown = (recent_prices[-1] - running_max[-1]) / running_max[-1]
    
    # RSI
    rsi = calculate_rsi(returns, period=14)
    
    # ADX (simplified)
    adx = trend_strength * 100  # Simplified ADX approximation
    
    # ATR
    atr = volatility * recent_prices[-1]  # Simplified ATR
    
    # Skewness and kurtosis
    from scipy import stats
    skewness = stats.skew(returns) if len(returns) > 0 else 0
    kurtosis = stats.kurtosis(returns) if len(returns) > 0 else 3
    
    return RegimeFeatures(
        returns=returns.tolist(),
        volatility=volatility,
        trend_strength=trend_strength,
        volume_ratio=volume_ratio,
        drawdown=drawdown,
        rsi=rsi,
        adx=adx,
        atr=atr,
        skewness=skewness,
        kurtosis=kurtosis,
    )


def calculate_rsi(returns: np.ndarray, period: int = 14) -> float:
    """Calculate RSI from returns"""
    if len(returns) < period:
        return 50.0
    
    gains = np.where(returns > 0, returns, 0)
    losses = np.where(returns < 0, -returns, 0)
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi
