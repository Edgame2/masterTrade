"""
Daily Strategy Review and Improvement System

This module automatically reviews strategy performance daily, compares real results with backtests,
and decides on strategy improvements, parameter adjustments, or replacements.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
import pandas as pd
from scipy import stats
import structlog

from postgres_database import Database
from core.strategy_generator import AdvancedStrategyGenerator
from enhanced_market_data_consumer import EnhancedMarketDataConsumer
from dynamic_data_manager import StrategyDataManager

logger = structlog.get_logger()

class ReviewDecision(Enum):
    KEEP_AS_IS = "keep_as_is"
    OPTIMIZE_PARAMETERS = "optimize_parameters"
    MODIFY_LOGIC = "modify_logic"
    REPLACE_STRATEGY = "replace_strategy"
    PAUSE_STRATEGY = "pause_strategy"
    INCREASE_ALLOCATION = "increase_allocation"
    DECREASE_ALLOCATION = "decrease_allocation"

class PerformanceGrade(Enum):
    EXCELLENT = "A+"  # Top 10% performers
    GOOD = "A"       # Top 25% performers
    AVERAGE = "B"    # Average performers
    POOR = "C"       # Below average
    TERRIBLE = "D"   # Bottom 10%, needs immediate action

@dataclass
class StrategyPerformanceMetrics:
    strategy_id: str
    strategy_name: str
    
    # Performance metrics
    total_return: float
    daily_returns: List[float]
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    
    # Risk metrics
    volatility: float
    var_95: float  # Value at Risk 95%
    cvar_95: float  # Conditional Value at Risk
    
    # Execution metrics
    avg_trade_duration: float
    total_trades: int
    avg_slippage: float
    
    # Market condition performance
    bull_market_return: float
    bear_market_return: float
    sideways_market_return: float
    
    # Backtest comparison
    backtest_sharpe: float
    backtest_return: float
    performance_degradation: float  # Real vs backtest performance
    
    # Strategy health indicators
    days_since_last_trade: int
    parameter_drift_score: float
    market_regime_alignment: float
    
    review_date: datetime

@dataclass
class StrategyReviewResult:
    strategy_id: str
    performance_grade: PerformanceGrade
    decision: ReviewDecision
    confidence_score: float
    
    # Detailed analysis
    strengths: List[str]
    weaknesses: List[str]
    improvement_suggestions: List[str]
    
    # Recommended actions
    parameter_adjustments: Dict[str, Any]
    allocation_change: float  # Percentage change in allocation
    replacement_candidates: List[str]
    
    # Performance prediction
    expected_future_performance: Dict[str, float]
    risk_assessment: str
    
    review_timestamp: datetime

class DailyStrategyReviewer:
    """
    Comprehensive daily strategy review and improvement system
    
    Features:
    - Daily performance analysis vs backtests
    - Market regime detection and strategy alignment
    - Automated parameter optimization suggestions
    - Strategy replacement recommendations
    - Risk-adjusted performance evaluation
    - Predictive performance modeling
    """
    
    def __init__(self, 
                 database: Database,
                 strategy_generator: AdvancedStrategyGenerator,
                 market_data_consumer: EnhancedMarketDataConsumer,
                 strategy_data_manager: StrategyDataManager):
        self.database = database
        self.strategy_generator = strategy_generator
        self.market_data_consumer = market_data_consumer
        self.strategy_data_manager = strategy_data_manager
        
        # Review configuration
        self.review_lookback_days = 30
        self.min_trades_for_review = 10
        self.performance_threshold = {
            'excellent': 0.15,  # Sharpe > 1.5
            'good': 0.10,       # Sharpe > 1.0
            'average': 0.05,    # Sharpe > 0.5
            'poor': 0.0,        # Sharpe > 0
            'terrible': -0.05   # Sharpe < 0
        }
        
        # Market regime detection
        self.market_regimes = ['bull', 'bear', 'sideways', 'volatile']
        self.current_market_regime = 'sideways'
        
        # Review history
        self.review_history: Dict[str, List[StrategyReviewResult]] = {}
    
    async def run_daily_review(self) -> Dict[str, StrategyReviewResult]:
        """
        Run comprehensive daily strategy review
        
        Returns:
            Dictionary of strategy_id -> StrategyReviewResult
        """
        try:
            logger.info("Starting daily strategy review process")
            
            # Get all active strategies
            active_strategies = await self.database.get_active_strategies()
            logger.info(f"Found {len(active_strategies)} active strategies to review")
            
            # Detect current market regime
            await self._detect_market_regime()
            
            review_results = {}
            
            for strategy in active_strategies:
                strategy_id = strategy['id']
                
                try:
                    # Calculate performance metrics
                    performance_metrics = await self._calculate_performance_metrics(strategy_id)
                    
                    if performance_metrics is None:
                        logger.warning(f"Insufficient data for strategy {strategy_id}, skipping review")
                        continue
                    
                    # Conduct comprehensive review
                    review_result = await self._conduct_strategy_review(
                        strategy, 
                        performance_metrics
                    )
                    
                    review_results[strategy_id] = review_result
                    
                    # Store review result
                    await self._store_review_result(review_result)
                    
                    # Execute recommended actions
                    await self._execute_review_actions(review_result)
                    
                    logger.info(
                        f"Strategy {strategy_id} reviewed",
                        grade=review_result.performance_grade.value,
                        decision=review_result.decision.value,
                        confidence=review_result.confidence_score
                    )
                    
                except Exception as e:
                    logger.error(f"Error reviewing strategy {strategy_id}: {e}")
                    continue
            
            # Generate daily review summary
            await self._generate_review_summary(review_results)
            
            logger.info(f"Daily review completed for {len(review_results)} strategies")
            return review_results
            
        except Exception as e:
            logger.error(f"Error in daily strategy review: {e}")
            raise
    
    async def _calculate_performance_metrics(self, strategy_id: str) -> Optional[StrategyPerformanceMetrics]:
        """Calculate comprehensive performance metrics for a strategy"""
        try:
            # Get strategy information
            strategy_info = await self.database.get_strategy(strategy_id)
            if not strategy_info:
                return None
            
            # Get recent performance data
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=self.review_lookback_days)
            
            # Get trading history
            trades = await self.database.get_strategy_trades(
                strategy_id=strategy_id,
                start_date=start_date,
                end_date=end_date
            )
            
            if len(trades) < self.min_trades_for_review:
                logger.info(f"Strategy {strategy_id} has only {len(trades)} trades, insufficient for review")
                return None
            
            # Calculate daily returns
            daily_returns = await self._calculate_daily_returns(trades)
            
            if len(daily_returns) == 0:
                return None
            
            # Calculate performance metrics
            total_return = sum(daily_returns)
            sharpe_ratio = self._calculate_sharpe_ratio(daily_returns)
            sortino_ratio = self._calculate_sortino_ratio(daily_returns)
            max_drawdown = self._calculate_max_drawdown(daily_returns)
            calmar_ratio = total_return / abs(max_drawdown) if max_drawdown != 0 else 0
            
            # Calculate trade-based metrics
            win_rate = self._calculate_win_rate(trades)
            profit_factor = self._calculate_profit_factor(trades)
            avg_trade_duration = self._calculate_avg_trade_duration(trades)
            avg_slippage = self._calculate_avg_slippage(trades)
            
            # Calculate risk metrics
            volatility = np.std(daily_returns) * np.sqrt(252)  # Annualized
            var_95 = np.percentile(daily_returns, 5)
            cvar_95 = np.mean([r for r in daily_returns if r <= var_95])
            
            # Get market condition performance
            market_performance = await self._calculate_market_condition_performance(
                strategy_id, daily_returns
            )
            
            # Compare with backtest results
            backtest_metrics = await self._get_backtest_metrics(strategy_id)
            performance_degradation = self._calculate_performance_degradation(
                sharpe_ratio, backtest_metrics.get('sharpe_ratio', 0)
            )
            
            # Calculate strategy health indicators
            days_since_last_trade = self._calculate_days_since_last_trade(trades)
            parameter_drift_score = await self._calculate_parameter_drift(strategy_id)
            market_regime_alignment = await self._calculate_market_alignment(strategy_id)
            
            return StrategyPerformanceMetrics(
                strategy_id=strategy_id,
                strategy_name=strategy_info.get('name', ''),
                total_return=total_return,
                daily_returns=daily_returns,
                sharpe_ratio=sharpe_ratio,
                sortino_ratio=sortino_ratio,
                max_drawdown=max_drawdown,
                calmar_ratio=calmar_ratio,
                win_rate=win_rate,
                profit_factor=profit_factor,
                volatility=volatility,
                var_95=var_95,
                cvar_95=cvar_95,
                avg_trade_duration=avg_trade_duration,
                total_trades=len(trades),
                avg_slippage=avg_slippage,
                bull_market_return=market_performance.get('bull', 0),
                bear_market_return=market_performance.get('bear', 0),
                sideways_market_return=market_performance.get('sideways', 0),
                backtest_sharpe=backtest_metrics.get('sharpe_ratio', 0),
                backtest_return=backtest_metrics.get('total_return', 0),
                performance_degradation=performance_degradation,
                days_since_last_trade=days_since_last_trade,
                parameter_drift_score=parameter_drift_score,
                market_regime_alignment=market_regime_alignment,
                review_date=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics for {strategy_id}: {e}")
            return None
    
    async def _conduct_strategy_review(self, 
                                     strategy: Dict, 
                                     metrics: StrategyPerformanceMetrics) -> StrategyReviewResult:
        """Conduct comprehensive strategy review and make improvement decisions"""
        
        strategy_id = strategy['id']
        
        # Grade performance
        performance_grade = self._grade_performance(metrics)
        
        # Analyze strengths and weaknesses
        strengths, weaknesses = self._analyze_strategy_characteristics(metrics)
        
        # Generate improvement suggestions
        improvement_suggestions = await self._generate_improvement_suggestions(strategy, metrics)
        
        # Make review decision
        decision, confidence = self._make_review_decision(strategy, metrics, performance_grade)
        
        # Calculate recommended parameter adjustments
        parameter_adjustments = await self._recommend_parameter_adjustments(strategy, metrics)
        
        # Calculate allocation changes
        allocation_change = self._calculate_allocation_change(metrics, performance_grade)
        
        # Find replacement candidates if needed
        replacement_candidates = []
        if decision == ReviewDecision.REPLACE_STRATEGY:
            replacement_candidates = await self._find_replacement_candidates(strategy, metrics)
        
        # Predict future performance
        future_performance = await self._predict_future_performance(strategy, metrics)
        
        # Assess risk
        risk_assessment = self._assess_risk(metrics)
        
        return StrategyReviewResult(
            strategy_id=strategy_id,
            performance_grade=performance_grade,
            decision=decision,
            confidence_score=confidence,
            strengths=strengths,
            weaknesses=weaknesses,
            improvement_suggestions=improvement_suggestions,
            parameter_adjustments=parameter_adjustments,
            allocation_change=allocation_change,
            replacement_candidates=replacement_candidates,
            expected_future_performance=future_performance,
            risk_assessment=risk_assessment,
            review_timestamp=datetime.now(timezone.utc)
        )
    
    def _grade_performance(self, metrics: StrategyPerformanceMetrics) -> PerformanceGrade:
        """Grade strategy performance based on multiple metrics"""
        
        # Calculate composite score
        score = 0
        
        # Sharpe ratio weight (40%)
        if metrics.sharpe_ratio >= 2.0:
            score += 40
        elif metrics.sharpe_ratio >= 1.5:
            score += 35
        elif metrics.sharpe_ratio >= 1.0:
            score += 25
        elif metrics.sharpe_ratio >= 0.5:
            score += 15
        elif metrics.sharpe_ratio >= 0:
            score += 5
        
        # Max drawdown weight (25%)
        if metrics.max_drawdown >= -0.05:  # Less than 5% drawdown
            score += 25
        elif metrics.max_drawdown >= -0.10:
            score += 20
        elif metrics.max_drawdown >= -0.15:
            score += 15
        elif metrics.max_drawdown >= -0.25:
            score += 10
        elif metrics.max_drawdown >= -0.35:
            score += 5
        
        # Win rate weight (15%)
        if metrics.win_rate >= 0.60:
            score += 15
        elif metrics.win_rate >= 0.55:
            score += 12
        elif metrics.win_rate >= 0.50:
            score += 9
        elif metrics.win_rate >= 0.45:
            score += 6
        elif metrics.win_rate >= 0.40:
            score += 3
        
        # Performance degradation weight (20%)
        if metrics.performance_degradation <= 0.05:  # Within 5% of backtest
            score += 20
        elif metrics.performance_degradation <= 0.15:
            score += 15
        elif metrics.performance_degradation <= 0.30:
            score += 10
        elif metrics.performance_degradation <= 0.50:
            score += 5
        
        # Determine grade
        if score >= 85:
            return PerformanceGrade.EXCELLENT
        elif score >= 70:
            return PerformanceGrade.GOOD
        elif score >= 50:
            return PerformanceGrade.AVERAGE
        elif score >= 30:
            return PerformanceGrade.POOR
        else:
            return PerformanceGrade.TERRIBLE
    
    def _make_review_decision(self, 
                            strategy: Dict, 
                            metrics: StrategyPerformanceMetrics,
                            grade: PerformanceGrade) -> Tuple[ReviewDecision, float]:
        """Make review decision based on comprehensive analysis"""
        
        confidence = 0.0
        
        # Excellent performers - keep or increase allocation
        if grade == PerformanceGrade.EXCELLENT:
            if metrics.performance_degradation < 0.10:
                decision = ReviewDecision.INCREASE_ALLOCATION
                confidence = 0.9
            else:
                decision = ReviewDecision.KEEP_AS_IS
                confidence = 0.8
        
        # Good performers - optimize or keep
        elif grade == PerformanceGrade.GOOD:
            if metrics.performance_degradation > 0.20:
                decision = ReviewDecision.OPTIMIZE_PARAMETERS
                confidence = 0.7
            else:
                decision = ReviewDecision.KEEP_AS_IS
                confidence = 0.6
        
        # Average performers - need optimization
        elif grade == PerformanceGrade.AVERAGE:
            if metrics.performance_degradation > 0.30:
                decision = ReviewDecision.MODIFY_LOGIC
                confidence = 0.6
            elif metrics.days_since_last_trade > 7:
                decision = ReviewDecision.OPTIMIZE_PARAMETERS
                confidence = 0.7
            else:
                decision = ReviewDecision.DECREASE_ALLOCATION
                confidence = 0.5
        
        # Poor performers - major changes needed
        elif grade == PerformanceGrade.POOR:
            if metrics.performance_degradation > 0.50:
                decision = ReviewDecision.REPLACE_STRATEGY
                confidence = 0.8
            elif metrics.max_drawdown < -0.30:
                decision = ReviewDecision.PAUSE_STRATEGY
                confidence = 0.9
            else:
                decision = ReviewDecision.MODIFY_LOGIC
                confidence = 0.6
        
        # Terrible performers - immediate action
        else:  # TERRIBLE
            if metrics.sharpe_ratio < -0.5 or metrics.max_drawdown < -0.40:
                decision = ReviewDecision.PAUSE_STRATEGY
                confidence = 0.95
            else:
                decision = ReviewDecision.REPLACE_STRATEGY
                confidence = 0.85
        
        # Adjust confidence based on data quality
        if metrics.total_trades < 20:
            confidence *= 0.8  # Less confidence with fewer trades
        
        if metrics.days_since_last_trade > 14:
            confidence *= 0.7  # Less confidence if strategy is inactive
        
        return decision, confidence
    
    async def _generate_improvement_suggestions(self, 
                                              strategy: Dict, 
                                              metrics: StrategyPerformanceMetrics) -> List[str]:
        """Generate specific improvement suggestions"""
        suggestions = []
        
        # Performance-based suggestions
        if metrics.sharpe_ratio < 1.0:
            suggestions.append("Consider adding volatility filters to improve risk-adjusted returns")
        
        if metrics.max_drawdown < -0.20:
            suggestions.append("Implement dynamic position sizing to reduce maximum drawdown")
        
        if metrics.win_rate < 0.45:
            suggestions.append("Review entry conditions - consider more selective signal generation")
        
        if metrics.avg_slippage > 0.001:  # More than 0.1%
            suggestions.append("Optimize execution timing to reduce slippage")
        
        # Market alignment suggestions
        if metrics.market_regime_alignment < 0.5:
            suggestions.append(f"Strategy not well-aligned with current {self.current_market_regime} market")
        
        # Parameter drift suggestions
        if metrics.parameter_drift_score > 0.3:
            suggestions.append("Parameters may need reoptimization based on recent market changes")
        
        # Activity-based suggestions
        if metrics.days_since_last_trade > 7:
            suggestions.append("Strategy showing low activity - consider relaxing entry conditions")
        
        # Performance degradation suggestions
        if metrics.performance_degradation > 0.25:
            suggestions.append("Significant performance degradation vs backtest - investigate overfitting")
        
        return suggestions
    
    async def _recommend_parameter_adjustments(self, 
                                             strategy: Dict, 
                                             metrics: StrategyPerformanceMetrics) -> Dict[str, Any]:
        """Recommend specific parameter adjustments"""
        adjustments = {}
        
        strategy_config = strategy.get('configuration', {})
        
        # Risk management adjustments
        if metrics.max_drawdown < -0.25:
            adjustments['position_size_multiplier'] = 0.7  # Reduce position size
            adjustments['stop_loss_tightening'] = 0.8  # Tighten stop losses
        
        # Performance optimization adjustments
        if metrics.win_rate < 0.40:
            # Suggest tighter entry criteria
            if 'rsi_oversold' in strategy_config:
                adjustments['rsi_oversold'] = max(20, strategy_config.get('rsi_oversold', 30) - 5)
            
            if 'signal_threshold' in strategy_config:
                adjustments['signal_threshold'] = strategy_config.get('signal_threshold', 0.5) + 0.1
        
        # Activity adjustments
        if metrics.days_since_last_trade > 10:
            # Relax entry conditions
            if 'volume_threshold' in strategy_config:
                adjustments['volume_threshold'] = strategy_config.get('volume_threshold', 1.0) * 0.8
        
        # Market regime adjustments
        if self.current_market_regime == 'volatile':
            adjustments['volatility_threshold_multiplier'] = 1.2
        elif self.current_market_regime == 'sideways':
            adjustments['mean_reversion_strength'] = 1.1
        
        return adjustments
    
    async def _find_replacement_candidates(self, 
                                         strategy: Dict, 
                                         metrics: StrategyPerformanceMetrics) -> List[str]:
        """Find better performing strategies as replacement candidates"""
        
        # Get strategies with similar characteristics but better performance
        similar_strategies = await self.database.get_similar_strategies(
            strategy_type=strategy.get('type'),
            symbols=strategy.get('symbols', []),
            timeframes=strategy.get('timeframes', [])
        )
        
        # Filter for better performers
        candidates = []
        for candidate in similar_strategies:
            candidate_metrics = await self._get_cached_performance_metrics(candidate['id'])
            
            if candidate_metrics and candidate_metrics.sharpe_ratio > metrics.sharpe_ratio * 1.2:
                candidates.append(candidate['id'])
        
        # If no similar strategies, generate new ones
        if not candidates:
            logger.info(f"Generating new strategy candidates to replace {strategy['id']}")
            new_strategies = await self.strategy_generator.generate_improved_strategies(
                base_strategy=strategy,
                target_metrics={'sharpe_ratio': metrics.sharpe_ratio * 1.5},
                count=3
            )
            candidates = [s['id'] for s in new_strategies]
        
        return candidates[:5]  # Return top 5 candidates
    
    async def _execute_review_actions(self, review: StrategyReviewResult):
        """Execute the recommended actions from strategy review"""
        try:
            strategy_id = review.strategy_id
            
            # Update strategy status based on decision
            if review.decision == ReviewDecision.PAUSE_STRATEGY:
                await self.database.update_strategy_status(strategy_id, 'paused')
                logger.info(f"Strategy {strategy_id} paused due to poor performance")
            
            elif review.decision == ReviewDecision.OPTIMIZE_PARAMETERS:
                if review.parameter_adjustments:
                    await self.database.update_strategy_parameters(
                        strategy_id, 
                        review.parameter_adjustments
                    )
                    logger.info(f"Updated parameters for strategy {strategy_id}")
            
            elif review.decision == ReviewDecision.REPLACE_STRATEGY:
                if review.replacement_candidates:
                    # Activate best replacement candidate
                    best_candidate = review.replacement_candidates[0]
                    await self.database.activate_replacement_strategy(
                        old_strategy_id=strategy_id,
                        new_strategy_id=best_candidate
                    )
                    logger.info(f"Replaced strategy {strategy_id} with {best_candidate}")
            
            # Update allocation if recommended
            if abs(review.allocation_change) > 0.1:  # More than 10% change
                await self.database.update_strategy_allocation(
                    strategy_id,
                    review.allocation_change
                )
                logger.info(
                    f"Updated allocation for strategy {strategy_id} by {review.allocation_change:.1%}"
                )
            
        except Exception as e:
            logger.error(f"Error executing review actions for {strategy_id}: {e}")
    
    # Helper methods for calculations
    def _calculate_daily_returns(self, trades: List[Dict]) -> List[float]:
        """Calculate daily returns from trade data"""
        # Group trades by date and calculate daily P&L
        daily_pnl = {}
        
        for trade in trades:
            trade_date = trade['timestamp'].date()
            pnl = trade.get('pnl', 0)
            
            if trade_date not in daily_pnl:
                daily_pnl[trade_date] = 0
            daily_pnl[trade_date] += pnl
        
        return list(daily_pnl.values())
    
    def _calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) == 0:
            return 0
        
        excess_returns = [r - risk_free_rate/252 for r in returns]  # Daily risk-free rate
        return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252) if np.std(excess_returns) > 0 else 0
    
    def _calculate_sortino_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio (downside deviation)"""
        if len(returns) == 0:
            return 0
        
        excess_returns = [r - risk_free_rate/252 for r in returns]
        downside_returns = [r for r in excess_returns if r < 0]
        
        if len(downside_returns) == 0:
            return float('inf')
        
        downside_std = np.std(downside_returns)
        return np.mean(excess_returns) / downside_std * np.sqrt(252) if downside_std > 0 else 0
    
    def _calculate_max_drawdown(self, returns: List[float]) -> float:
        """Calculate maximum drawdown"""
        if len(returns) == 0:
            return 0
        
        cumulative = np.cumprod([1 + r for r in returns])
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / peak
        return np.min(drawdown)
    
    def _calculate_win_rate(self, trades: List[Dict]) -> float:
        """Calculate win rate"""
        if len(trades) == 0:
            return 0
        
        winning_trades = len([t for t in trades if t.get('pnl', 0) > 0])
        return winning_trades / len(trades)
    
    def _calculate_profit_factor(self, trades: List[Dict]) -> float:
        """Calculate profit factor"""
        gross_profits = sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) > 0)
        gross_losses = abs(sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) < 0))
        
        return gross_profits / gross_losses if gross_losses > 0 else float('inf')
    
    async def _detect_market_regime(self):
        """Detect current market regime"""
        try:
            # Get recent market data for major indices
            symbols = ['BTCUSDT', 'ETHUSDT', 'SPY', 'QQQ']
            
            market_data = await self.market_data_consumer.get_historical_data(
                symbols=symbols,
                timeframes=['1d'],
                start_date=datetime.now(timezone.utc) - timedelta(days=60),
                end_date=datetime.now(timezone.utc)
            )
            
            # Calculate regime indicators
            volatility_scores = []
            trend_scores = []
            
            for symbol in symbols:
                df = market_data.get(symbol, {}).get('1d', pd.DataFrame())
                if not df.empty:
                    # Calculate volatility (normalized)
                    returns = df['close'].pct_change().dropna()
                    volatility = returns.std() * np.sqrt(252)
                    volatility_scores.append(volatility)
                    
                    # Calculate trend strength
                    trend = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]
                    trend_scores.append(trend)
            
            if volatility_scores and trend_scores:
                avg_volatility = np.mean(volatility_scores)
                avg_trend = np.mean(trend_scores)
                
                # Classify market regime
                if avg_volatility > 0.4:  # High volatility
                    self.current_market_regime = 'volatile'
                elif avg_trend > 0.15:    # Strong uptrend
                    self.current_market_regime = 'bull'
                elif avg_trend < -0.15:   # Strong downtrend
                    self.current_market_regime = 'bear'
                else:                     # Low volatility, no strong trend
                    self.current_market_regime = 'sideways'
                
                logger.info(f"Detected market regime: {self.current_market_regime}")
        
        except Exception as e:
            logger.error(f"Error detecting market regime: {e}")
            self.current_market_regime = 'sideways'  # Default fallback
    
    async def _store_review_result(self, review: StrategyReviewResult):
        """Store review result in database"""
        try:
            review_data = {
                'strategy_id': review.strategy_id,
                'review_timestamp': review.review_timestamp,
                'performance_grade': review.performance_grade.value,
                'decision': review.decision.value,
                'confidence_score': review.confidence_score,
                'strengths': review.strengths,
                'weaknesses': review.weaknesses,
                'improvement_suggestions': review.improvement_suggestions,
                'parameter_adjustments': review.parameter_adjustments,
                'allocation_change': review.allocation_change,
                'replacement_candidates': review.replacement_candidates,
                'expected_future_performance': review.expected_future_performance,
                'risk_assessment': review.risk_assessment
            }
            
            await self.database.store_strategy_review(review_data)
            
            # Update review history
            if review.strategy_id not in self.review_history:
                self.review_history[review.strategy_id] = []
            
            self.review_history[review.strategy_id].append(review)
            
            # Keep only last 30 reviews per strategy
            if len(self.review_history[review.strategy_id]) > 30:
                self.review_history[review.strategy_id] = self.review_history[review.strategy_id][-30:]
        
        except Exception as e:
            logger.error(f"Error storing review result: {e}")
    
    async def _generate_review_summary(self, review_results: Dict[str, StrategyReviewResult]):
        """Generate daily review summary"""
        try:
            summary = {
                'review_date': datetime.now(timezone.utc).date(),
                'total_strategies_reviewed': len(review_results),
                'grade_distribution': {},
                'decision_distribution': {},
                'avg_confidence': 0,
                'top_performers': [],
                'strategies_needing_attention': [],
                'market_regime': self.current_market_regime
            }
            
            # Calculate distributions
            grades = [r.performance_grade.value for r in review_results.values()]
            decisions = [r.decision.value for r in review_results.values()]
            
            summary['grade_distribution'] = {grade: grades.count(grade) for grade in set(grades)}
            summary['decision_distribution'] = {decision: decisions.count(decision) for decision in set(decisions)}
            
            # Calculate average confidence
            if review_results:
                summary['avg_confidence'] = np.mean([r.confidence_score for r in review_results.values()])
            
            # Identify top performers and problem strategies
            excellent_strategies = [
                r.strategy_id for r in review_results.values() 
                if r.performance_grade == PerformanceGrade.EXCELLENT
            ]
            
            problem_strategies = [
                r.strategy_id for r in review_results.values()
                if r.performance_grade in [PerformanceGrade.POOR, PerformanceGrade.TERRIBLE]
            ]
            
            summary['top_performers'] = excellent_strategies[:10]
            summary['strategies_needing_attention'] = problem_strategies
            
            # Store summary
            await self.database.store_daily_review_summary(summary)
            
            logger.info(
                "Daily review summary generated",
                total_reviewed=summary['total_strategies_reviewed'],
                excellent_count=len(excellent_strategies),
                problem_count=len(problem_strategies),
                avg_confidence=summary['avg_confidence']
            )
        
        except Exception as e:
            logger.error(f"Error generating review summary: {e}")
    
    # Placeholder methods for additional calculations
    async def _calculate_market_condition_performance(self, strategy_id: str, daily_returns: List[float]) -> Dict[str, float]:
        """Calculate performance in different market conditions"""
        # Placeholder - would analyze returns during different market regimes
        return {'bull': 0.0, 'bear': 0.0, 'sideways': 0.0}
    
    async def _get_backtest_metrics(self, strategy_id: str) -> Dict[str, float]:
        """Get backtest metrics for comparison"""
        backtest_data = await self.database.get_strategy_backtest_results(strategy_id)
        return backtest_data.get('metrics', {}) if backtest_data else {}
    
    def _calculate_performance_degradation(self, real_sharpe: float, backtest_sharpe: float) -> float:
        """Calculate performance degradation vs backtest"""
        if backtest_sharpe == 0:
            return 0
        return abs(real_sharpe - backtest_sharpe) / abs(backtest_sharpe)
    
    def _calculate_days_since_last_trade(self, trades: List[Dict]) -> int:
        """Calculate days since last trade"""
        if not trades:
            return 999  # Very high number if no trades
        
        last_trade_date = max(trade['timestamp'] for trade in trades)
        return (datetime.now(timezone.utc) - last_trade_date).days
    
    async def _calculate_parameter_drift(self, strategy_id: str) -> float:
        """Calculate parameter drift score"""
        # Placeholder - would analyze how much optimal parameters have changed
        return 0.0
    
    async def _calculate_market_alignment(self, strategy_id: str) -> float:
        """Calculate market regime alignment score"""
        # Placeholder - would analyze strategy performance in current market regime
        return 0.5
    
    def _analyze_strategy_characteristics(self, metrics: StrategyPerformanceMetrics) -> Tuple[List[str], List[str]]:
        """Analyze strategy strengths and weaknesses"""
        strengths = []
        weaknesses = []
        
        # Analyze strengths
        if metrics.sharpe_ratio > 1.5:
            strengths.append("Excellent risk-adjusted returns")
        if metrics.max_drawdown > -0.10:
            strengths.append("Low maximum drawdown")
        if metrics.win_rate > 0.55:
            strengths.append("High win rate")
        if metrics.performance_degradation < 0.15:
            strengths.append("Consistent with backtesting expectations")
        
        # Analyze weaknesses
        if metrics.sharpe_ratio < 0.5:
            weaknesses.append("Poor risk-adjusted returns")
        if metrics.max_drawdown < -0.25:
            weaknesses.append("High maximum drawdown")
        if metrics.win_rate < 0.40:
            weaknesses.append("Low win rate")
        if metrics.performance_degradation > 0.30:
            weaknesses.append("Significant degradation vs backtest")
        if metrics.days_since_last_trade > 10:
            weaknesses.append("Low trading activity")
        
        return strengths, weaknesses
    
    def _calculate_allocation_change(self, metrics: StrategyPerformanceMetrics, grade: PerformanceGrade) -> float:
        """Calculate recommended allocation change"""
        if grade == PerformanceGrade.EXCELLENT:
            return 0.20  # Increase by 20%
        elif grade == PerformanceGrade.GOOD:
            return 0.05  # Slight increase
        elif grade == PerformanceGrade.AVERAGE:
            return 0.0   # No change
        elif grade == PerformanceGrade.POOR:
            return -0.30 # Decrease by 30%
        else:  # TERRIBLE
            return -0.70 # Severe decrease
    
    async def _predict_future_performance(self, strategy: Dict, metrics: StrategyPerformanceMetrics) -> Dict[str, float]:
        """Predict future performance"""
        # Placeholder for ML-based performance prediction
        return {
            'expected_sharpe_1m': metrics.sharpe_ratio * 0.95,
            'expected_return_1m': metrics.total_return * 0.8,
            'confidence_interval': 0.2
        }
    
    def _assess_risk(self, metrics: StrategyPerformanceMetrics) -> str:
        """Assess strategy risk level"""
        if metrics.max_drawdown < -0.30 or metrics.sharpe_ratio < 0:
            return "HIGH RISK - Consider immediate intervention"
        elif metrics.max_drawdown < -0.20 or metrics.volatility > 0.5:
            return "MEDIUM RISK - Monitor closely"
        else:
            return "LOW RISK - Normal monitoring"
    
    async def _get_cached_performance_metrics(self, strategy_id: str) -> Optional[StrategyPerformanceMetrics]:
        """Get cached performance metrics"""
        # Placeholder - would retrieve from cache or database
        return None


# Convenience function to schedule daily reviews
async def schedule_daily_reviews(reviewer: DailyStrategyReviewer):
    """Schedule daily strategy reviews"""
    import schedule
    import asyncio
    
    def run_review():
        asyncio.create_task(reviewer.run_daily_review())
    
    # Schedule daily review at 2 AM UTC
    schedule.every().day.at("02:00").do(run_review)
    
    while True:
        schedule.run_pending()
        await asyncio.sleep(3600)  # Check every hour