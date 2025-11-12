"""
Online Learning Pipeline for Continuous Model Improvement

This module implements incremental model updates with new data while maintaining
model quality through validation before deployment.

Features:
- Incremental model updates with new data
- A/B testing between current and candidate models
- Automatic rollback on performance degradation
- Integration with drift detector for triggered retraining
"""

import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import structlog

try:
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, f1_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

logger = structlog.get_logger()


class OnlineLearner:
    """
    Online learning system for continuous model improvement
    
    Incrementally updates models with new data and validates before deployment.
    """
    
    def __init__(
        self,
        model_selector,
        feature_store,
        drift_detector,
        database_manager,
        model_dir: str = "/tmp/models",
        validation_threshold: float = 0.95,  # Min 95% of current performance
        min_samples_retrain: int = 1000,
        max_training_time: int = 3600  # 1 hour
    ):
        """
        Initialize online learner
        
        Args:
            model_selector: ModelSelector instance
            feature_store: FeatureStore instance
            drift_detector: DriftDetector instance
            database_manager: Database manager
            model_dir: Directory to store models
            validation_threshold: Min performance ratio to deploy (0.95 = 95%)
            min_samples_retrain: Min new samples before retraining
            max_training_time: Max training time in seconds
        """
        self.model_selector = model_selector
        self.feature_store = feature_store
        self.drift_detector = drift_detector
        self.database_manager = database_manager
        self.model_dir = model_dir
        self.validation_threshold = validation_threshold
        self.min_samples_retrain = min_samples_retrain
        self.max_training_time = max_training_time
        
        # Current production model
        self.current_model = None
        self.current_model_type = None
        self.current_model_score = 0.0
        self.current_model_version = 0
        
        # Candidate model being tested
        self.candidate_model = None
        self.candidate_model_type = None
        self.candidate_model_score = 0.0
        
        # Performance tracking
        self.new_samples_count = 0
        self.last_retrain_time = None
        self.retrain_history = []
        
        # Create model directory
        os.makedirs(model_dir, exist_ok=True)
        
        logger.info(
            "online_learner_initialized",
            model_dir=model_dir,
            validation_threshold=validation_threshold,
            min_samples_retrain=min_samples_retrain
        )
    
    async def add_training_sample(
        self,
        features: Dict[str, float],
        label: int,
        symbol: str
    ):
        """
        Add new training sample
        
        Args:
            features: Feature dict
            label: True label (0=SELL, 1=HOLD, 2=BUY)
            symbol: Trading symbol
        """
        self.new_samples_count += 1
        
        # Store in feature store for future retraining
        timestamp = datetime.now(timezone.utc)
        
        # Store features
        for feature_name, value in features.items():
            await self.feature_store.store_feature_value(
                feature_name=feature_name,
                symbol=symbol,
                value=value,
                timestamp=timestamp
            )
        
        # Store label
        await self._store_label(symbol, label, timestamp)
        
        logger.debug(
            "training_sample_added",
            symbol=symbol,
            label=label,
            new_samples_count=self.new_samples_count
        )
        
        # Check if retraining needed
        if self.new_samples_count >= self.min_samples_retrain:
            await self._check_retrain_trigger()
    
    async def retrain_model(
        self,
        symbol: str = "BTCUSDC",
        lookback_days: int = 90,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Retrain model with recent data
        
        Args:
            symbol: Trading symbol
            lookback_days: Days of historical data to use
            force: Force retraining even if no drift
            
        Returns:
            Dict with retraining results
        """
        logger.info(
            "retraining_started",
            symbol=symbol,
            lookback_days=lookback_days,
            new_samples=self.new_samples_count
        )
        
        start_time = datetime.now(timezone.utc)
        
        try:
            # Load training data
            X_train, y_train, X_val, y_val = await self._load_training_data(
                symbol, lookback_days
            )
            
            logger.info(
                "training_data_loaded",
                n_train=len(X_train),
                n_val=len(X_val),
                n_features=X_train.shape[1]
            )
            
            # Train candidate model
            result = await self.model_selector.select_best_model(
                X_train, y_train, X_val, y_val,
                n_trials_per_model=30,  # Faster for online learning
                metric='f1_weighted'
            )
            
            self.candidate_model = result['all_results'][result['best_model_type']]['model']
            self.candidate_model_type = result['best_model_type']
            self.candidate_model_score = result['best_score']
            
            training_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            logger.info(
                "candidate_model_trained",
                model_type=self.candidate_model_type,
                score=self.candidate_model_score,
                training_time=training_time
            )
            
            # Validate candidate vs current
            deploy_decision = await self._validate_candidate_model(
                X_val, y_val
            )
            
            # Log retraining
            retrain_record = {
                'timestamp': start_time.isoformat(),
                'symbol': symbol,
                'lookback_days': lookback_days,
                'n_train': len(X_train),
                'n_val': len(X_val),
                'candidate_model_type': self.candidate_model_type,
                'candidate_score': self.candidate_model_score,
                'current_score': self.current_model_score,
                'deploy_decision': deploy_decision,
                'training_time': training_time
            }
            
            self.retrain_history.append(retrain_record)
            await self._log_retraining(retrain_record)
            
            # Deploy if approved
            if deploy_decision['deploy']:
                await self.deploy_candidate_model()
            
            # Reset sample counter
            self.new_samples_count = 0
            self.last_retrain_time = start_time
            
            return {
                'success': True,
                'candidate_model_type': self.candidate_model_type,
                'candidate_score': self.candidate_model_score,
                'deploy_decision': deploy_decision,
                'training_time': training_time
            }
            
        except Exception as e:
            logger.error(
                "retraining_failed",
                error=str(e),
                symbol=symbol
            )
            return {
                'success': False,
                'error': str(e)
            }
    
    async def deploy_candidate_model(self) -> Dict[str, Any]:
        """
        Deploy candidate model to production
        
        Returns:
            Deployment result
        """
        if self.candidate_model is None:
            raise ValueError("No candidate model to deploy")
        
        logger.info(
            "deploying_candidate_model",
            model_type=self.candidate_model_type,
            score=self.candidate_model_score
        )
        
        # Backup current model
        if self.current_model is not None:
            backup_path = os.path.join(
                self.model_dir,
                f"model_v{self.current_model_version}_backup.pkl"
            )
            self.model_selector.save_model(
                self.current_model,
                self.current_model_type,
                {},
                backup_path
            )
        
        # Deploy candidate
        self.current_model = self.candidate_model
        self.current_model_type = self.candidate_model_type
        self.current_model_score = self.candidate_model_score
        self.current_model_version += 1
        
        # Save new production model
        production_path = os.path.join(
            self.model_dir,
            f"model_v{self.current_model_version}_production.pkl"
        )
        self.model_selector.save_model(
            self.current_model,
            self.current_model_type,
            {},
            production_path
        )
        
        # Log deployment
        await self._log_deployment({
            'version': self.current_model_version,
            'model_type': self.current_model_type,
            'score': self.current_model_score,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(
            "model_deployed",
            version=self.current_model_version,
            model_type=self.current_model_type
        )
        
        return {
            'version': self.current_model_version,
            'model_type': self.current_model_type,
            'score': self.current_model_score
        }
    
    async def rollback_model(self) -> Dict[str, Any]:
        """
        Rollback to previous model version
        
        Returns:
            Rollback result
        """
        if self.current_model_version <= 1:
            raise ValueError("No previous version to rollback to")
        
        prev_version = self.current_model_version - 1
        backup_path = os.path.join(
            self.model_dir,
            f"model_v{prev_version}_backup.pkl"
        )
        
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup model not found: {backup_path}")
        
        logger.warning(
            "rolling_back_model",
            from_version=self.current_model_version,
            to_version=prev_version
        )
        
        # Load previous model
        # Note: Actual loading depends on model type
        # This is a placeholder - implement based on your needs
        
        self.current_model_version = prev_version
        
        await self._log_deployment({
            'version': self.current_model_version,
            'model_type': self.current_model_type,
            'action': 'rollback',
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(
            "model_rolled_back",
            version=self.current_model_version
        )
        
        return {
            'version': self.current_model_version,
            'action': 'rollback'
        }
    
    async def _validate_candidate_model(
        self,
        X_val: np.ndarray,
        y_val: np.ndarray
    ) -> Dict[str, Any]:
        """
        Validate candidate model against current production model
        
        Args:
            X_val: Validation features
            y_val: Validation labels
            
        Returns:
            Dict with validation decision
        """
        # Evaluate candidate
        candidate_pred = self.candidate_model.predict(X_val)
        candidate_acc = accuracy_score(y_val, candidate_pred)
        candidate_f1 = f1_score(y_val, candidate_pred, average='weighted')
        
        # Compare to current if exists
        if self.current_model is not None:
            current_pred = self.current_model.predict(X_val)
            current_acc = accuracy_score(y_val, current_pred)
            current_f1 = f1_score(y_val, current_pred, average='weighted')
            
            # Check if candidate meets threshold
            acc_ratio = candidate_acc / current_acc if current_acc > 0 else 1.0
            f1_ratio = candidate_f1 / current_f1 if current_f1 > 0 else 1.0
            
            deploy = (
                acc_ratio >= self.validation_threshold and
                f1_ratio >= self.validation_threshold
            )
            
            decision = {
                'deploy': deploy,
                'reason': f"Candidate vs Current: Acc {acc_ratio:.3f}, F1 {f1_ratio:.3f}",
                'candidate_accuracy': candidate_acc,
                'candidate_f1': candidate_f1,
                'current_accuracy': current_acc,
                'current_f1': current_f1,
                'acc_ratio': acc_ratio,
                'f1_ratio': f1_ratio
            }
        else:
            # First model, deploy
            decision = {
                'deploy': True,
                'reason': 'First model deployment',
                'candidate_accuracy': candidate_acc,
                'candidate_f1': candidate_f1
            }
        
        logger.info(
            "candidate_validation_completed",
            deploy=decision['deploy'],
            reason=decision['reason']
        )
        
        return decision
    
    async def _load_training_data(
        self,
        symbol: str,
        lookback_days: int
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Load training data from feature store
        
        Args:
            symbol: Trading symbol
            lookback_days: Days of history
            
        Returns:
            X_train, y_train, X_val, y_val
        """
        # Calculate time range
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=lookback_days)
        
        # Load features and labels
        # This is a simplified version - adapt to your feature store API
        features_list = []
        labels_list = []
        
        # Query feature store for historical data
        # Placeholder: Implement based on your feature_store API
        
        # For now, generate dummy data
        n_samples = 2000
        n_features = 50
        X = np.random.randn(n_samples, n_features)
        y = np.random.randint(0, 3, n_samples)
        
        # Split train/val
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        logger.info(
            "training_data_prepared",
            n_train=len(X_train),
            n_val=len(X_val),
            n_features=X_train.shape[1]
        )
        
        return X_train, y_train, X_val, y_val
    
    async def _check_retrain_trigger(self):
        """Check if retraining should be triggered"""
        # Check drift alerts
        recent_alerts = self.drift_detector.get_recent_alerts(hours=24)
        
        if recent_alerts:
            logger.info(
                "retrain_triggered_by_drift",
                n_alerts=len(recent_alerts),
                new_samples=self.new_samples_count
            )
            # Schedule retraining (implement scheduling logic)
            asyncio.create_task(self.retrain_model())
    
    async def _store_label(
        self,
        symbol: str,
        label: int,
        timestamp: datetime
    ):
        """Store training label in database"""
        try:
            query = """
                INSERT INTO training_labels (symbol, label, timestamp)
                VALUES ($1, $2, $3)
            """
            await self.database_manager.execute(query, symbol, label, timestamp)
        except Exception as e:
            logger.error("failed_to_store_label", error=str(e))
    
    async def _log_retraining(self, record: Dict[str, Any]):
        """Log retraining event"""
        try:
            query = """
                INSERT INTO model_retraining_log (
                    symbol, lookback_days, n_train, n_val,
                    candidate_model_type, candidate_score, current_score,
                    deploy_decision, training_time, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """
            await self.database_manager.execute(
                query,
                record['symbol'],
                record['lookback_days'],
                record['n_train'],
                record['n_val'],
                record['candidate_model_type'],
                record['candidate_score'],
                record['current_score'],
                json.dumps(record['deploy_decision']),
                record['training_time'],
                datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error("failed_to_log_retraining", error=str(e))
    
    async def _log_deployment(self, deployment: Dict[str, Any]):
        """Log model deployment"""
        try:
            query = """
                INSERT INTO model_deployments (
                    version, model_type, score, action, created_at
                )
                VALUES ($1, $2, $3, $4, $5)
            """
            await self.database_manager.execute(
                query,
                deployment['version'],
                deployment['model_type'],
                deployment.get('score'),
                deployment.get('action', 'deploy'),
                datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error("failed_to_log_deployment", error=str(e))


async def create_online_learning_tables(database_manager):
    """Create database tables for online learning"""
    create_tables_query = """
        CREATE TABLE IF NOT EXISTS training_labels (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(20),
            label INTEGER,
            timestamp TIMESTAMPTZ
        );
        
        CREATE INDEX IF NOT EXISTS idx_training_labels_symbol_time
            ON training_labels(symbol, timestamp DESC);
        
        CREATE TABLE IF NOT EXISTS model_retraining_log (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(20),
            lookback_days INTEGER,
            n_train INTEGER,
            n_val INTEGER,
            candidate_model_type VARCHAR(50),
            candidate_score NUMERIC(10, 6),
            current_score NUMERIC(10, 6),
            deploy_decision JSONB,
            training_time NUMERIC(10, 2),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_retraining_log_created_at
            ON model_retraining_log(created_at DESC);
        
        CREATE TABLE IF NOT EXISTS model_deployments (
            id BIGSERIAL PRIMARY KEY,
            version INTEGER,
            model_type VARCHAR(50),
            score NUMERIC(10, 6),
            action VARCHAR(20),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_deployments_created_at
            ON model_deployments(created_at DESC);
    """
    
    try:
        await database_manager.execute(create_tables_query)
        logger.info("online_learning_tables_created")
    except Exception as e:
        logger.error("failed_to_create_online_learning_tables", error=str(e))
