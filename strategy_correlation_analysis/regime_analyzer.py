"""
Market Regime Analyzer

Advanced market regime detection and regime-based correlation analysis including:
- Hidden Markov Model regime detection
- Regime-specific correlation analysis
- Regime transition analysis and prediction
- Dynamic regime-based strategy allocation
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import warnings

# Suppress sklearn warnings
with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    from sklearn.mixture import GaussianMixture
    from hmmlearn import hmm
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans

import scipy.stats as stats
from scipy import linalg

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classifications"""
    BULL_LOW_VOL = "bull_low_volatility"
    BULL_HIGH_VOL = "bull_high_volatility" 
    BEAR_LOW_VOL = "bear_low_volatility"
    BEAR_HIGH_VOL = "bear_high_volatility"
    SIDEWAYS_LOW_VOL = "sideways_low_volatility"
    SIDEWAYS_HIGH_VOL = "sideways_high_volatility"
    CRISIS = "crisis"
    RECOVERY = "recovery"


class RegimeFeature(Enum):
    """Features used for regime detection"""
    RETURNS = "returns"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    VIX = "vix"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    SKEWNESS = "skewness"
    KURTOSIS = "kurtosis"


@dataclass
class RegimeTransition:
    """Regime transition information"""
    from_regime: MarketRegime
    to_regime: MarketRegime
    transition_date: datetime
    transition_probability: float
    duration_days: int
    market_context: Dict[str, float]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "from_regime": self.from_regime.value,
            "to_regime": self.to_regime.value,
            "transition_date": self.transition_date.isoformat(),
            "transition_probability": self.transition_probability,
            "duration_days": self.duration_days,
            "market_context": self.market_context
        }


@dataclass
class RegimeCorrelation:
    """Correlation analysis within market regimes"""
    regime: MarketRegime
    strategy_correlations: Dict[str, float]
    correlation_matrix: pd.DataFrame
    regime_probability: float
    sample_size: int
    start_date: datetime
    end_date: datetime
    regime_characteristics: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "regime": self.regime.value,
            "strategy_correlations": self.strategy_correlations,
            "correlation_matrix": self.correlation_matrix.to_dict(),
            "regime_probability": self.regime_probability,
            "sample_size": self.sample_size,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "regime_characteristics": self.regime_characteristics
        }


