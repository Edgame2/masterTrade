"""
Advanced Risk Management Controller

This module provides comprehensive portfolio-level risk management with:
- Portfolio-level risk limits and controls
- Correlation-based position sizing adjustments  
- Dynamic stop-loss based on volatility regimes
- Maximum drawdown controls with circuit breakers
- Asset class and sector exposure limits
- Risk aggregation across strategies
- Stress testing and scenario analysis

Integrates with:
- Market data service for correlations, volatility, sentiment
- Existing risk_manager components (position_sizing, stop_loss_manager, portfolio_risk_controller)
- Strategy service for position signals
"""

import asyncio
import math
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Set
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, field
from enum import Enum
import structlog
from scipy import stats
from collections import defaultdict

from config import settings, get_asset_class, get_risk_multiplier
from database import RiskManagementDatabase
from position_sizing import PositionSizingEngine, PositionSizeRequest, PositionSizeResult
from stop_loss_manager import StopLossManager, StopLossConfig, StopLossType
from portfolio_risk_controller import (
    PortfolioRiskController, RiskMetrics, RiskLevel, 
    RiskAlert, AlertType, ExposureLimits
)

logger = structlog.get_logger()


class RiskRegime(Enum):
    """Market risk regime classification"""
    LOW_VOL_BULLISH = "low_vol_bullish"
    LOW_VOL_BEARISH = "low_vol_bearish"
    HIGH_VOL_BULLISH = "high_vol_bullish"
    HIGH_VOL_BEARISH = "high_vol_bearish"
    EXTREME_VOLATILITY = "extreme_volatility"
    CRISIS = "crisis"


class CircuitBreakerLevel(Enum):
    """Circuit breaker severity levels"""
    NONE = "none"
    WARNING = "warning"          # 5% drawdown - warning alerts
    LEVEL_1 = "level_1"          # 10% drawdown - reduce new positions by 50%
    LEVEL_2 = "level_2"          # 15% drawdown - no new positions
    LEVEL_3 = "level_3"          # 20% drawdown - close all positions


@dataclass
class PortfolioLimits:
    """Comprehensive portfolio-level limits"""
    # Overall portfolio limits
    max_portfolio_leverage: float = 2.0
    max_portfolio_var_percent: float = 5.0  # Max 5% 1-day VaR
    max_drawdown_percent: float = 15.0      # Max 15% from peak
    min_cash_reserve_percent: float = 10.0   # Keep 10% in cash
    
    # Position concentration limits
    max_single_position_percent: float = 10.0     # Max 10% per position
    max_correlated_exposure_percent: float = 25.0 # Max 25% in correlated assets (>0.7)
    max_sector_exposure_percent: float = 30.0     # Max 30% per sector
    
    # Asset class limits
    max_crypto_exposure_percent: float = 80.0     # Max 80% in crypto
    max_defi_exposure_percent: float = 20.0       # Max 20% in DeFi
    max_altcoin_exposure_percent: float = 40.0    # Max 40% in altcoins
    
    # Risk concentration
    max_single_strategy_percent: float = 40.0     # Max 40% to one strategy
    max_short_exposure_percent: float = 20.0      # Max 20% short exposure
    
    # Volatility-based limits
    high_vol_position_reduction: float = 0.5      # Reduce size by 50% in high vol
    extreme_vol_position_reduction: float = 0.25  # Reduce size by 75% in extreme vol


@dataclass
class CorrelationRiskMetrics:
    """Correlation-based risk assessment"""
    portfolio_correlation: float            # Average portfolio correlation
    diversification_ratio: float            # Portfolio vol / weighted avg vol
    correlation_clusters: Dict[str, List[str]]  # Highly correlated asset groups
    effective_assets: float                 # Number of independent bets
    correlation_risk_score: float           # 0-100, higher = more risk
    recommendations: List[str]


@dataclass
class DynamicStopLossParams:
    """Volatility-regime adjusted stop-loss parameters"""
    regime: RiskRegime
    base_stop_percent: float
    adjusted_stop_percent: float
    trailing_distance_percent: float
    atr_multiplier: float
    time_decay_rate: float
    breakeven_trigger_percent: float
    volatility_multiplier: float
    reasoning: str


@dataclass
class DrawdownControl:
    """Drawdown monitoring and control state"""
    current_portfolio_value: float
    peak_portfolio_value: float
    current_drawdown_percent: float
    circuit_breaker_level: CircuitBreakerLevel
    positions_allowed: bool
    position_size_multiplier: float         # 0.0 to 1.0
    time_until_reset: Optional[timedelta]
    actions_taken: List[str]
    last_updated: datetime


@dataclass
class RiskApprovalResult:
    """Result of comprehensive risk check"""
    approved: bool
    position_size_adjustment: float         # Multiplier: 0.0 to 1.0
    stop_loss_params: DynamicStopLossParams
    risk_score: float                       # 0-100
    risk_factors: Dict[str, float]
    warnings: List[str]
    rejections: List[str]
    recommendations: List[str]
    metadata: Dict[str, any]


