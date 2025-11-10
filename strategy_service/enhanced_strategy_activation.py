"""
Enhanced Dynamic Strategy Activation System

Advanced strategy activation system that:
- Analyzes current market conditions and regime
- Detects regime changes in real-time
- Evaluates strategy performance in similar historical conditions
- Automatically activates/deactivates strategies based on fit
- Integrates with risk management system for regime awareness
- Uses machine learning for condition similarity matching
"""

import asyncio
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import structlog
from scipy.spatial.distance import euclidean
from sklearn.preprocessing import StandardScaler

from postgres_database import Database
from config import settings

logger = structlog.get_logger()


class MarketRegime(Enum):
    """Market regime types"""
    BULL_TRENDING = "bull_trending"
    BEAR_TRENDING = "bear_trending"
    SIDEWAYS_RANGE = "sideways_range"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CRISIS = "crisis"
    RECOVERY = "recovery"


class StrategyType(Enum):
    """Strategy type classification"""
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    TREND_FOLLOWING = "trend_following"
    SCALPING = "scalping"
    SWING = "swing"
    ARBITRAGE = "arbitrage"
    HYBRID = "hybrid"


@dataclass
class MarketConditions:
    """Current market conditions snapshot"""
    timestamp: datetime
    regime: MarketRegime
    volatility: float
    trend_strength: float
    volume_trend: float
    sentiment_score: float
    fear_greed_index: int
    correlation_to_btc: float
    liquidity_score: float
    macro_score: float
    features_vector: np.ndarray
    
@dataclass
class StrategyPerformance:
    """Strategy performance in specific conditions"""
    strategy_id: str
    condition_similarity: float
    historical_sharpe: float
    historical_return: float
    historical_win_rate: float
    historical_max_drawdown: float
    trade_count: int
    avg_trade_duration: float
    profit_factor: float
    consistency_score: float


@dataclass
class ActivationDecision:
    """Strategy activation/deactivation decision"""
    strategy_id: str
    strategy_name: str
    action: str  # 'activate', 'deactivate', 'keep'
    current_status: str
    new_status: str
    confidence: float
    reasoning: List[str]
    performance_in_current_regime: StrategyPerformance
    expected_sharpe: float
    expected_return: float
    risk_score: float
    sentiment_alignment_score: float
    sentiment_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegimeChange:
    """Detected regime change event"""
    timestamp: datetime
    old_regime: MarketRegime
    new_regime: MarketRegime
    confidence: float
    trigger_factors: List[str]
    affected_strategies: List[str]