class HMMRegimeDetector:
    """
    Hidden Markov Model for regime detection
    
    Uses market features to identify distinct market regimes and
    their transition probabilities.
    """
    
    def __init__(
        self,
        n_regimes: int = 4,
        covariance_type: str = "full",
        n_iter: int = 100,
        random_state: int = 42
    ):
        self.n_regimes = n_regimes
        self.covariance_type = covariance_type
        self.n_iter = n_iter
        self.random_state = random_state
        
        self.model = None
        self.scaler = StandardScaler()
        self.regime_labels = {}
        self.transition_matrix = None
        self.is_fitted = False
    
    def prepare_features(
        self,
        market_data: pd.DataFrame,
        features: List[RegimeFeature] = None
    ) -> pd.DataFrame:
        """
        Prepare features for regime detection
        """
        if features is None:
            features = [
                RegimeFeature.RETURNS,
                RegimeFeature.VOLATILITY,
                RegimeFeature.MOMENTUM
            ]
        
        feature_df = pd.DataFrame(index=market_data.index)
        
        for feature in features:
            if feature == RegimeFeature.RETURNS:
                if 'close' in market_data.columns:
                    feature_df['returns'] = market_data['close'].pct_change()
                elif 'price' in market_data.columns:
                    feature_df['returns'] = market_data['price'].pct_change()
            
            elif feature == RegimeFeature.VOLATILITY:
                if 'returns' not in feature_df.columns:
                    if 'close' in market_data.columns:
                        returns = market_data['close'].pct_change()
                    elif 'price' in market_data.columns:
                        returns = market_data['price'].pct_change()
                    else:
                        continue
                else:
                    returns = feature_df['returns']
                
                # Rolling volatility (20-day)
                feature_df['volatility'] = returns.rolling(20, min_periods=10).std()
            
            elif feature == RegimeFeature.VOLUME:
                if 'volume' in market_data.columns:
                    # Normalized volume
                    volume_ma = market_data['volume'].rolling(20, min_periods=10).mean()
                    feature_df['volume_ratio'] = market_data['volume'] / volume_ma
            
            elif feature == RegimeFeature.VIX:
                if 'vix' in market_data.columns:
                    feature_df['vix'] = market_data['vix']
                elif 'volatility_index' in market_data.columns:
                    feature_df['vix'] = market_data['volatility_index']
            
            elif feature == RegimeFeature.MOMENTUM:
                if 'close' in market_data.columns:
                    price = market_data['close']
                elif 'price' in market_data.columns:
                    price = market_data['price']
                else:
                    continue
                
                # 20-day momentum
                feature_df['momentum'] = price / price.shift(20) - 1
            
            elif feature == RegimeFeature.MEAN_REVERSION:
                if 'close' in market_data.columns:
                    price = market_data['close']
                elif 'price' in market_data.columns:
                    price = market_data['price']
                else:
                    continue
                
                # Distance from moving average
                ma_20 = price.rolling(20, min_periods=10).mean()
                feature_df['mean_reversion'] = (price - ma_20) / ma_20
            
            elif feature == RegimeFeature.SKEWNESS:
                if 'returns' not in feature_df.columns:
                    if 'close' in market_data.columns:
                        returns = market_data['close'].pct_change()
                    elif 'price' in market_data.columns:
                        returns = market_data['price'].pct_change()
                    else:
                        continue
                else:
                    returns = feature_df['returns']
                
                # Rolling skewness
                feature_df['skewness'] = returns.rolling(20, min_periods=10).skew()
            
            elif feature == RegimeFeature.KURTOSIS:
                if 'returns' not in feature_df.columns:
                    if 'close' in market_data.columns:
                        returns = market_data['close'].pct_change()
                    elif 'price' in market_data.columns:
                        returns = market_data['price'].pct_change()
                    else:
                        continue
                else:
                    returns = feature_df['returns']
                
                # Rolling kurtosis
                feature_df['kurtosis'] = returns.rolling(20, min_periods=10).kurt()
        
        # Drop NaN values
        feature_df = feature_df.dropna()
        
        return feature_df
    
    def fit(
        self,
        market_data: pd.DataFrame,
        features: List[RegimeFeature] = None
    ) -> 'HMMRegimeDetector':
        """
        Fit HMM regime detection model
        """
        # Prepare features
        feature_df = self.prepare_features(market_data, features)
        
        if len(feature_df) < 50:
            raise ValueError("Insufficient data for regime detection")
        
        # Scale features
        scaled_features = self.scaler.fit_transform(feature_df.values)
        
        # Fit HMM model
        try:
            self.model = hmm.GaussianHMM(
                n_components=self.n_regimes,
                covariance_type=self.covariance_type,
                n_iter=self.n_iter,
                random_state=self.random_state
            )
            
            self.model.fit(scaled_features)
            
            # Get regime predictions
            regime_sequence = self.model.predict(scaled_features)
            
            # Get transition matrix
            self.transition_matrix = self.model.transmat_
            
            # Characterize regimes based on feature means
            self._characterize_regimes(feature_df, regime_sequence)
            
            self.is_fitted = True
            
        except Exception as e:
            logger.error(f"HMM fitting failed: {e}")
            # Fallback to K-means clustering
            self._fit_kmeans_fallback(scaled_features, feature_df)
        
        return self
    
    def _fit_kmeans_fallback(self, scaled_features: np.ndarray, feature_df: pd.DataFrame):
        """Fallback to K-means if HMM fails"""
        try:
            kmeans = KMeans(
                n_clusters=self.n_regimes,
                random_state=self.random_state,
                n_init=10
            )
            
            regime_sequence = kmeans.fit_predict(scaled_features)
            
            # Create simple transition matrix
            self.transition_matrix = np.ones((self.n_regimes, self.n_regimes)) / self.n_regimes
            
            # Mock HMM model for prediction
            class MockHMM:
                def __init__(self, labels):
                    self.labels = labels
                
                def predict(self, X):
                    return self.labels[:len(X)]
            
            self.model = MockHMM(regime_sequence)
            self._characterize_regimes(feature_df, regime_sequence)
            
            self.is_fitted = True
            logger.warning("Used K-means fallback for regime detection")
            
        except Exception as e:
            logger.error(f"K-means fallback also failed: {e}")
            raise
    
    def _characterize_regimes(self, feature_df: pd.DataFrame, regime_sequence: np.ndarray):
        """Characterize regimes based on feature statistics"""
        self.regime_labels = {}
        
        for regime_id in range(self.n_regimes):
            regime_mask = regime_sequence == regime_id
            regime_data = feature_df[regime_mask]
            
            if len(regime_data) == 0:
                continue
            
            # Calculate regime characteristics
            characteristics = {}
            for col in regime_data.columns:
                characteristics[f"{col}_mean"] = float(regime_data[col].mean())
                characteristics[f"{col}_std"] = float(regime_data[col].std())
            
            # Classify regime based on characteristics
            regime_label = self._classify_regime(characteristics)
            self.regime_labels[regime_id] = {
                'label': regime_label,
                'characteristics': characteristics,
                'frequency': float(np.sum(regime_mask) / len(regime_sequence))
            }
    
    def _classify_regime(self, characteristics: Dict[str, float]) -> MarketRegime:
        """Classify regime based on characteristics"""
        try:
            returns_mean = characteristics.get('returns_mean', 0)
            volatility_mean = characteristics.get('volatility_mean', 0)
            
            # Simple classification logic
            if returns_mean > 0.001:  # Positive returns
                if volatility_mean > 0.02:  # High volatility
                    return MarketRegime.BULL_HIGH_VOL
                else:
                    return MarketRegime.BULL_LOW_VOL
            elif returns_mean < -0.001:  # Negative returns
                if volatility_mean > 0.02:
                    return MarketRegime.BEAR_HIGH_VOL
                else:
                    return MarketRegime.BEAR_LOW_VOL
            else:  # Neutral returns
                if volatility_mean > 0.02:
                    return MarketRegime.SIDEWAYS_HIGH_VOL
                else:
                    return MarketRegime.SIDEWAYS_LOW_VOL
        
        except Exception:
            return MarketRegime.SIDEWAYS_LOW_VOL
    
    def predict_regimes(
        self,
        market_data: pd.DataFrame,
        features: List[RegimeFeature] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Predict regimes for new market data
        
        Returns:
            regime_sequence: Array of regime predictions
            regime_probabilities: Array of regime probability distributions
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction")
        
        # Prepare features
        feature_df = self.prepare_features(market_data, features)
        
        if len(feature_df) == 0:
            raise ValueError("No valid features for prediction")
        
        # Scale features
        scaled_features = self.scaler.transform(feature_df.values)
        
        # Predict regimes
        if hasattr(self.model, 'predict_proba'):
            regime_probabilities = self.model.predict_proba(scaled_features)
            regime_sequence = np.argmax(regime_probabilities, axis=1)
        else:
            regime_sequence = self.model.predict(scaled_features)
            # Create uniform probabilities for fallback
            regime_probabilities = np.ones((len(regime_sequence), self.n_regimes)) / self.n_regimes
        
        return regime_sequence, regime_probabilities
    
    def get_regime_transitions(
        self,
        market_data: pd.DataFrame,
        features: List[RegimeFeature] = None
    ) -> List[RegimeTransition]:
        """
        Analyze regime transitions in the data
        """
        regime_sequence, regime_probabilities = self.predict_regimes(market_data, features)
        
        transitions = []
        current_regime = regime_sequence[0]
        regime_start = 0
        
        for i, regime in enumerate(regime_sequence[1:], 1):
            if regime != current_regime:
                # Regime transition detected
                from_regime_label = self.regime_labels.get(current_regime, {}).get('label', MarketRegime.SIDEWAYS_LOW_VOL)
                to_regime_label = self.regime_labels.get(regime, {}).get('label', MarketRegime.SIDEWAYS_LOW_VOL)
                
                transition_prob = float(regime_probabilities[i, regime]) if len(regime_probabilities) > i else 0.5
                
                # Get market context at transition
                context_data = market_data.iloc[i-5:i+5] if len(market_data) > i+5 else market_data.iloc[max(0, i-5):i+1]
                market_context = self._extract_market_context(context_data)
                
                transitions.append(RegimeTransition(
                    from_regime=from_regime_label,
                    to_regime=to_regime_label,
                    transition_date=market_data.index[i] if hasattr(market_data.index[i], 'date') else datetime.now(),
                    transition_probability=transition_prob,
                    duration_days=i - regime_start,
                    market_context=market_context
                ))
                
                current_regime = regime
                regime_start = i
        
        return transitions
    
    def _extract_market_context(self, market_data: pd.DataFrame) -> Dict[str, float]:
        """Extract market context around regime transitions"""
        context = {}
        
        try:
            if 'close' in market_data.columns:
                price = market_data['close']
            elif 'price' in market_data.columns:
                price = market_data['price']
            else:
                return context
            
            if len(price) > 1:
                context['price_change'] = float((price.iloc[-1] - price.iloc[0]) / price.iloc[0])
                context['volatility'] = float(price.pct_change().std())
            
            if 'volume' in market_data.columns and len(market_data['volume']) > 1:
                context['avg_volume'] = float(market_data['volume'].mean())
            
        except Exception as e:
            logger.warning(f"Context extraction failed: {e}")
        
        return context


class RegimeAnalyzer:
    """
    Comprehensive market regime analysis and regime-based correlation analysis
    """
    
    def __init__(self, n_regimes: int = 4):
        self.n_regimes = n_regimes
        self.regime_detector = HMMRegimeDetector(n_regimes=n_regimes)
        self.regime_correlations: Dict[MarketRegime, RegimeCorrelation] = {}
    
    def analyze_regime_correlations(
        self,
        market_data: pd.DataFrame,
        strategy_returns: Dict[str, pd.Series],
        features: List[RegimeFeature] = None
    ) -> Dict[MarketRegime, RegimeCorrelation]:
        """
        Analyze correlations within different market regimes
        """
        # Fit regime detection model
        self.regime_detector.fit(market_data, features)
        
        # Predict regimes
        regime_sequence, regime_probabilities = self.regime_detector.predict_regimes(market_data, features)
        
        # Align regime predictions with strategy returns
        feature_df = self.regime_detector.prepare_features(market_data, features)
        
        # Create aligned dataset
        aligned_returns = pd.DataFrame(strategy_returns)
        aligned_returns = aligned_returns.reindex(feature_df.index).dropna()
        
        if len(aligned_returns) != len(regime_sequence):
            # Truncate to minimum length
            min_len = min(len(aligned_returns), len(regime_sequence))
            aligned_returns = aligned_returns.iloc[:min_len]
            regime_sequence = regime_sequence[:min_len]
            regime_probabilities = regime_probabilities[:min_len]
        
        # Analyze correlations by regime
        regime_correlations = {}
        
        for regime_id in range(self.n_regimes):
            regime_mask = regime_sequence == regime_id
            
            if np.sum(regime_mask) < 10:  # Insufficient data for this regime
                continue
            
            regime_returns = aligned_returns[regime_mask]
            regime_prob = float(np.mean(regime_probabilities[regime_mask, regime_id]))
            
            if len(regime_returns) < 10:
                continue
            
            # Calculate correlation matrix for this regime
            regime_corr_matrix = regime_returns.corr()
            
            # Calculate average correlations with each strategy
            strategy_correlations = {}
            strategies = list(regime_returns.columns)
            
            for strategy in strategies:
                other_strategies = [s for s in strategies if s != strategy]
                if other_strategies:
                    avg_corr = regime_corr_matrix[strategy][other_strategies].mean()
                    strategy_correlations[strategy] = float(avg_corr)
            
            # Get regime label
            regime_label = self.regime_detector.regime_labels.get(
                regime_id, {}
            ).get('label', MarketRegime.SIDEWAYS_LOW_VOL)
            
            # Create regime correlation object
            regime_correlation = RegimeCorrelation(
                regime=regime_label,
                strategy_correlations=strategy_correlations,
                correlation_matrix=regime_corr_matrix,
                regime_probability=regime_prob,
                sample_size=int(np.sum(regime_mask)),
                start_date=aligned_returns.index[regime_mask][0],
                end_date=aligned_returns.index[regime_mask][-1],
                regime_characteristics=self.regime_detector.regime_labels.get(regime_id, {}).get('characteristics', {})
            )
            
            regime_correlations[regime_label] = regime_correlation
        
        self.regime_correlations = regime_correlations
        return regime_correlations
    
    def compare_regime_correlations(
        self,
        regime_correlations: Dict[MarketRegime, RegimeCorrelation] = None
    ) -> Dict[str, Dict]:
        """
        Compare correlations across different market regimes
        """
        if regime_correlations is None:
            regime_correlations = self.regime_correlations
        
        if not regime_correlations:
            raise ValueError("No regime correlations available for comparison")
        
        # Extract all strategies
        all_strategies = set()
        for regime_corr in regime_correlations.values():
            all_strategies.update(regime_corr.strategy_correlations.keys())
        
        all_strategies = list(all_strategies)
        
        # Compare correlations across regimes
        regime_comparison = {}
        
        for strategy in all_strategies:
            strategy_regime_correlations = {}
            
            for regime, regime_corr in regime_correlations.items():
                if strategy in regime_corr.strategy_correlations:
                    strategy_regime_correlations[regime.value] = regime_corr.strategy_correlations[strategy]
            
            if len(strategy_regime_correlations) > 1:
                correlations_list = list(strategy_regime_correlations.values())
                regime_comparison[strategy] = {
                    'regime_correlations': strategy_regime_correlations,
                    'correlation_range': max(correlations_list) - min(correlations_list),
                    'correlation_volatility': float(np.std(correlations_list)),
                    'most_correlated_regime': max(strategy_regime_correlations, key=strategy_regime_correlations.get),
                    'least_correlated_regime': min(strategy_regime_correlations, key=strategy_regime_correlations.get)
                }
        
        return regime_comparison
    
    def predict_regime_transitions(
        self,
        current_market_data: pd.DataFrame,
        horizon_days: int = 30,
        features: List[RegimeFeature] = None
    ) -> Dict[str, Union[MarketRegime, float, Dict]]:
        """
        Predict potential regime transitions
        """
        if not self.regime_detector.is_fitted:
            raise ValueError("Regime detector must be fitted first")
        
        # Get current regime
        current_regime_seq, current_probs = self.regime_detector.predict_regimes(
            current_market_data.tail(1), features
        )
        
        current_regime_id = current_regime_seq[-1]
        current_regime_label = self.regime_detector.regime_labels.get(
            current_regime_id, {}
        ).get('label', MarketRegime.SIDEWAYS_LOW_VOL)
        
        # Use transition matrix to predict future regimes
        transition_matrix = self.regime_detector.transition_matrix
        
        if transition_matrix is not None:
            # Calculate future regime probabilities
            current_state = np.zeros(self.n_regimes)
            current_state[current_regime_id] = 1.0
            
            future_probs = {}
            state = current_state.copy()
            
            for day in [1, 7, 14, 30]:
                if day <= horizon_days:
                    state = np.dot(state, transition_matrix)
                    future_regime_id = np.argmax(state)
                    future_regime_label = self.regime_detector.regime_labels.get(
                        future_regime_id, {}
                    ).get('label', MarketRegime.SIDEWAYS_LOW_VOL)
                    
                    future_probs[f'day_{day}'] = {
                        'most_likely_regime': future_regime_label.value,
                        'probability': float(state[future_regime_id]),
                        'regime_probabilities': {
                            self.regime_detector.regime_labels.get(i, {}).get('label', MarketRegime.SIDEWAYS_LOW_VOL).value: float(prob)
                            for i, prob in enumerate(state)
                            if i in self.regime_detector.regime_labels
                        }
                    }
        else:
            future_probs = {}
        
        return {
            'current_regime': current_regime_label.value,
            'current_probability': float(current_probs[-1, current_regime_id]),
            'transition_predictions': future_probs
        }
    
    def generate_regime_report(
        self,
        market_data: pd.DataFrame,
        strategy_returns: Dict[str, pd.Series],
        features: List[RegimeFeature] = None
    ) -> Dict[str, Union[str, Dict, List]]:
        """
        Generate comprehensive regime analysis report
        """
        # Perform regime analysis
        regime_correlations = self.analyze_regime_correlations(market_data, strategy_returns, features)
        
        # Get regime transitions
        transitions = self.regime_detector.get_regime_transitions(market_data, features)
        
        # Compare regime correlations
        regime_comparison = self.compare_regime_correlations(regime_correlations)
        
        # Predict future regimes
        try:
            transition_predictions = self.predict_regime_transitions(market_data, features=features)
        except Exception as e:
            logger.warning(f"Regime prediction failed: {e}")
            transition_predictions = {}
        
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'analysis_summary': {
                'total_regimes_detected': len(regime_correlations),
                'total_transitions': len(transitions),
                'analysis_period': {
                    'start': market_data.index[0].isoformat() if hasattr(market_data.index[0], 'isoformat') else str(market_data.index[0]),
                    'end': market_data.index[-1].isoformat() if hasattr(market_data.index[-1], 'isoformat') else str(market_data.index[-1])
                }
            },
            'regime_correlations': {
                regime.value: correlation.to_dict() 
                for regime, correlation in regime_correlations.items()
            },
            'regime_transitions': [transition.to_dict() for transition in transitions],
            'regime_comparison': regime_comparison,
            'transition_predictions': transition_predictions,
            'regime_statistics': {
                regime.value: {
                    'frequency': self.regime_detector.regime_labels.get(
                        list(self.regime_detector.regime_labels.keys())[list(regime_correlations.keys()).index(regime)]
                    ).get('frequency', 0.0),
                    'average_correlation': np.mean(list(correlation.strategy_correlations.values())) if correlation.strategy_correlations else 0.0
                }
                for regime, correlation in regime_correlations.items()
            }
        }
        
        return report