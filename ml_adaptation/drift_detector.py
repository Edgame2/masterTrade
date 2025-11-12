"""
Concept Drift Detection for Trading Models

This module implements drift detection algorithms to monitor model performance
and feature distributions over time. When drift is detected, it triggers
retraining alerts.

Algorithms:
- Page-Hinkley Test: Detects changes in sequential data
- ADWIN: Adaptive Windowing for drift detection
- Statistical tests: KS test, Chi-square test for distribution changes
"""

import asyncio
import json
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import structlog

try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

logger = structlog.get_logger()


class PageHinkleyTest:
    """
    Page-Hinkley test for detecting concept drift
    
    Monitors a data stream and detects when statistical properties change.
    Useful for detecting performance degradation in trading models.
    """
    
    def __init__(
        self,
        delta: float = 0.005,
        threshold: float = 50.0,
        alpha: float = 0.9999
    ):
        """
        Initialize Page-Hinkley test
        
        Args:
            delta: Magnitude of changes to detect (smaller = more sensitive)
            threshold: Detection threshold (higher = less sensitive)
            alpha: Forgetting factor for cumulative sum
        """
        self.delta = delta
        self.threshold = threshold
        self.alpha = alpha
        
        self.sum = 0.0
        self.min_sum = 0.0
        self.n_samples = 0
        self.mean = 0.0
        
        self.drift_detected = False
        self.drift_point = None
    
    def add_element(self, value: float) -> bool:
        """
        Add new value and check for drift
        
        Args:
            value: New data point (e.g., prediction error, accuracy)
            
        Returns:
            True if drift detected
        """
        self.n_samples += 1
        
        # Update running mean
        self.mean = self.alpha * self.mean + (1 - self.alpha) * value
        
        # Update cumulative sum
        self.sum += value - self.mean - self.delta
        
        # Update minimum
        self.min_sum = min(self.min_sum, self.sum)
        
        # Check for drift
        if self.sum - self.min_sum > self.threshold:
            self.drift_detected = True
            self.drift_point = self.n_samples
            logger.warning(
                "page_hinkley_drift_detected",
                n_samples=self.n_samples,
                sum_diff=self.sum - self.min_sum,
                threshold=self.threshold
            )
            return True
        
        return False
    
    def reset(self):
        """Reset detector state"""
        self.sum = 0.0
        self.min_sum = 0.0
        self.n_samples = 0
        self.mean = 0.0
        self.drift_detected = False
        self.drift_point = None


class ADWIN:
    """
    Adaptive Windowing (ADWIN) drift detector
    
    Automatically adjusts window size based on data and detects changes
    in data distribution.
    """
    
    def __init__(self, delta: float = 0.002):
        """
        Initialize ADWIN
        
        Args:
            delta: Confidence parameter (smaller = more sensitive)
        """
        self.delta = delta
        self.window = deque()
        self.total = 0.0
        self.variance = 0.0
        self.width = 0
        
        self.drift_detected = False
        self.n_detections = 0
    
    def add_element(self, value: float) -> bool:
        """
        Add element and check for drift
        
        Args:
            value: New data point
            
        Returns:
            True if drift detected
        """
        # Add to window
        self.window.append(value)
        self.width += 1
        self.total += value
        
        # Update variance
        if self.width > 1:
            mean = self.total / self.width
            self.variance = sum((x - mean) ** 2 for x in self.window) / self.width
        
        # Check for drift by comparing subwindows
        drift = self._detect_change()
        
        if drift:
            self.drift_detected = True
            self.n_detections += 1
            logger.warning(
                "adwin_drift_detected",
                window_size=self.width,
                n_detections=self.n_detections
            )
            
            # Compress window
            self._compress_window()
        
        return drift
    
    def _detect_change(self) -> bool:
        """Check if change detected in window"""
        if self.width < 2:
            return False
        
        # Split window and compare means
        n = self.width
        for i in range(1, n):
            w0 = list(self.window)[:i]
            w1 = list(self.window)[i:]
            
            n0, n1 = len(w0), len(w1)
            mean0 = sum(w0) / n0
            mean1 = sum(w1) / n1
            
            # Compute bound
            m = 1.0 / (1.0 / n0 + 1.0 / n1)
            epsilon = np.sqrt(2.0 * self.variance * np.log(2.0 / self.delta) / m)
            
            # Check if difference exceeds bound
            if abs(mean0 - mean1) > epsilon:
                return True
        
        return False
    
    def _compress_window(self):
        """Remove old elements after drift detection"""
        # Remove first half of window
        n_remove = self.width // 2
        for _ in range(n_remove):
            value = self.window.popleft()
            self.total -= value
            self.width -= 1
    
    def reset(self):
        """Reset detector"""
        self.window.clear()
        self.total = 0.0
        self.variance = 0.0
        self.width = 0
        self.drift_detected = False
        self.n_detections = 0