class AdvancedRiskController:
    """
    Advanced Portfolio-Level Risk Management System
    
    Coordinates all risk management components to enforce comprehensive
    portfolio-level controls, adapt to market conditions, and prevent
    catastrophic losses.
    """
    
    def __init__(
        self,
        database: RiskManagementDatabase,
        position_sizing: PositionSizingEngine,
        stop_loss_manager: StopLossManager,
        portfolio_controller: PortfolioRiskController
    ):
        self.database = database
        self.position_sizing = position_sizing
        self.stop_loss_manager = stop_loss_manager
        self.portfolio_controller = portfolio_controller
        
        # Risk limits and state
        self.portfolio_limits = PortfolioLimits()
        self.drawdown_control: Optional[DrawdownControl] = None
        self.current_regime: RiskRegime = RiskRegime.LOW_VOL_BULLISH
        
        # Cached data
        self._correlation_matrix: Optional[np.ndarray] = None
        self._correlation_symbols: List[str] = []
        self._last_correlation_update: Optional[datetime] = None
        
        logger.info("Advanced Risk Controller initialized")
    
    
    async def approve_new_position(
        self,
        symbol: str,
        strategy_id: str,
        signal_strength: float,
        requested_size_usd: float,
        current_price: float,
        volatility: Optional[float] = None
    ) -> RiskApprovalResult:
        """
        Comprehensive risk approval for new position
        
        Checks:
        1. Circuit breaker status
        2. Portfolio-level limits
        3. Correlation risk
        4. Sector/asset class exposure
        5. Volatility regime
        6. Drawdown controls
        
        Returns adjusted position size and stop-loss parameters
        """
        warnings = []
        rejections = []
        recommendations = []
        risk_factors = {}
        
        try:
            # Step 1: Update drawdown control state
            await self._update_drawdown_control()
            
            # Step 2: Check circuit breaker
            if not self.drawdown_control.positions_allowed:
                return RiskApprovalResult(
                    approved=False,
                    position_size_adjustment=0.0,
                    stop_loss_params=await self._get_stop_loss_params(symbol, volatility),
                    risk_score=100.0,
                    risk_factors={'circuit_breaker': 1.0},
                    warnings=[],
                    rejections=[f"Circuit breaker {self.drawdown_control.circuit_breaker_level.value} active"],
                    recommendations=["Wait for portfolio recovery before opening new positions"],
                    metadata={'drawdown': self.drawdown_control.current_drawdown_percent}
                )
            
            # Step 3: Get current portfolio state
            portfolio_metrics = await self.portfolio_controller.calculate_risk_metrics()
            positions = await self.database.get_all_active_positions()
            
            # Step 4: Determine risk regime
            regime = await self._determine_risk_regime(volatility)
            risk_factors['regime'] = self._regime_to_score(regime)
            
            # Step 5: Calculate correlation risk
            correlation_risk = await self._assess_correlation_risk(symbol, positions)
            risk_factors['correlation'] = correlation_risk.correlation_risk_score / 100.0
            
            if correlation_risk.correlation_risk_score > 70:
                warnings.append(
                    f"High correlation risk: {correlation_risk.correlation_risk_score:.1f}/100"
                )
                recommendations.extend(correlation_risk.recommendations)
            
            # Step 6: Check portfolio-level limits
            position_size_multiplier = 1.0
            
            # Apply circuit breaker reduction
            position_size_multiplier *= self.drawdown_control.position_size_multiplier
            
            # Apply regime-based reduction
            if regime == RiskRegime.HIGH_VOL_BULLISH or regime == RiskRegime.HIGH_VOL_BEARISH:
                position_size_multiplier *= self.portfolio_limits.high_vol_position_reduction
                warnings.append(f"High volatility regime: position size reduced by 50%")
            elif regime == RiskRegime.EXTREME_VOLATILITY or regime == RiskRegime.CRISIS:
                position_size_multiplier *= self.portfolio_limits.extreme_vol_position_reduction
                warnings.append(f"Extreme volatility regime: position size reduced by 75%")
            
            # Check leverage limit
            current_leverage = portfolio_metrics.leverage_ratio
            if current_leverage >= self.portfolio_limits.max_portfolio_leverage * 0.9:
                position_size_multiplier *= 0.5
                warnings.append(
                    f"Portfolio leverage at {current_leverage:.2f}x (limit {self.portfolio_limits.max_portfolio_leverage}x)"
                )
            
            if current_leverage >= self.portfolio_limits.max_portfolio_leverage:
                rejections.append("Portfolio leverage limit exceeded")
            
            # Check VaR limit
            if portfolio_metrics.var_1d > self.portfolio_limits.max_portfolio_var_percent:
                rejections.append(
                    f"Portfolio VaR {portfolio_metrics.var_1d:.2f}% exceeds limit {self.portfolio_limits.max_portfolio_var_percent}%"
                )
            
            # Step 7: Check concentration limits
            concentration_multiplier = await self._check_concentration_limits(
                symbol, strategy_id, requested_size_usd * position_size_multiplier,
                portfolio_metrics, positions
            )
            
            if concentration_multiplier < 1.0:
                warnings.append(f"Concentration limits: position size reduced by {(1-concentration_multiplier)*100:.0f}%")
            
            position_size_multiplier *= concentration_multiplier
            
            if concentration_multiplier == 0.0:
                rejections.append("Concentration limits would be exceeded")
            
            # Step 8: Check asset class exposure
            asset_class = get_asset_class(symbol)
            exposure_check = await self._check_asset_class_exposure(
                asset_class, requested_size_usd * position_size_multiplier, portfolio_metrics
            )
            
            if not exposure_check['allowed']:
                rejections.append(exposure_check['reason'])
                position_size_multiplier = 0.0
            elif exposure_check['reduction'] < 1.0:
                warnings.append(exposure_check['reason'])
                position_size_multiplier *= exposure_check['reduction']
            
            # Step 9: Check correlation exposure
            if correlation_risk.correlation_risk_score > 80:
                corr_multiplier = 0.5
                position_size_multiplier *= corr_multiplier
                warnings.append("Very high correlation with existing positions: size reduced by 50%")
            
            # Step 10: Calculate final risk score
            risk_score = self._calculate_composite_risk_score(
                risk_factors, portfolio_metrics, correlation_risk
            )
            
            # Step 11: Get dynamic stop-loss parameters
            stop_params = await self._get_stop_loss_params(symbol, volatility)
            
            # Step 12: Make approval decision
            approved = len(rejections) == 0 and position_size_multiplier > 0.1
            
            if not approved and len(rejections) == 0:
                rejections.append("Position size reduced below minimum viable threshold")
            
            # Generate recommendations
            if approved:
                recommendations.append(
                    f"Position approved with {position_size_multiplier*100:.0f}% of requested size"
                )
                recommendations.append(
                    f"Stop-loss: {stop_params.adjusted_stop_percent:.2f}% ({stop_params.reasoning})"
                )
            
            return RiskApprovalResult(
                approved=approved,
                position_size_adjustment=position_size_multiplier,
                stop_loss_params=stop_params,
                risk_score=risk_score,
                risk_factors=risk_factors,
                warnings=warnings,
                rejections=rejections,
                recommendations=recommendations,
                metadata={
                    'regime': regime.value,
                    'drawdown': self.drawdown_control.current_drawdown_percent,
                    'leverage': current_leverage,
                    'var_1d': portfolio_metrics.var_1d,
                    'correlation_score': correlation_risk.correlation_risk_score
                }
            )
            
        except Exception as e:
            logger.error(f"Error in position approval: {e}", exc_info=True)
            return RiskApprovalResult(
                approved=False,
                position_size_adjustment=0.0,
                stop_loss_params=await self._get_stop_loss_params(symbol, volatility),
                risk_score=100.0,
                risk_factors={'error': 1.0},
                warnings=[],
                rejections=[f"Risk approval error: {str(e)}"],
                recommendations=["Review system logs and retry"],
                metadata={}
            )
    
    
    async def adjust_existing_positions(self) -> Dict[str, any]:
        """
        Periodically review and adjust existing positions based on:
        - Portfolio drawdown
        - Volatility regime changes
        - Correlation shifts
        - Exposure limit breaches
        
        Returns summary of adjustments made
        """
        adjustments = {
            'stops_tightened': [],
            'positions_reduced': [],
            'positions_closed': [],
            'warnings_issued': [],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # Update drawdown state
            await self._update_drawdown_control()
            
            # Get current positions
            positions = await self.database.get_all_active_positions()
            
            if not positions:
                return adjustments
            
            # Circuit breaker Level 3: Close all positions
            if self.drawdown_control.circuit_breaker_level == CircuitBreakerLevel.LEVEL_3:
                logger.critical(
                    f"Circuit breaker LEVEL 3 triggered at {self.drawdown_control.current_drawdown_percent:.2f}% drawdown"
                )
                
                for position in positions:
                    await self._close_position(position['id'], "Circuit breaker Level 3")
                    adjustments['positions_closed'].append({
                        'symbol': position['symbol'],
                        'reason': 'circuit_breaker_level_3'
                    })
                
                return adjustments
            
            # Get portfolio metrics and regime
            portfolio_metrics = await self.portfolio_controller.calculate_risk_metrics()
            regime = await self._determine_risk_regime()
            
            # Check each position
            for position in positions:
                symbol = position['symbol']
                position_id = position['id']
                
                # Get current volatility
                volatility = await self.database.get_symbol_volatility(
                    symbol, settings.VOLATILITY_LOOKBACK_DAYS
                )
                
                # Check if stop-loss needs tightening
                stop_adjustment = await self._evaluate_stop_adjustment(
                    position, volatility, regime, portfolio_metrics
                )
                
                if stop_adjustment['action'] == 'tighten':
                    await self.stop_loss_manager.update_stop_loss(
                        position_id, stop_adjustment['new_stop_price']
                    )
                    adjustments['stops_tightened'].append({
                        'symbol': symbol,
                        'old_stop': stop_adjustment['old_stop'],
                        'new_stop': stop_adjustment['new_stop_price'],
                        'reason': stop_adjustment['reason']
                    })
                
                # Check if position should be reduced
                reduction = await self._evaluate_position_reduction(
                    position, portfolio_metrics, regime
                )
                
                if reduction['should_reduce']:
                    await self._reduce_position(
                        position_id, reduction['reduction_percent'], reduction['reason']
                    )
                    adjustments['positions_reduced'].append({
                        'symbol': symbol,
                        'reduction_percent': reduction['reduction_percent'],
                        'reason': reduction['reason']
                    })
            
            # Issue warnings if needed
            if portfolio_metrics.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                adjustments['warnings_issued'].append({
                    'level': portfolio_metrics.risk_level.value,
                    'message': f"Portfolio risk level: {portfolio_metrics.risk_level.value}",
                    'risk_score': portfolio_metrics.risk_score
                })
            
            logger.info(
                "Position adjustments completed",
                stops_tightened=len(adjustments['stops_tightened']),
                positions_reduced=len(adjustments['positions_reduced']),
                positions_closed=len(adjustments['positions_closed'])
            )
            
            return adjustments
            
        except Exception as e:
            logger.error(f"Error adjusting positions: {e}", exc_info=True)
            return adjustments
    
    
    async def _update_drawdown_control(self):
        """Update drawdown monitoring and circuit breaker state"""
        try:
            # Get current portfolio value
            portfolio_value = await self.database.get_total_portfolio_value()
            
            # Get peak value (all-time high)
            peak_value = await self.database.get_peak_portfolio_value()
            
            if peak_value is None or portfolio_value > peak_value:
                # New peak
                await self.database.update_peak_portfolio_value(portfolio_value)
                peak_value = portfolio_value
            
            # Calculate drawdown
            drawdown_percent = ((peak_value - portfolio_value) / peak_value) * 100
            
            # Determine circuit breaker level
            if drawdown_percent >= 20.0:
                level = CircuitBreakerLevel.LEVEL_3
                positions_allowed = False
                size_multiplier = 0.0
                actions = ["CLOSE_ALL_POSITIONS", "STOP_TRADING"]
            elif drawdown_percent >= 15.0:
                level = CircuitBreakerLevel.LEVEL_2
                positions_allowed = False
                size_multiplier = 0.0
                actions = ["NO_NEW_POSITIONS", "REVIEW_STRATEGY"]
            elif drawdown_percent >= 10.0:
                level = CircuitBreakerLevel.LEVEL_1
                positions_allowed = True
                size_multiplier = 0.5
                actions = ["REDUCE_POSITION_SIZES", "TIGHTEN_STOPS"]
            elif drawdown_percent >= 5.0:
                level = CircuitBreakerLevel.WARNING
                positions_allowed = True
                size_multiplier = 0.75
                actions = ["MONITOR_CLOSELY", "CONSIDER_REDUCING_RISK"]
            else:
                level = CircuitBreakerLevel.NONE
                positions_allowed = True
                size_multiplier = 1.0
                actions = []
            
            self.drawdown_control = DrawdownControl(
                current_portfolio_value=portfolio_value,
                peak_portfolio_value=peak_value,
                current_drawdown_percent=drawdown_percent,
                circuit_breaker_level=level,
                positions_allowed=positions_allowed,
                position_size_multiplier=size_multiplier,
                time_until_reset=None,
                actions_taken=actions,
                last_updated=datetime.now(timezone.utc)
            )
            
            # Log significant drawdown events
            if level != CircuitBreakerLevel.NONE:
                logger.warning(
                    f"Drawdown control activated: {level.value}",
                    drawdown_percent=drawdown_percent,
                    portfolio_value=portfolio_value,
                    peak_value=peak_value
                )
            
        except Exception as e:
            logger.error(f"Error updating drawdown control: {e}", exc_info=True)
            # Safe defaults on error
            self.drawdown_control = DrawdownControl(
                current_portfolio_value=0.0,
                peak_portfolio_value=0.0,
                current_drawdown_percent=0.0,
                circuit_breaker_level=CircuitBreakerLevel.NONE,
                positions_allowed=True,
                position_size_multiplier=1.0,
                time_until_reset=None,
                actions_taken=[],
                last_updated=datetime.now(timezone.utc)
            )
    
    
    async def _determine_risk_regime(self, volatility: Optional[float] = None) -> RiskRegime:
        """
        Determine current market risk regime based on:
        - Volatility levels
        - Market sentiment
        - Correlation patterns
        - Recent price action
        """
        try:
            # Get market-wide volatility if not provided
            if volatility is None:
                volatility = await self.database.get_market_volatility()
            
            # Get sentiment data from market_data_service
            sentiment_data = await self._get_market_sentiment()
            
            # Get recent returns
            returns = await self.database.get_recent_market_returns(days=30)
            
            # Classify volatility level
            if volatility > 0.6:  # 60% annualized
                vol_level = "extreme"
            elif volatility > 0.4:  # 40% annualized
                vol_level = "high"
            else:
                vol_level = "low"
            
            # Classify market direction
            avg_return = np.mean(returns) if returns else 0
            if avg_return > 0.001:  # Positive trend
                direction = "bullish"
            elif avg_return < -0.001:  # Negative trend
                direction = "bearish"
            else:
                direction = "neutral"
            
            # Combine into regime
            if vol_level == "extreme" or sentiment_data.get('fear_greed', 50) < 20:
                regime = RiskRegime.CRISIS
            elif vol_level == "high" and direction == "bullish":
                regime = RiskRegime.HIGH_VOL_BULLISH
            elif vol_level == "high" and direction == "bearish":
                regime = RiskRegime.HIGH_VOL_BEARISH
            elif vol_level == "low" and direction == "bullish":
                regime = RiskRegime.LOW_VOL_BULLISH
            elif vol_level == "low" and direction == "bearish":
                regime = RiskRegime.LOW_VOL_BEARISH
            else:
                regime = RiskRegime.LOW_VOL_BULLISH  # Default
            
            self.current_regime = regime
            return regime
            
        except Exception as e:
            logger.error(f"Error determining risk regime: {e}", exc_info=True)
            return RiskRegime.LOW_VOL_BULLISH  # Safe default
    
    
    async def _get_market_sentiment(self) -> Dict[str, any]:
        """Fetch market sentiment data from market_data_service"""
        try:
            # This would call the market_data_service API
            # For now, return placeholder
            return {
                'fear_greed': 50,
                'sentiment_score': 0.0,
                'confidence': 0.5
            }
        except Exception as e:
            logger.error(f"Error fetching sentiment: {e}")
            return {'fear_greed': 50, 'sentiment_score': 0.0, 'confidence': 0.0}
    
    
    async def _assess_correlation_risk(
        self, 
        new_symbol: str,
        existing_positions: List[Dict]
    ) -> CorrelationRiskMetrics:
        """
        Assess correlation risk of adding new position to portfolio
        
        Analyzes:
        - Correlation with existing positions
        - Diversification benefit
        - Correlation clusters
        - Effective number of independent bets
        """
        try:
            if not existing_positions:
                # No positions = perfect diversification
                return CorrelationRiskMetrics(
                    portfolio_correlation=0.0,
                    diversification_ratio=1.0,
                    correlation_clusters={},
                    effective_assets=1.0,
                    correlation_risk_score=0.0,
                    recommendations=["First position - no correlation risk"]
                )
            
            # Get correlation matrix
            await self._update_correlation_matrix(new_symbol, existing_positions)
            
            if self._correlation_matrix is None:
                # Fallback if correlation data unavailable
                return CorrelationRiskMetrics(
                    portfolio_correlation=0.5,
                    diversification_ratio=0.8,
                    correlation_clusters={},
                    effective_assets=float(len(existing_positions)),
                    correlation_risk_score=50.0,
                    recommendations=["Correlation data unavailable - assume moderate risk"]
                )
            
            # Calculate metrics
            avg_correlation = np.mean(self._correlation_matrix[np.triu_indices_from(self._correlation_matrix, k=1)])
            
            # Find correlation clusters (assets with correlation > 0.7)
            clusters = self._identify_correlation_clusters(0.7)
            
            # Calculate effective number of assets (inverse of average pairwise correlation)
            effective_n = len(existing_positions) / (1 + (len(existing_positions) - 1) * avg_correlation)
            
            # Diversification ratio (theoretical / actual volatility)
            diversification_ratio = effective_n / len(existing_positions)
            
            # Risk score (0-100): higher correlation = higher score
            correlation_risk_score = min(100, avg_correlation * 150)
            
            # Generate recommendations
            recommendations = []
            if correlation_risk_score > 80:
                recommendations.append("Very high correlation - consider different asset class")
            elif correlation_risk_score > 60:
                recommendations.append("High correlation - monitor exposure closely")
            
            if len(clusters) > 0:
                recommendations.append(f"Found {len(clusters)} correlation clusters")
            
            if effective_n < 2.0:
                recommendations.append("Low diversification - portfolio acts like 1-2 assets")
            
            return CorrelationRiskMetrics(
                portfolio_correlation=float(avg_correlation),
                diversification_ratio=float(diversification_ratio),
                correlation_clusters=clusters,
                effective_assets=float(effective_n),
                correlation_risk_score=float(correlation_risk_score),
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"Error assessing correlation risk: {e}", exc_info=True)
            return CorrelationRiskMetrics(
                portfolio_correlation=0.5,
                diversification_ratio=0.8,
                correlation_clusters={},
                effective_assets=float(len(existing_positions)) if existing_positions else 1.0,
                correlation_risk_score=50.0,
                recommendations=["Error calculating correlation risk"]
            )
    
    
    async def _update_correlation_matrix(self, new_symbol: str, positions: List[Dict]):
        """Fetch and cache correlation matrix from market_data_service"""
        try:
            # Check if cache is still valid (refresh every hour)
            if (self._last_correlation_update is not None and 
                datetime.now(timezone.utc) - self._last_correlation_update < timedelta(hours=1)):
                return
            
            # Get symbols
            symbols = [pos['symbol'] for pos in positions]
            if new_symbol not in symbols:
                symbols.append(new_symbol)
            
            # Fetch correlation data from market_data_service
            # This would call the correlation API endpoint
            # For now, simulate with random data
            n = len(symbols)
            correlations = np.random.uniform(0.3, 0.8, size=(n, n))
            correlations = (correlations + correlations.T) / 2  # Make symmetric
            np.fill_diagonal(correlations, 1.0)
            
            self._correlation_matrix = correlations
            self._correlation_symbols = symbols
            self._last_correlation_update = datetime.now(timezone.utc)
            
        except Exception as e:
            logger.error(f"Error updating correlation matrix: {e}", exc_info=True)
            self._correlation_matrix = None
    
    
    def _identify_correlation_clusters(self, threshold: float = 0.7) -> Dict[str, List[str]]:
        """Identify groups of highly correlated assets"""
        if self._correlation_matrix is None:
            return {}
        
        clusters = {}
        n = len(self._correlation_symbols)
        
        for i in range(n):
            highly_correlated = []
            for j in range(n):
                if i != j and self._correlation_matrix[i, j] > threshold:
                    highly_correlated.append(self._correlation_symbols[j])
            
            if highly_correlated:
                clusters[self._correlation_symbols[i]] = highly_correlated
        
        return clusters
    
    
    async def _check_concentration_limits(
        self,
        symbol: str,
        strategy_id: str,
        position_size_usd: float,
        portfolio_metrics: RiskMetrics,
        positions: List[Dict]
    ) -> float:
        """
        Check concentration limits and return size multiplier
        
        Returns value between 0.0 and 1.0
        """
        multiplier = 1.0
        
        # Single position limit
        position_percent = (position_size_usd / portfolio_metrics.total_portfolio_value) * 100
        if position_percent > self.portfolio_limits.max_single_position_percent:
            multiplier = self.portfolio_limits.max_single_position_percent / position_percent
        
        # Strategy concentration
        strategy_exposure = sum(
            pos['size_usd'] for pos in positions 
            if pos.get('strategy_id') == strategy_id
        )
        strategy_percent = ((strategy_exposure + position_size_usd) / 
                          portfolio_metrics.total_portfolio_value) * 100
        
        if strategy_percent > self.portfolio_limits.max_single_strategy_percent:
            strategy_multiplier = max(
                0, 
                (self.portfolio_limits.max_single_strategy_percent * 
                 portfolio_metrics.total_portfolio_value - strategy_exposure) / position_size_usd
            )
            multiplier = min(multiplier, strategy_multiplier)
        
        return max(0.0, multiplier)
    
    
    async def _check_asset_class_exposure(
        self,
        asset_class: str,
        position_size_usd: float,
        portfolio_metrics: RiskMetrics
    ) -> Dict[str, any]:
        """Check asset class exposure limits"""
        current_exposure = portfolio_metrics.sector_concentration.get(asset_class, 0.0)
        new_exposure_percent = ((current_exposure * portfolio_metrics.total_portfolio_value + 
                                position_size_usd) / portfolio_metrics.total_portfolio_value) * 100
        
        limits = {
            'crypto': self.portfolio_limits.max_crypto_exposure_percent,
            'defi': self.portfolio_limits.max_defi_exposure_percent,
            'altcoin': self.portfolio_limits.max_altcoin_exposure_percent
        }
        
        limit = limits.get(asset_class, 100.0)
        
        if new_exposure_percent > limit:
            return {
                'allowed': False,
                'reduction': 0.0,
                'reason': f"{asset_class} exposure would exceed {limit}% limit"
            }
        elif new_exposure_percent > limit * 0.9:
            return {
                'allowed': True,
                'reduction': 0.5,
                'reason': f"{asset_class} exposure approaching {limit}% limit"
            }
        else:
            return {
                'allowed': True,
                'reduction': 1.0,
                'reason': f"{asset_class} exposure within limits"
            }
    
    
    async def _get_stop_loss_params(
        self, 
        symbol: str, 
        volatility: Optional[float]
    ) -> DynamicStopLossParams:
        """
        Calculate dynamic stop-loss parameters based on volatility regime
        """
        if volatility is None:
            volatility = await self.database.get_symbol_volatility(
                symbol, settings.VOLATILITY_LOOKBACK_DAYS
            )
        
        # Base stop-loss percent (from config)
        base_stop = settings.DEFAULT_STOP_LOSS_PERCENT
        
        # Adjust based on regime
        if self.current_regime == RiskRegime.LOW_VOL_BULLISH:
            multiplier = 1.0
            trailing_dist = 0.02
            atr_mult = 2.0
            time_decay = 0.1
            breakeven_trigger = 0.02
            reasoning = "Low volatility bullish market - standard stops"
            
        elif self.current_regime == RiskRegime.LOW_VOL_BEARISH:
            multiplier = 0.8
            trailing_dist = 0.015
            atr_mult = 1.5
            time_decay = 0.15
            breakeven_trigger = 0.015
            reasoning = "Low volatility bearish market - tighter stops"
            
        elif self.current_regime == RiskRegime.HIGH_VOL_BULLISH:
            multiplier = 1.5
            trailing_dist = 0.04
            atr_mult = 3.0
            time_decay = 0.05
            breakeven_trigger = 0.03
            reasoning = "High volatility bullish market - wider stops to avoid whipsaw"
            
        elif self.current_regime == RiskRegime.HIGH_VOL_BEARISH:
            multiplier = 1.2
            trailing_dist = 0.03
            atr_mult = 2.5
            time_decay = 0.08
            breakeven_trigger = 0.025
            reasoning = "High volatility bearish market - moderate stops"
            
        elif self.current_regime == RiskRegime.EXTREME_VOLATILITY:
            multiplier = 2.0
            trailing_dist = 0.06
            atr_mult = 4.0
            time_decay = 0.02
            breakeven_trigger = 0.05
            reasoning = "Extreme volatility - very wide stops to avoid premature exit"
            
        else:  # CRISIS
            multiplier = 0.5
            trailing_dist = 0.01
            atr_mult = 1.0
            time_decay = 0.2
            breakeven_trigger = 0.01
            reasoning = "Crisis mode - very tight stops for capital preservation"
        
        # Further adjust for asset-specific volatility
        vol_adjustment = 1.0 + (volatility - 0.3)  # Assume 0.3 is normal
        
        adjusted_stop = base_stop * multiplier * vol_adjustment
        
        # Enforce min/max bounds
        adjusted_stop = max(0.005, min(0.15, adjusted_stop))  # 0.5% to 15%
        
        return DynamicStopLossParams(
            regime=self.current_regime,
            base_stop_percent=base_stop,
            adjusted_stop_percent=adjusted_stop,
            trailing_distance_percent=trailing_dist,
            atr_multiplier=atr_mult,
            time_decay_rate=time_decay,
            breakeven_trigger_percent=breakeven_trigger,
            volatility_multiplier=vol_adjustment,
            reasoning=reasoning
        )
    
    
    def _calculate_composite_risk_score(
        self,
        risk_factors: Dict[str, float],
        portfolio_metrics: RiskMetrics,
        correlation_risk: CorrelationRiskMetrics
    ) -> float:
        """
        Calculate composite risk score (0-100)
        Higher score = higher risk
        """
        scores = []
        weights = []
        
        # Regime risk
        if 'regime' in risk_factors:
            scores.append(risk_factors['regime'] * 100)
            weights.append(0.2)
        
        # Correlation risk
        scores.append(correlation_risk.correlation_risk_score)
        weights.append(0.25)
        
        # Portfolio VaR
        var_score = min(100, (portfolio_metrics.var_1d / self.portfolio_limits.max_portfolio_var_percent) * 100)
        scores.append(var_score)
        weights.append(0.2)
        
        # Drawdown risk
        drawdown_score = min(100, (self.drawdown_control.current_drawdown_percent / 
                                   self.portfolio_limits.max_drawdown_percent) * 100)
        scores.append(drawdown_score)
        weights.append(0.15)
        
        # Leverage risk
        leverage_score = min(100, (portfolio_metrics.leverage_ratio / 
                                  self.portfolio_limits.max_portfolio_leverage) * 100)
        scores.append(leverage_score)
        weights.append(0.1)
        
        # Concentration risk
        concentration_score = min(100, portfolio_metrics.concentration_hhi * 100)
        scores.append(concentration_score)
        weights.append(0.1)
        
        # Weighted average
        composite_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        
        return min(100, max(0, composite_score))
    
    
    def _regime_to_score(self, regime: RiskRegime) -> float:
        """Convert regime to risk score (0-1)"""
        regime_scores = {
            RiskRegime.LOW_VOL_BULLISH: 0.2,
            RiskRegime.LOW_VOL_BEARISH: 0.4,
            RiskRegime.HIGH_VOL_BULLISH: 0.6,
            RiskRegime.HIGH_VOL_BEARISH: 0.7,
            RiskRegime.EXTREME_VOLATILITY: 0.9,
            RiskRegime.CRISIS: 1.0
        }
        return regime_scores.get(regime, 0.5)
    
    
    async def _evaluate_stop_adjustment(
        self,
        position: Dict,
        volatility: float,
        regime: RiskRegime,
        portfolio_metrics: RiskMetrics
    ) -> Dict[str, any]:
        """Evaluate if stop-loss should be adjusted"""
        # Get current stop
        current_stop = position.get('stop_loss_price', 0.0)
        entry_price = position['entry_price']
        current_price = position['current_price']
        
        # Get dynamic params
        params = await self._get_stop_loss_params(position['symbol'], volatility)
        
        # Calculate new recommended stop
        new_stop = current_price * (1 - params.adjusted_stop_percent)
        
        # Only tighten stops, never widen
        if new_stop > current_stop and current_price > entry_price:
            return {
                'action': 'tighten',
                'old_stop': current_stop,
                'new_stop_price': new_stop,
                'reason': f"Regime change to {regime.value}"
            }
        
        return {'action': 'none'}
    
    
    async def _evaluate_position_reduction(
        self,
        position: Dict,
        portfolio_metrics: RiskMetrics,
        regime: RiskRegime
    ) -> Dict[str, any]:
        """Evaluate if position should be reduced"""
        # Reduce positions in crisis
        if regime == RiskRegime.CRISIS:
            return {
                'should_reduce': True,
                'reduction_percent': 50.0,
                'reason': 'Crisis regime - reducing exposure'
            }
        
        # Reduce if portfolio VaR exceeded
        if portfolio_metrics.var_1d > self.portfolio_limits.max_portfolio_var_percent * 1.2:
            return {
                'should_reduce': True,
                'reduction_percent': 30.0,
                'reason': 'Portfolio VaR exceeded - reducing positions'
            }
        
        return {'should_reduce': False}
    
    
    async def _close_position(self, position_id: str, reason: str):
        """Close a position (circuit breaker triggered)"""
        try:
            await self.database.close_position(position_id, reason)
            logger.warning(f"Position {position_id} closed: {reason}")
        except Exception as e:
            logger.error(f"Error closing position {position_id}: {e}", exc_info=True)
    
    
    async def _reduce_position(self, position_id: str, reduction_percent: float, reason: str):
        """Reduce a position size"""
        try:
            await self.database.reduce_position(position_id, reduction_percent, reason)
            logger.info(f"Position {position_id} reduced by {reduction_percent}%: {reason}")
        except Exception as e:
            logger.error(f"Error reducing position {position_id}: {e}", exc_info=True)
    
    
    async def get_risk_dashboard_data(self) -> Dict[str, any]:
        """
        Get comprehensive risk dashboard data
        
        Returns all current risk metrics, limits, and status for monitoring
        """
        try:
            # Update state
            await self._update_drawdown_control()
            
            # Get portfolio metrics
            portfolio_metrics = await self.portfolio_controller.calculate_risk_metrics()
            
            # Get positions
            positions = await self.database.get_all_active_positions()
            
            # Calculate correlation risk for portfolio
            correlation_risk = await self._assess_correlation_risk(
                '', positions  # Empty symbol for portfolio-wide assessment
            )
            
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'circuit_breaker': {
                    'level': self.drawdown_control.circuit_breaker_level.value,
                    'drawdown_percent': self.drawdown_control.current_drawdown_percent,
                    'positions_allowed': self.drawdown_control.positions_allowed,
                    'size_multiplier': self.drawdown_control.position_size_multiplier,
                    'actions': self.drawdown_control.actions_taken
                },
                'risk_regime': self.current_regime.value,
                'portfolio_metrics': {
                    'total_value': portfolio_metrics.total_portfolio_value,
                    'leverage': portfolio_metrics.leverage_ratio,
                    'var_1d': portfolio_metrics.var_1d,
                    'var_5d': portfolio_metrics.var_5d,
                    'drawdown': portfolio_metrics.current_drawdown,
                    'risk_score': portfolio_metrics.risk_score,
                    'risk_level': portfolio_metrics.risk_level.value
                },
                'correlation_metrics': {
                    'avg_correlation': correlation_risk.portfolio_correlation,
                    'diversification_ratio': correlation_risk.diversification_ratio,
                    'effective_assets': correlation_risk.effective_assets,
                    'correlation_risk_score': correlation_risk.correlation_risk_score
                },
                'limits': {
                    'max_leverage': self.portfolio_limits.max_portfolio_leverage,
                    'max_var': self.portfolio_limits.max_portfolio_var_percent,
                    'max_drawdown': self.portfolio_limits.max_drawdown_percent,
                    'max_single_position': self.portfolio_limits.max_single_position_percent,
                    'max_sector': self.portfolio_limits.max_sector_exposure_percent
                },
                'active_positions': len(positions)
            }
            
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}", exc_info=True)
            return {'error': str(e)}