class EnhancedStrategyActivationSystem:
    """
    Enhanced Dynamic Strategy Activation System
    
    Key Features:
    - Real-time market regime detection
    - Historical performance analysis in similar conditions
    - Automatic strategy activation/deactivation
    - Machine learning-based condition matching
    - Integration with risk management system
    - Regime change detection and response
    """
    
    def __init__(self, database: Database):
        self.database = database
        self.current_regime: Optional[MarketRegime] = None
        self.current_conditions: Optional[MarketConditions] = None
        self.active_strategies: Set[str] = set()
        self.historical_conditions: List[MarketConditions] = []
        self.scaler = StandardScaler()
        
        # Configuration
        self.max_active_strategies = settings.MAX_ACTIVE_STRATEGIES
        self.min_condition_similarity = 0.7
        self.min_historical_trades = 20
        self.regime_change_threshold = 0.15
        self.activation_cooldown_hours = 2
        self.sentiment_window_hours = 24
        self.sentiment_min_alignment = 0.45
        self.sentiment_weight = 0.15
        
        # Cache
        self._last_regime_check: Optional[datetime] = None
        self._last_activation_check: Optional[datetime] = None
        self._strategy_performance_cache: Dict[str, Dict] = {}
        
        logger.info("Enhanced Strategy Activation System initialized")
    
    
    async def initialize(self):
        """Initialize the system"""
        try:
            # Load current active strategies
            await self._load_active_strategies()
            
            # Load historical market conditions
            await self._load_historical_conditions()
            
            # Fit scaler on historical data
            if self.historical_conditions:
                features = np.array([c.features_vector for c in self.historical_conditions])
                self.scaler.fit(features)
            
            # Detect current market regime
            await self.detect_market_regime()
            
            # Perform initial activation check
            await self.check_and_update_activations()
            
            logger.info(
                "Strategy activation system initialized",
                current_regime=self.current_regime.value if self.current_regime else None,
                active_strategies=len(self.active_strategies)
            )
            
        except Exception as e:
            logger.error(f"Error initializing activation system: {e}", exc_info=True)
            raise
    
    
    async def detect_market_regime(self) -> Tuple[MarketRegime, float]:
        """
        Detect current market regime based on multiple factors
        
        Returns:
            Tuple of (regime, confidence)
        """
        try:
            # Get market data
            conditions = await self._collect_current_conditions()
            
            # Previous regime
            old_regime = self.current_regime
            
            # Classify regime based on conditions
            regime, confidence = self._classify_regime(conditions)
            
            # Update current state
            self.current_regime = regime
            self.current_conditions = conditions
            self._last_regime_check = datetime.now(timezone.utc)
            
            # Store in database
            await self._store_regime_detection(regime, confidence, conditions)
            
            # Check for regime change
            if old_regime and old_regime != regime:
                await self._handle_regime_change(old_regime, regime, confidence)
            
            logger.info(
                f"Market regime detected: {regime.value}",
                confidence=confidence,
                volatility=conditions.volatility,
                trend_strength=conditions.trend_strength,
                sentiment=conditions.sentiment_score
            )
            
            return regime, confidence
            
        except Exception as e:
            logger.error(f"Error detecting market regime: {e}", exc_info=True)
            return MarketRegime.SIDEWAYS_RANGE, 0.5  # Safe default
    
    
    async def _collect_current_conditions(self) -> MarketConditions:
        """Collect current market conditions from various sources"""
        try:
            # Get market data (via API call to market_data_service)
            market_data = await self._fetch_market_data()
            
            # Get sentiment data
            sentiment = await self._fetch_sentiment_data()
            
            # Get macro indicators
            macro = await self._fetch_macro_indicators()
            
            # Get risk regime from risk manager
            risk_regime = await self._fetch_risk_regime()
            
            # Calculate volatility (annualized)
            volatility = market_data.get('volatility', 0.3)
            
            # Calculate trend strength (-1 to 1)
            trend_strength = self._calculate_trend_strength(market_data)
            
            # Volume trend
            volume_trend = self._calculate_volume_trend(market_data)
            
            # Sentiment score (-1 to 1)
            sentiment_score = sentiment.get('aggregated_score', 0.0)
            
            # Fear & Greed Index (0-100)
            fear_greed = sentiment.get('fear_greed_index', 50)
            
            # BTC correlation
            btc_correlation = market_data.get('btc_correlation', 0.8)
            
            # Liquidity score (0-1)
            liquidity = market_data.get('liquidity_score', 0.7)
            
            # Macro score (-1 to 1)
            macro_score = self._calculate_macro_score(macro)
            
            # Create feature vector for similarity matching
            features = np.array([
                volatility,
                trend_strength,
                volume_trend,
                sentiment_score,
                fear_greed / 100.0,
                btc_correlation,
                liquidity,
                macro_score
            ])
            
            return MarketConditions(
                timestamp=datetime.now(timezone.utc),
                regime=MarketRegime.SIDEWAYS_RANGE,  # Will be set by classification
                volatility=volatility,
                trend_strength=trend_strength,
                volume_trend=volume_trend,
                sentiment_score=sentiment_score,
                fear_greed_index=fear_greed,
                correlation_to_btc=btc_correlation,
                liquidity_score=liquidity,
                macro_score=macro_score,
                features_vector=features
            )
            
        except Exception as e:
            logger.error(f"Error collecting market conditions: {e}", exc_info=True)
            # Return safe defaults
            return MarketConditions(
                timestamp=datetime.now(timezone.utc),
                regime=MarketRegime.SIDEWAYS_RANGE,
                volatility=0.3,
                trend_strength=0.0,
                volume_trend=0.0,
                sentiment_score=0.0,
                fear_greed_index=50,
                correlation_to_btc=0.8,
                liquidity_score=0.7,
                macro_score=0.0,
                features_vector=np.zeros(8)
            )
    
    
    def _classify_regime(self, conditions: MarketConditions) -> Tuple[MarketRegime, float]:
        """
        Classify market regime based on conditions
        
        Returns:
            Tuple of (regime, confidence)
        """
        scores = defaultdict(float)
        
        # Crisis detection (highest priority)
        if conditions.fear_greed_index < 20 or conditions.volatility > 0.8:
            scores[MarketRegime.CRISIS] += 1.0
        
        # Volatility-based classification
        if conditions.volatility > 0.5:
            scores[MarketRegime.HIGH_VOLATILITY] += 0.7
        elif conditions.volatility < 0.2:
            scores[MarketRegime.LOW_VOLATILITY] += 0.7
        
        # Trend-based classification
        if conditions.trend_strength > 0.3:
            scores[MarketRegime.BULL_TRENDING] += 0.8
            if conditions.sentiment_score > 0.3:
                scores[MarketRegime.BULL_TRENDING] += 0.2
        elif conditions.trend_strength < -0.3:
            scores[MarketRegime.BEAR_TRENDING] += 0.8
            if conditions.sentiment_score < -0.3:
                scores[MarketRegime.BEAR_TRENDING] += 0.2
        else:
            scores[MarketRegime.SIDEWAYS_RANGE] += 0.6
        
        # Recovery detection
        if (conditions.fear_greed_index > 40 and 
            conditions.trend_strength > 0.2 and 
            conditions.sentiment_score > 0.0):
            scores[MarketRegime.RECOVERY] += 0.5
        
        # Adjust for volume
        if conditions.volume_trend > 0.3:
            # High volume supports trending
            if MarketRegime.BULL_TRENDING in scores:
                scores[MarketRegime.BULL_TRENDING] += 0.2
            if MarketRegime.BEAR_TRENDING in scores:
                scores[MarketRegime.BEAR_TRENDING] += 0.2
        
        # Get regime with highest score
        if not scores:
            return MarketRegime.SIDEWAYS_RANGE, 0.5
        
        best_regime = max(scores.items(), key=lambda x: x[1])
        confidence = min(1.0, best_regime[1] / 1.5)  # Normalize confidence
        
        return best_regime[0], confidence
    
    
    async def check_and_update_activations(self) -> Dict[str, List[ActivationDecision]]:
        """
        Check current strategy activations and update if needed
        
        Returns:
            Dict with 'activated', 'deactivated', and 'kept' decisions
        """
        try:
            # Check cooldown period
            if not self._should_check_activations():
                return {'activated': [], 'deactivated': [], 'kept': []}
            
            # Ensure we have current regime
            if not self.current_regime or not self.current_conditions:
                await self.detect_market_regime()
            
            # Get all available strategies
            all_strategies = await self._get_all_strategies()
            
            # Evaluate each strategy for current conditions
            decisions = []
            for strategy in all_strategies:
                decision = await self._evaluate_strategy_activation(strategy)
                decisions.append(decision)
            
            # Sort by expected performance
            decisions.sort(key=lambda x: x.expected_sharpe, reverse=True)
            
            # Select top strategies to activate
            activation_decisions = self._select_strategies_to_activate(decisions)
            
            # Apply activation changes
            results = await self._apply_activation_decisions(activation_decisions)
            
            # Update last check time
            self._last_activation_check = datetime.now(timezone.utc)
            
            # Log results
            logger.info(
                "Strategy activation check completed",
                activated=len(results['activated']),
                deactivated=len(results['deactivated']),
                kept=len(results['kept']),
                regime=self.current_regime.value
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error checking activations: {e}", exc_info=True)
            return {'activated': [], 'deactivated': [], 'kept': []}
    
    
    async def _evaluate_strategy_activation(self, strategy: Dict) -> ActivationDecision:
        """
        Evaluate whether a strategy should be activated based on current conditions
        """
        try:
            strategy_id = strategy['id']
            strategy_name = strategy.get('name', strategy_id)
            current_status = strategy.get('status', 'inactive')
            
            # Get strategy type
            strategy_type = StrategyType(strategy.get('strategy_type', 'hybrid'))
            
            # Find similar historical conditions
            similar_conditions = self._find_similar_conditions(
                self.current_conditions,
                top_k=10
            )
            
            # Evaluate performance in similar conditions
            performance = await self._evaluate_strategy_in_conditions(
                strategy_id,
                similar_conditions
            )
            
            # Check if strategy is suitable for current regime
            regime_suitability = self._check_regime_suitability(
                strategy_type,
                self.current_regime
            )
            
            # Calculate expected performance
            expected_sharpe = performance.historical_sharpe * performance.consistency_score
            expected_return = performance.historical_return * performance.consistency_score
            
            # Calculate risk score
            risk_score = self._calculate_strategy_risk_score(
                performance,
                self.current_conditions
            )

            # Calculate sentiment alignment against current market mood
            sentiment_alignment, sentiment_context = await self._calculate_sentiment_alignment(strategy)
            
            # Determine action
            reasoning = []
            confidence = 0.0
            
            if performance.trade_count < self.min_historical_trades:
                action = 'deactivate' if current_status == 'active' else 'keep'
                reasoning.append(f"Insufficient historical trades ({performance.trade_count})")
                confidence = 0.9
            elif performance.condition_similarity < self.min_condition_similarity:
                action = 'deactivate' if current_status == 'active' else 'keep'
                reasoning.append(f"Low condition similarity ({performance.condition_similarity:.2f})")
                confidence = 0.8
            elif regime_suitability < 0.5:
                action = 'deactivate' if current_status == 'active' else 'keep'
                reasoning.append(f"Strategy type not suitable for {self.current_regime.value}")
                confidence = 0.85
            elif sentiment_alignment < self.sentiment_min_alignment:
                action = 'deactivate' if current_status == 'active' else 'keep'
                reasoning.append(f"Weak sentiment alignment ({sentiment_alignment:.2f})")
                confidence = max(0.8, regime_suitability)
            elif expected_sharpe > 1.5 and risk_score < 0.6:
                action = 'activate'
                reasoning.append(f"Strong historical performance (Sharpe: {expected_sharpe:.2f})")
                reasoning.append(f"Suitable for {self.current_regime.value} regime")
                confidence = min(0.95, regime_suitability * performance.consistency_score)
            elif expected_sharpe > 1.0 and risk_score < 0.7:
                action = 'activate' if current_status != 'active' else 'keep'
                reasoning.append(f"Good historical performance (Sharpe: {expected_sharpe:.2f})")
                confidence = 0.75
            else:
                action = 'deactivate' if current_status == 'active' else 'keep'
                reasoning.append(f"Marginal performance (Sharpe: {expected_sharpe:.2f})")
                confidence = 0.7

            if sentiment_alignment >= 0.75:
                reasoning.append(f"Positive sentiment support ({sentiment_alignment:.2f})")
            elif sentiment_alignment < self.sentiment_min_alignment:
                if not any("sentiment alignment" in item.lower() for item in reasoning):
                    reasoning.append(f"Sentiment alignment below threshold ({sentiment_alignment:.2f})")
            
            # Determine new status
            if action == 'activate':
                new_status = 'active'
            elif action == 'deactivate':
                new_status = 'inactive'
            else:
                new_status = current_status
            
            return ActivationDecision(
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                action=action,
                current_status=current_status,
                new_status=new_status,
                confidence=confidence,
                reasoning=reasoning,
                performance_in_current_regime=performance,
                expected_sharpe=expected_sharpe,
                expected_return=expected_return,
                risk_score=risk_score,
                sentiment_alignment_score=sentiment_alignment,
                sentiment_context=sentiment_context
            )
            
        except Exception as e:
            logger.error(f"Error evaluating strategy {strategy.get('id')}: {e}", exc_info=True)
            return ActivationDecision(
                strategy_id=strategy.get('id', 'unknown'),
                strategy_name=strategy.get('name', 'unknown'),
                action='keep',
                current_status=strategy.get('status', 'inactive'),
                new_status=strategy.get('status', 'inactive'),
                confidence=0.0,
                reasoning=["Error evaluating strategy"],
                performance_in_current_regime=StrategyPerformance(
                    strategy_id=strategy.get('id', 'unknown'),
                    condition_similarity=0.0,
                    historical_sharpe=0.0,
                    historical_return=0.0,
                    historical_win_rate=0.0,
                    historical_max_drawdown=0.0,
                    trade_count=0,
                    avg_trade_duration=0.0,
                    profit_factor=0.0,
                    consistency_score=0.0
                ),
                expected_sharpe=0.0,
                expected_return=0.0,
                risk_score=1.0,
                sentiment_alignment_score=0.5,
                sentiment_context={'error': str(e)}
            )
    
    
    def _find_similar_conditions(
        self, 
        current: MarketConditions,
        top_k: int = 10
    ) -> List[MarketConditions]:
        """
        Find historically similar market conditions
        
        Uses Euclidean distance in normalized feature space
        """
        if not self.historical_conditions:
            return []
        
        # Normalize current conditions
        current_features = self.scaler.transform([current.features_vector])[0]
        
        # Calculate distances to all historical conditions
        distances = []
        for hist in self.historical_conditions:
            hist_features = self.scaler.transform([hist.features_vector])[0]
            dist = euclidean(current_features, hist_features)
            distances.append((dist, hist))
        
        # Sort by distance and return top_k
        distances.sort(key=lambda x: x[0])
        return [cond for _, cond in distances[:top_k]]
    
    
    async def _evaluate_strategy_in_conditions(
        self,
        strategy_id: str,
        similar_conditions: List[MarketConditions]
    ) -> StrategyPerformance:
        """
        Evaluate strategy performance in similar historical conditions
        """
        try:
            if not similar_conditions:
                return StrategyPerformance(
                    strategy_id=strategy_id,
                    condition_similarity=0.0,
                    historical_sharpe=0.0,
                    historical_return=0.0,
                    historical_win_rate=0.0,
                    historical_max_drawdown=0.0,
                    trade_count=0,
                    avg_trade_duration=0.0,
                    profit_factor=0.0,
                    consistency_score=0.0
                )
            
            # Get time periods for similar conditions
            time_periods = [(c.timestamp - timedelta(days=1), c.timestamp + timedelta(days=1)) 
                           for c in similar_conditions]
            
            # Get trades from those periods
            all_trades = []
            for start, end in time_periods:
                trades = await self.database.get_strategy_trades(
                    strategy_id=strategy_id,
                    start_date=start,
                    end_date=end
                )
                all_trades.extend(trades)
            
            if not all_trades:
                return StrategyPerformance(
                    strategy_id=strategy_id,
                    condition_similarity=0.9,
                    historical_sharpe=0.0,
                    historical_return=0.0,
                    historical_win_rate=0.0,
                    historical_max_drawdown=0.0,
                    trade_count=0,
                    avg_trade_duration=0.0,
                    profit_factor=0.0,
                    consistency_score=0.0
                )
            
            # Calculate performance metrics
            returns = [t['pnl_percent'] / 100.0 for t in all_trades]
            wins = [r for r in returns if r > 0]
            losses = [abs(r) for r in returns if r < 0]
            
            sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0
            total_return = sum(returns)
            win_rate = len(wins) / len(all_trades) if all_trades else 0
            max_dd = self._calculate_max_drawdown(returns)
            avg_duration = np.mean([t.get('duration_hours', 24) for t in all_trades])
            profit_factor = (sum(wins) / sum(losses)) if losses else 0
            
            # Calculate consistency score
            consistency = self._calculate_consistency_score(returns)
            
            # Average condition similarity
            avg_similarity = np.mean([
                1.0 - (euclidean(self.current_conditions.features_vector, c.features_vector) / 
                       np.linalg.norm(self.current_conditions.features_vector))
                for c in similar_conditions
            ])
            
            return StrategyPerformance(
                strategy_id=strategy_id,
                condition_similarity=float(avg_similarity),
                historical_sharpe=float(sharpe),
                historical_return=float(total_return),
                historical_win_rate=float(win_rate),
                historical_max_drawdown=float(max_dd),
                trade_count=len(all_trades),
                avg_trade_duration=float(avg_duration),
                profit_factor=float(profit_factor),
                consistency_score=float(consistency)
            )
            
        except Exception as e:
            logger.error(f"Error evaluating strategy performance: {e}", exc_info=True)
            return StrategyPerformance(
                strategy_id=strategy_id,
                condition_similarity=0.0,
                historical_sharpe=0.0,
                historical_return=0.0,
                historical_win_rate=0.0,
                historical_max_drawdown=0.0,
                trade_count=0,
                avg_trade_duration=0.0,
                profit_factor=0.0,
                consistency_score=0.0
            )
    
    
    def _check_regime_suitability(
        self,
        strategy_type: StrategyType,
        regime: MarketRegime
    ) -> float:
        """
        Check how suitable a strategy type is for a market regime
        
        Returns score from 0.0 to 1.0
        """
        # Strategy-regime suitability matrix
        suitability = {
            StrategyType.MOMENTUM: {
                MarketRegime.BULL_TRENDING: 0.9,
                MarketRegime.BEAR_TRENDING: 0.7,
                MarketRegime.SIDEWAYS_RANGE: 0.3,
                MarketRegime.HIGH_VOLATILITY: 0.6,
                MarketRegime.LOW_VOLATILITY: 0.5,
                MarketRegime.CRISIS: 0.2,
                MarketRegime.RECOVERY: 0.8
            },
            StrategyType.MEAN_REVERSION: {
                MarketRegime.BULL_TRENDING: 0.4,
                MarketRegime.BEAR_TRENDING: 0.4,
                MarketRegime.SIDEWAYS_RANGE: 0.9,
                MarketRegime.HIGH_VOLATILITY: 0.7,
                MarketRegime.LOW_VOLATILITY: 0.8,
                MarketRegime.CRISIS: 0.3,
                MarketRegime.RECOVERY: 0.6
            },
            StrategyType.BREAKOUT: {
                MarketRegime.BULL_TRENDING: 0.8,
                MarketRegime.BEAR_TRENDING: 0.5,
                MarketRegime.SIDEWAYS_RANGE: 0.6,
                MarketRegime.HIGH_VOLATILITY: 0.8,
                MarketRegime.LOW_VOLATILITY: 0.4,
                MarketRegime.CRISIS: 0.4,
                MarketRegime.RECOVERY: 0.9
            },
            StrategyType.TREND_FOLLOWING: {
                MarketRegime.BULL_TRENDING: 0.9,
                MarketRegime.BEAR_TRENDING: 0.8,
                MarketRegime.SIDEWAYS_RANGE: 0.2,
                MarketRegime.HIGH_VOLATILITY: 0.5,
                MarketRegime.LOW_VOLATILITY: 0.7,
                MarketRegime.CRISIS: 0.3,
                MarketRegime.RECOVERY: 0.7
            },
            StrategyType.SCALPING: {
                MarketRegime.BULL_TRENDING: 0.6,
                MarketRegime.BEAR_TRENDING: 0.6,
                MarketRegime.SIDEWAYS_RANGE: 0.7,
                MarketRegime.HIGH_VOLATILITY: 0.8,
                MarketRegime.LOW_VOLATILITY: 0.5,
                MarketRegime.CRISIS: 0.5,
                MarketRegime.RECOVERY: 0.6
            },
            StrategyType.SWING: {
                MarketRegime.BULL_TRENDING: 0.8,
                MarketRegime.BEAR_TRENDING: 0.7,
                MarketRegime.SIDEWAYS_RANGE: 0.6,
                MarketRegime.HIGH_VOLATILITY: 0.6,
                MarketRegime.LOW_VOLATILITY: 0.7,
                MarketRegime.CRISIS: 0.4,
                MarketRegime.RECOVERY: 0.8
            },
            StrategyType.ARBITRAGE: {
                MarketRegime.BULL_TRENDING: 0.6,
                MarketRegime.BEAR_TRENDING: 0.6,
                MarketRegime.SIDEWAYS_RANGE: 0.7,
                MarketRegime.HIGH_VOLATILITY: 0.9,
                MarketRegime.LOW_VOLATILITY: 0.5,
                MarketRegime.CRISIS: 0.8,
                MarketRegime.RECOVERY: 0.6
            },
            StrategyType.HYBRID: {
                MarketRegime.BULL_TRENDING: 0.7,
                MarketRegime.BEAR_TRENDING: 0.7,
                MarketRegime.SIDEWAYS_RANGE: 0.7,
                MarketRegime.HIGH_VOLATILITY: 0.7,
                MarketRegime.LOW_VOLATILITY: 0.7,
                MarketRegime.CRISIS: 0.6,
                MarketRegime.RECOVERY: 0.7
            }
        }
        
        return suitability.get(strategy_type, {}).get(regime, 0.5)
    
    
    def _select_strategies_to_activate(
        self,
        decisions: List[ActivationDecision]
    ) -> Dict[str, List[ActivationDecision]]:
        """
        Select which strategies to activate based on decisions and limits
        """
        # Filter candidates that should be activated
        activation_candidates = [d for d in decisions if d.action == 'activate']
        
        # Keep currently active strategies that shouldn't be deactivated
        keep_active = [d for d in decisions if d.action == 'keep' and d.current_status == 'active']
        
        # Strategies that should be deactivated
        deactivate_candidates = [d for d in decisions if d.action == 'deactivate']
        
        # Select top strategies up to max limit
        selected_to_activate = []
        current_active_count = len(keep_active)
        
        for candidate in activation_candidates:
            if current_active_count + len(selected_to_activate) < self.max_active_strategies:
                selected_to_activate.append(candidate)
            else:
                # Change action to 'keep' for strategies that can't be activated due to limit
                candidate.action = 'keep'
                candidate.new_status = candidate.current_status
                candidate.reasoning.append(f"Max active strategies limit reached ({self.max_active_strategies})")
        
        return {
            'activate': selected_to_activate,
            'deactivate': deactivate_candidates,
            'keep': [d for d in decisions if d.action == 'keep']
        }
    
    
    async def _apply_activation_decisions(
        self,
        decisions: Dict[str, List[ActivationDecision]]
    ) -> Dict[str, List[ActivationDecision]]:
        """Apply activation/deactivation decisions to database"""
        try:
            # Apply activations
            for decision in decisions['activate']:
                try:
                    strategy = await self.database.get_strategy(decision.strategy_id)
                    metadata = (strategy or {}).get('metadata', {}) if strategy else {}
                    metadata.update(
                        {
                            'activation_reason': '; '.join(decision.reasoning),
                            'last_activation_timestamp': datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    await self.database.update_strategy(
                        decision.strategy_id,
                        {
                            'status': 'active',
                            'is_active': True,
                            'metadata': metadata,
                        },
                    )

                    self.active_strategies.add(decision.strategy_id)
                    
                    logger.info(
                        f"Strategy activated: {decision.strategy_name}",
                        strategy_id=decision.strategy_id,
                        expected_sharpe=decision.expected_sharpe,
                        reasoning=decision.reasoning
                    )
                    
                except Exception as e:
                    logger.error(f"Error activating strategy {decision.strategy_id}: {e}")
            
            # Apply deactivations
            for decision in decisions['deactivate']:
                try:
                    strategy = await self.database.get_strategy(decision.strategy_id)
                    metadata = (strategy or {}).get('metadata', {}) if strategy else {}
                    metadata.update(
                        {
                            'deactivation_reason': '; '.join(decision.reasoning),
                            'last_deactivation_timestamp': datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    await self.database.update_strategy(
                        decision.strategy_id,
                        {
                            'status': 'inactive',
                            'is_active': False,
                            'metadata': metadata,
                        },
                    )

                    self.active_strategies.discard(decision.strategy_id)
                    
                    logger.info(
                        f"Strategy deactivated: {decision.strategy_name}",
                        strategy_id=decision.strategy_id,
                        reasoning=decision.reasoning
                    )
                    
                except Exception as e:
                    logger.error(f"Error deactivating strategy {decision.strategy_id}: {e}")
            
            # Store activation decision history
            await self._store_activation_decisions(decisions)
            
            return {
                'activated': decisions['activate'],
                'deactivated': decisions['deactivate'],
                'kept': decisions['keep']
            }
            
        except Exception as e:
            logger.error(f"Error applying activation decisions: {e}", exc_info=True)
            return {'activated': [], 'deactivated': [], 'kept': []}
    
    
    async def _handle_regime_change(
        self,
        old_regime: MarketRegime,
        new_regime: MarketRegime,
        confidence: float
    ):
        """Handle detected regime change"""
        try:
            logger.warning(
                f"Market regime change detected: {old_regime.value} → {new_regime.value}",
                confidence=confidence
            )
            
            # Create regime change event
            regime_change = RegimeChange(
                timestamp=datetime.now(timezone.utc),
                old_regime=old_regime,
                new_regime=new_regime,
                confidence=confidence,
                trigger_factors=self._identify_regime_change_factors(),
                affected_strategies=list(self.active_strategies)
            )
            
            # Store in database
            await self._store_regime_change(regime_change)
            
            # Force immediate activation check
            self._last_activation_check = None
            await self.check_and_update_activations()
            
        except Exception as e:
            logger.error(f"Error handling regime change: {e}", exc_info=True)
    
    
    # Helper methods (stubs - implement based on your infrastructure)
    
    def _should_check_activations(self) -> bool:
        """Check if cooldown period has passed"""
        if self._last_activation_check is None:
            return True
        
        elapsed = (datetime.now(timezone.utc) - self._last_activation_check).total_seconds()
        return elapsed >= (self.activation_cooldown_hours * 3600)
    
    async def _load_active_strategies(self):
        """Load currently active strategies from database"""
        # Implementation depends on your database structure
        pass
    
    async def _load_historical_conditions(self):
        """Load historical market conditions for similarity matching"""
        # Implementation depends on your data storage
        pass
    
    async def _fetch_market_data(self) -> Dict:
        """Fetch current market data from market_data_service"""
        # API call to market_data_service
        return {}
    
    async def _fetch_sentiment_data(self) -> Dict:
        """Fetch sentiment data"""
        # API call to market_data_service sentiment endpoint
        return {}
    
    async def _fetch_macro_indicators(self) -> Dict:
        """Fetch macro-economic indicators"""
        # API call to market_data_service macro endpoint
        return {}
    
    async def _fetch_risk_regime(self) -> str:
        """Fetch current risk regime from risk_manager"""
        # API call to risk_manager
        return "low_vol_bullish"
    
    def _calculate_trend_strength(self, market_data: Dict) -> float:
        """Calculate trend strength from market data"""
        # Implementation
        return 0.0
    
    def _calculate_volume_trend(self, market_data: Dict) -> float:
        """Calculate volume trend"""
        # Implementation
        return 0.0
    
    def _calculate_macro_score(self, macro: Dict) -> float:
        """Calculate macro-economic score"""
        # Implementation
        return 0.0
    
    async def _get_all_strategies(self) -> List[Dict]:
        """Get all strategies from database"""
        # Implementation
        return []
    
    def _calculate_strategy_risk_score(
        self,
        performance: StrategyPerformance,
        conditions: MarketConditions
    ) -> float:
        """Calculate risk score for strategy"""
        # Consider max drawdown, volatility, etc.
        risk = (performance.historical_max_drawdown + conditions.volatility) / 2.0
        return min(1.0, risk)

    async def _calculate_sentiment_alignment(self, strategy: Dict) -> Tuple[float, Dict[str, Any]]:
        """Derive sentiment alignment score for a strategy based on tracked symbols."""
        try:
            symbols: List[str] = []
            for entry in strategy.get('symbols') or []:
                if isinstance(entry, dict):
                    symbol_value = entry.get('symbol')
                else:
                    symbol_value = str(entry)
                if symbol_value:
                    upper_value = symbol_value.upper()
                    if upper_value not in symbols:
                        symbols.append(upper_value)

            parameters = strategy.get('parameters') or {}
            param_symbols = parameters.get('symbols') or parameters.get('symbol')
            if isinstance(param_symbols, str):
                sym = param_symbols.upper()
                if sym not in symbols:
                    symbols.append(sym)
            elif isinstance(param_symbols, (list, tuple, set)):
                for sym in param_symbols:
                    val = str(sym).upper()
                    if val and val not in symbols:
                        symbols.append(val)

            hours_back = self.sentiment_window_hours
            now = datetime.now(timezone.utc)

            symbol_insights: List[Dict[str, Any]] = []
            symbol_scores: List[float] = []
            latest_symbol_ts: Optional[datetime] = None

            if symbols:
                tasks = [
                    self.database.get_sentiment_entries(symbol=symbol, hours_back=hours_back, limit=60)
                    for symbol in symbols
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for symbol, entries in zip(symbols, results):
                    if isinstance(entries, Exception):
                        logger.warning(
                            "Sentiment query failed for symbol",
                            symbol=symbol,
                            error=str(entries),
                        )
                        continue

                    polarities: List[float] = []
                    freshest: Optional[datetime] = None
                    for entry in entries:
                        polarity = self._extract_sentiment_polarity(entry)
                        if polarity is None and entry.get('value') is not None:
                            polarity = self._fear_greed_to_polarity(entry.get('value'))
                        if polarity is not None:
                            polarities.append(polarity)
                        ts = self._parse_iso_timestamp(entry.get('timestamp'))
                        if ts and (freshest is None or ts > freshest):
                            freshest = ts

                    if polarities:
                        avg = sum(polarities) / len(polarities)
                        recency = 1.0
                        if freshest:
                            age_hours = max(0.0, (now - freshest).total_seconds() / 3600.0)
                            if age_hours > 6:
                                recency = max(0.25, 1 - (age_hours - 6) / 30)
                            if latest_symbol_ts is None or freshest > latest_symbol_ts:
                                latest_symbol_ts = freshest
                        adjusted = avg * recency
                        symbol_scores.append(adjusted)
                        symbol_insights.append(
                            {
                                'symbol': symbol,
                                'average_polarity': avg,
                                'adjusted_polarity': adjusted,
                                'sample_count': len(polarities),
                                'latest_timestamp': freshest.isoformat() if freshest else None,
                                'recency_factor': recency,
                            }
                        )

            global_entries = await self.database.get_sentiment_entries(
                sentiment_types=[
                    'global_crypto_sentiment',
                    'global_market_sentiment',
                    'market_sentiment',
                ],
                hours_back=hours_back,
                limit=80,
            )

            global_polarities: List[float] = []
            latest_global_ts: Optional[datetime] = None
            for entry in global_entries:
                polarity = self._extract_sentiment_polarity(entry)
                if polarity is None and entry.get('value') is not None:
                    polarity = self._fear_greed_to_polarity(entry.get('value'))
                if polarity is not None:
                    global_polarities.append(polarity)
                ts = self._parse_iso_timestamp(entry.get('timestamp'))
                if ts and (latest_global_ts is None or ts > latest_global_ts):
                    latest_global_ts = ts

            avg_symbol = sum(symbol_scores) / len(symbol_scores) if symbol_scores else None
            avg_global = sum(global_polarities) / len(global_polarities) if global_polarities else None

            if avg_symbol is not None and avg_global is not None:
                combined = avg_symbol * 0.6 + avg_global * 0.4
            elif avg_symbol is not None:
                combined = avg_symbol
            elif avg_global is not None:
                combined = avg_global
            else:
                combined = 0.0

            alignment = self._polarity_to_alignment(combined)

            if latest_symbol_ts:
                age_hours = max(0.0, (now - latest_symbol_ts).total_seconds() / 3600.0)
                if age_hours > 12:
                    alignment *= max(0.35, 1 - (age_hours - 12) / 48)

            context = {
                'symbols': symbols,
                'avg_symbol_polarity': avg_symbol,
                'avg_global_polarity': avg_global,
                'combined_polarity': combined,
                'symbol_insights': symbol_insights[:6],
                'global_sample_count': len(global_polarities),
                'latest_symbol_timestamp': latest_symbol_ts.isoformat() if latest_symbol_ts else None,
                'latest_global_timestamp': latest_global_ts.isoformat() if latest_global_ts else None,
            }

            return max(0.0, min(1.0, alignment)), context

        except Exception as error:
            logger.error(
                "Error calculating sentiment alignment",
                error=str(error),
                strategy_id=strategy.get('id'),
            )
            return 0.5, {'error': str(error)}
    
    def _calculate_max_drawdown(self, returns: List[float]) -> float:
        """Calculate maximum drawdown"""
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        return abs(float(np.min(drawdown))) if len(drawdown) > 0 else 0.0
    
    def _calculate_consistency_score(self, returns: List[float]) -> float:
        """Calculate consistency score (0-1)"""
        if not returns:
            return 0.0
        # Based on distribution of returns
        positive_ratio = len([r for r in returns if r > 0]) / len(returns)
        volatility = np.std(returns)
        consistency = positive_ratio * (1.0 - min(1.0, volatility / 0.1))
        return float(max(0.0, min(1.0, consistency)))

    @staticmethod
    def _polarity_to_alignment(polarity: Optional[float]) -> float:
        if polarity is None:
            return 0.5
        return max(0.0, min(1.0, (polarity + 1.0) / 2.0))

    @staticmethod
    def _extract_sentiment_polarity(entry: Dict[str, Any]) -> Optional[float]:
        if not entry:
            return None

        for key in ('aggregated_score', 'polarity', 'sentiment_score', 'score'):
            if entry.get(key) is not None:
                try:
                    value = float(entry[key])
                    if key in {'sentiment_score', 'score'} and abs(value) > 1.0:
                        value = value / 100.0 if abs(value) > 10 else value
                    return max(-1.0, min(1.0, value))
                except (TypeError, ValueError):
                    continue

        aggregated = entry.get('aggregated_sentiment')
        if isinstance(aggregated, dict):
            for key in ('average_polarity', 'polarity', 'aggregated_score'):
                value = aggregated.get(key)
                if value is not None:
                    try:
                        return max(-1.0, min(1.0, float(value)))
                    except (TypeError, ValueError):
                        continue

        metadata = entry.get('metadata')
        if isinstance(metadata, dict):
            for key in ('polarity', 'average_polarity'):
                value = metadata.get(key)
                if value is not None:
                    try:
                        return max(-1.0, min(1.0, float(value)))
                    except (TypeError, ValueError):
                        continue

        return None

    @staticmethod
    def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return None
        return None

    @staticmethod
    def _fear_greed_to_polarity(value: Any) -> Optional[float]:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        polarity = (numeric - 50.0) / 50.0
        return max(-1.0, min(1.0, polarity))
    
    def _identify_regime_change_factors(self) -> List[str]:
        """Identify what triggered regime change"""
        factors = []
        if self.current_conditions:
            if self.current_conditions.volatility > 0.5:
                factors.append("High volatility")
            if abs(self.current_conditions.trend_strength) > 0.5:
                factors.append("Strong trend")
            if self.current_conditions.fear_greed_index < 30:
                factors.append("Extreme fear")
            if self.current_conditions.fear_greed_index > 70:
                factors.append("Extreme greed")
        return factors
    
    async def _store_regime_detection(self, regime: MarketRegime, confidence: float, conditions: MarketConditions):
        """Store regime detection in database"""
        # Implementation
        pass
    
    async def _store_regime_change(self, regime_change: RegimeChange):
        """Store regime change event"""
        # Implementation
        pass
    
    async def _store_activation_decisions(self, decisions: Dict[str, List[ActivationDecision]]):
        """Store activation decisions for audit trail"""
        # Implementation
        pass