class DriftDetector:
    """
    Comprehensive drift detection system
    
    Monitors model performance and feature distributions to detect concept drift.
    Triggers retraining alerts when drift is detected.
    """
    
    def __init__(
        self,
        database_manager=None,
        performance_threshold: float = 0.1,
        distribution_threshold: float = 0.05,
        min_samples: int = 100
    ):
        """
        Initialize drift detector
        
        Args:
            database_manager: Database manager for logging
            performance_threshold: Min accuracy drop to trigger alert (0.1 = 10%)
            distribution_threshold: P-value threshold for distribution tests
            min_samples: Minimum samples before checking drift
        """
        self.database_manager = database_manager
        self.performance_threshold = performance_threshold
        self.distribution_threshold = distribution_threshold
        self.min_samples = min_samples
        
        # Performance monitoring
        self.ph_accuracy = PageHinkleyTest(delta=0.005, threshold=50.0)
        self.adwin_accuracy = ADWIN(delta=0.002)
        
        # Feature distribution monitoring
        self.reference_features: Dict[str, np.ndarray] = {}
        self.current_features: Dict[str, List[float]] = {}
        
        # Alert tracking
        self.alerts = []
        self.last_alert_time = None
        self.alert_cooldown = timedelta(hours=1)  # Min time between alerts
        
        logger.info(
            "drift_detector_initialized",
            performance_threshold=performance_threshold,
            distribution_threshold=distribution_threshold
        )
    
    async def update_performance(
        self,
        accuracy: float,
        timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Update performance metrics and check for drift
        
        Args:
            accuracy: Current model accuracy (0-1)
            timestamp: Time of measurement
            
        Returns:
            Dict with drift detection results
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        # Check both detectors
        ph_drift = self.ph_accuracy.add_element(accuracy)
        adwin_drift = self.adwin_accuracy.add_element(accuracy)
        
        drift_detected = ph_drift or adwin_drift
        
        result = {
            'accuracy': accuracy,
            'timestamp': timestamp.isoformat(),
            'ph_drift': ph_drift,
            'adwin_drift': adwin_drift,
            'drift_detected': drift_detected
        }
        
        # Create alert if drift detected
        if drift_detected:
            await self._create_alert(
                alert_type='performance_drift',
                severity='high',
                message=f"Model performance drift detected. Accuracy: {accuracy:.4f}",
                details=result
            )
        
        # Store in database
        if self.database_manager:
            await self._log_performance(result)
        
        return result
    
    async def update_feature_distribution(
        self,
        feature_name: str,
        value: float
    ) -> Dict[str, Any]:
        """
        Update feature distribution and check for drift
        
        Args:
            feature_name: Name of feature
            value: Feature value
            
        Returns:
            Dict with drift results
        """
        # Add to current distribution
        if feature_name not in self.current_features:
            self.current_features[feature_name] = []
        
        self.current_features[feature_name].append(value)
        
        # Check drift if enough samples
        if len(self.current_features[feature_name]) >= self.min_samples:
            drift_detected = await self._check_distribution_drift(feature_name)
            
            if drift_detected:
                await self._create_alert(
                    alert_type='distribution_drift',
                    severity='medium',
                    message=f"Feature distribution drift detected: {feature_name}",
                    details={
                        'feature_name': feature_name,
                        'n_samples': len(self.current_features[feature_name])
                    }
                )
                
                return {
                    'feature_name': feature_name,
                    'drift_detected': True,
                    'n_samples': len(self.current_features[feature_name])
                }
        
        return {
            'feature_name': feature_name,
            'drift_detected': False,
            'n_samples': len(self.current_features.get(feature_name, []))
        }
    
    async def set_reference_distribution(
        self,
        feature_name: str,
        values: np.ndarray
    ):
        """
        Set reference distribution for a feature
        
        Args:
            feature_name: Feature name
            values: Reference values from training data
        """
        self.reference_features[feature_name] = values
        logger.info(
            "reference_distribution_set",
            feature_name=feature_name,
            n_samples=len(values)
        )
    
    async def _check_distribution_drift(
        self,
        feature_name: str
    ) -> bool:
        """
        Check if feature distribution has drifted using statistical tests
        
        Args:
            feature_name: Feature to check
            
        Returns:
            True if drift detected
        """
        if not SCIPY_AVAILABLE:
            logger.warning("scipy_not_available_for_distribution_tests")
            return False
        
        if feature_name not in self.reference_features:
            logger.warning(
                "no_reference_distribution",
                feature_name=feature_name
            )
            return False
        
        reference = self.reference_features[feature_name]
        current = np.array(self.current_features[feature_name])
        
        # Kolmogorov-Smirnov test
        ks_statistic, ks_pvalue = stats.ks_2samp(reference, current)
        
        # Check if distributions are significantly different
        drift_detected = ks_pvalue < self.distribution_threshold
        
        if drift_detected:
            logger.warning(
                "distribution_drift_detected",
                feature_name=feature_name,
                ks_statistic=ks_statistic,
                ks_pvalue=ks_pvalue,
                threshold=self.distribution_threshold
            )
        
        return drift_detected
    
    async def check_batch_drift(
        self,
        X_reference: np.ndarray,
        X_current: np.ndarray,
        feature_names: List[str]
    ) -> Dict[str, Any]:
        """
        Check drift across all features in batch
        
        Args:
            X_reference: Reference feature matrix
            X_current: Current feature matrix
            feature_names: List of feature names
            
        Returns:
            Dict with drift results per feature
        """
        if not SCIPY_AVAILABLE:
            raise ImportError("scipy required for batch drift detection")
        
        results = {
            'n_features': len(feature_names),
            'n_drifted': 0,
            'drifted_features': [],
            'feature_results': []
        }
        
        for i, name in enumerate(feature_names):
            ref_values = X_reference[:, i]
            cur_values = X_current[:, i]
            
            # KS test
            ks_stat, ks_pval = stats.ks_2samp(ref_values, cur_values)
            
            # Chi-square test for categorical-like features
            try:
                chi2_stat, chi2_pval = stats.chisquare(
                    np.histogram(cur_values, bins=10)[0] + 1,  # +1 to avoid zeros
                    np.histogram(ref_values, bins=10)[0] + 1
                )
            except:
                chi2_stat, chi2_pval = None, None
            
            drift = ks_pval < self.distribution_threshold
            
            feature_result = {
                'feature_name': name,
                'drift_detected': drift,
                'ks_statistic': float(ks_stat),
                'ks_pvalue': float(ks_pval),
                'chi2_statistic': float(chi2_stat) if chi2_stat is not None else None,
                'chi2_pvalue': float(chi2_pval) if chi2_pval is not None else None
            }
            
            results['feature_results'].append(feature_result)
            
            if drift:
                results['n_drifted'] += 1
                results['drifted_features'].append(name)
        
        # Create alert if significant drift
        drift_ratio = results['n_drifted'] / results['n_features']
        if drift_ratio > 0.2:  # >20% of features drifted
            await self._create_alert(
                alert_type='batch_distribution_drift',
                severity='high',
                message=f"Significant feature drift detected: {results['n_drifted']}/{results['n_features']} features",
                details=results
            )
        
        logger.info(
            "batch_drift_check_completed",
            n_features=results['n_features'],
            n_drifted=results['n_drifted'],
            drift_ratio=drift_ratio
        )
        
        return results
    
    async def _create_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        details: Dict[str, Any]
    ):
        """Create drift alert"""
        now = datetime.now(timezone.utc)
        
        # Check cooldown
        if self.last_alert_time:
            time_since_last = now - self.last_alert_time
            if time_since_last < self.alert_cooldown:
                logger.debug(
                    "alert_suppressed_cooldown",
                    time_since_last=time_since_last.total_seconds()
                )
                return
        
        alert = {
            'type': alert_type,
            'severity': severity,
            'message': message,
            'details': details,
            'timestamp': now.isoformat(),
            'action_required': 'model_retraining'
        }
        
        self.alerts.append(alert)
        self.last_alert_time = now
        
        # Store in database
        if self.database_manager:
            await self._log_alert(alert)
        
        logger.warning(
            "drift_alert_created",
            type=alert_type,
            severity=severity,
            message=message
        )
    
    def get_recent_alerts(
        self,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get alerts from last N hours"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        recent = [
            alert for alert in self.alerts
            if datetime.fromisoformat(alert['timestamp']) > cutoff
        ]
        
        return recent
    
    def reset(self):
        """Reset all detectors"""
        self.ph_accuracy.reset()
        self.adwin_accuracy.reset()
        self.current_features.clear()
        self.alerts.clear()
        self.last_alert_time = None
        
        logger.info("drift_detector_reset")
    
    async def _log_performance(self, result: Dict[str, Any]):
        """Log performance metrics to database"""
        try:
            query = """
                INSERT INTO drift_performance_log (
                    accuracy, ph_drift, adwin_drift, drift_detected, created_at
                )
                VALUES ($1, $2, $3, $4, $5)
            """
            
            await self.database_manager.execute(
                query,
                result['accuracy'],
                result['ph_drift'],
                result['adwin_drift'],
                result['drift_detected'],
                datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error("failed_to_log_performance", error=str(e))
    
    async def _log_alert(self, alert: Dict[str, Any]):
        """Log alert to database"""
        try:
            query = """
                INSERT INTO drift_alerts (
                    alert_type, severity, message, details, created_at
                )
                VALUES ($1, $2, $3, $4, $5)
            """
            
            await self.database_manager.execute(
                query,
                alert['type'],
                alert['severity'],
                alert['message'],
                json.dumps(alert['details']),
                datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error("failed_to_log_alert", error=str(e))


async def create_drift_tables(database_manager):
    """Create database tables for drift monitoring"""
    create_tables_query = """
        CREATE TABLE IF NOT EXISTS drift_performance_log (
            id BIGSERIAL PRIMARY KEY,
            accuracy NUMERIC(10, 6),
            ph_drift BOOLEAN,
            adwin_drift BOOLEAN,
            drift_detected BOOLEAN,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_drift_performance_created_at
            ON drift_performance_log(created_at DESC);
        
        CREATE TABLE IF NOT EXISTS drift_alerts (
            id BIGSERIAL PRIMARY KEY,
            alert_type VARCHAR(50),
            severity VARCHAR(20),
            message TEXT,
            details JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_drift_alerts_created_at
            ON drift_alerts(created_at DESC);
        
        CREATE INDEX IF NOT EXISTS idx_drift_alerts_type
            ON drift_alerts(alert_type);
    """
    
    try:
        await database_manager.execute(create_tables_query)
        logger.info("drift_monitoring_tables_created")
    except Exception as e:
        logger.error("failed_to_create_drift_tables", error=str(e))
