"""
Portfolio Risk Controls

This module implements comprehensive portfolio-level risk monitoring,
correlation analysis, exposure limits, and risk metrics dashboards.
"""

import asyncio
import math
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Union
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, field
from enum import Enum
import structlog

from config import settings, get_asset_class, get_risk_multiplier
from database import RiskManagementDatabase

logger = structlog.get_logger()

class RiskLevel(Enum):
    """Portfolio risk levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertType(Enum):
    """Risk alert types"""
    EXPOSURE_LIMIT = "exposure_limit"
    CORRELATION_BREACH = "correlation_breach"
    VAR_EXCEEDED = "var_exceeded"
    DRAWDOWN_WARNING = "drawdown_warning"
    CONCENTRATION_RISK = "concentration_risk"
    LIQUIDITY_RISK = "liquidity_risk"
    VOLATILITY_SPIKE = "volatility_spike"

@dataclass
class RiskMetrics:
    """Portfolio risk metrics snapshot"""
    timestamp: datetime
    total_portfolio_value: float
    total_exposure: float
    cash_balance: float
    leverage_ratio: float
    
    # Risk measures
    var_1d: float  # 1-day Value at Risk
    var_5d: float  # 5-day Value at Risk
    expected_shortfall: float  # Conditional VaR
    max_drawdown: float
    current_drawdown: float
    
    # Diversification metrics
    concentration_hhi: float  # Herfindahl-Hirschman Index
    correlation_risk: float
    sector_concentration: Dict[str, float]
    
    # Individual position metrics
    largest_position_percent: float
    positions_over_5pct: int
    positions_over_10pct: int
    
    # Liquidity metrics
    avg_liquidity_score: float
    illiquid_positions_percent: float
    
    risk_level: RiskLevel
    risk_score: float  # 0-100 scale

@dataclass
class RiskAlert:
    """Risk management alert"""
    id: str
    alert_type: AlertType
    severity: RiskLevel
    title: str
    message: str
    symbol: Optional[str]
    current_value: float
    threshold_value: float
    recommendation: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    metadata: Dict = field(default_factory=dict)

@dataclass
class ExposureLimits:
    """Portfolio exposure limits"""
    max_single_position: float
    max_sector_exposure: Dict[str, float]
    max_correlation_exposure: float
    max_leverage: float
    max_var_percent: float
    max_drawdown_percent: float

@dataclass
class PortfolioState:
    """Current portfolio state"""
    positions: List[Dict]
    total_value: float
    available_cash: float
    unrealized_pnl: float
    realized_pnl: float
    exposure_by_asset: Dict[str, float]
    exposure_by_sector: Dict[str, float]
    correlation_matrix: Dict[str, float]
    
class PortfolioRiskController:
    """
    Comprehensive portfolio risk management system
    
    Features:
    - Real-time risk monitoring and alerting
    - Correlation analysis and limits
    - Value at Risk (VaR) calculations
    - Drawdown tracking and limits
    - Concentration risk management
    - Liquidity risk assessment
    - Automated risk rebalancing
    """
    
    def __init__(self, database: RiskManagementDatabase):
        self.database = database
        self.current_alerts: Dict[str, RiskAlert] = {}
        
    async def calculate_portfolio_risk(self) -> RiskMetrics:
        """
        Calculate comprehensive portfolio risk metrics
        
        Returns:
            RiskMetrics object with all risk measurements
        """
        try:
            logger.info("Calculating portfolio risk metrics")
            
            # Get current portfolio state
            portfolio_state = await self._get_portfolio_state()
            
            # Calculate basic metrics
            total_value = portfolio_state.total_value
            total_exposure = sum(portfolio_state.exposure_by_asset.values())
            leverage_ratio = total_exposure / total_value if total_value > 0 else 0
            
            # Calculate VaR metrics
            var_1d = await self._calculate_var(portfolio_state, days=1)
            var_5d = await self._calculate_var(portfolio_state, days=5)
            expected_shortfall = await self._calculate_expected_shortfall(portfolio_state)
            
            # Calculate drawdown metrics
            max_drawdown = await self.database.get_max_drawdown()
            current_drawdown = await self._calculate_current_drawdown(portfolio_state)
            
            # Calculate concentration metrics
            concentration_hhi = self._calculate_hhi(portfolio_state.exposure_by_asset)
            correlation_risk = await self._calculate_correlation_risk(portfolio_state)
            
            # Calculate position metrics
            position_metrics = self._calculate_position_metrics(portfolio_state)
            
            # Calculate liquidity metrics
            liquidity_metrics = await self._calculate_liquidity_metrics(portfolio_state)
            
            # Calculate overall risk level and score
            risk_score = self._calculate_risk_score({
                'var_1d': var_1d,
                'leverage': leverage_ratio,
                'concentration': concentration_hhi,
                'drawdown': current_drawdown,
                'correlation_risk': correlation_risk,
                'liquidity': liquidity_metrics['avg_score']
            })
            
            risk_level = self._determine_risk_level(risk_score)
            
            metrics = RiskMetrics(
                timestamp=datetime.now(timezone.utc),
                total_portfolio_value=total_value,
                total_exposure=total_exposure,
                cash_balance=portfolio_state.available_cash,
                leverage_ratio=leverage_ratio,
                var_1d=var_1d,
                var_5d=var_5d,
                expected_shortfall=expected_shortfall,
                max_drawdown=max_drawdown,
                current_drawdown=current_drawdown,
                concentration_hhi=concentration_hhi,
                correlation_risk=correlation_risk,
                sector_concentration=portfolio_state.exposure_by_sector,
                largest_position_percent=position_metrics['largest_percent'],
                positions_over_5pct=position_metrics['over_5pct'],
                positions_over_10pct=position_metrics['over_10pct'],
                avg_liquidity_score=liquidity_metrics['avg_score'],
                illiquid_positions_percent=liquidity_metrics['illiquid_percent'],
                risk_level=risk_level,
                risk_score=risk_score
            )
            
            # Store metrics in database
            await self.database.store_risk_metrics(metrics)
            
            logger.info(
                f"Portfolio risk calculated",
                risk_score=risk_score,
                risk_level=risk_level.value,
                var_1d=var_1d,
                leverage=leverage_ratio
            )
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating portfolio risk: {e}")
            raise
    
    async def check_risk_limits(self) -> List[RiskAlert]:
        """
        Check all risk limits and generate alerts
        
        Returns:
            List of active risk alerts
        """
        try:
            logger.info("Checking portfolio risk limits")
            
            alerts = []
            portfolio_state = await self._get_portfolio_state()
            
            # Check exposure limits
            alerts.extend(await self._check_exposure_limits(portfolio_state))
            
            # Check correlation limits
            alerts.extend(await self._check_correlation_limits(portfolio_state))
            
            # Check VaR limits
            alerts.extend(await self._check_var_limits(portfolio_state))
            
            # Check drawdown limits
            alerts.extend(await self._check_drawdown_limits(portfolio_state))
            
            # Check concentration limits
            alerts.extend(await self._check_concentration_limits(portfolio_state))
            
            # Check liquidity limits
            alerts.extend(await self._check_liquidity_limits(portfolio_state))
            
            # Store alerts in database
            for alert in alerts:
                await self.database.store_risk_alert(alert)
                self.current_alerts[alert.id] = alert
            
            logger.info(f"Risk limit check completed", alert_count=len(alerts))
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error checking risk limits: {e}")
            return []
    
    async def suggest_risk_rebalancing(self) -> List[Dict]:
        """
        Suggest portfolio rebalancing to reduce risk
        
        Returns:
            List of rebalancing suggestions
        """
        try:
            logger.info("Generating risk rebalancing suggestions")
            
            suggestions = []
            portfolio_state = await self._get_portfolio_state()
            risk_metrics = await self.calculate_portfolio_risk()
            
            # Suggest position size reductions for high-risk positions
            if risk_metrics.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                suggestions.extend(
                    await self._suggest_position_reductions(portfolio_state, risk_metrics)
                )
            
            # Suggest correlation reduction
            if risk_metrics.correlation_risk > settings.MAX_CORRELATION_EXPOSURE:
                suggestions.extend(
                    await self._suggest_correlation_reduction(portfolio_state)
                )
            
            # Suggest diversification improvements
            if risk_metrics.concentration_hhi > 0.3:  # High concentration
                suggestions.extend(
                    await self._suggest_diversification(portfolio_state)
                )
            
            # Suggest liquidity improvements
            if risk_metrics.illiquid_positions_percent > 20:  # >20% illiquid
                suggestions.extend(
                    await self._suggest_liquidity_improvements(portfolio_state)
                )
            
            logger.info(f"Generated {len(suggestions)} rebalancing suggestions")
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error generating rebalancing suggestions: {e}")
            return []
    
    async def monitor_real_time_risk(self, price_updates: Dict[str, float]) -> Dict:
        """
        Real-time risk monitoring with price updates
        
        Args:
            price_updates: Dictionary of symbol -> current price
            
        Returns:
            Risk monitoring summary
        """
        try:
            # Update position values with new prices
            updated_portfolio = await self._update_portfolio_values(price_updates)
            
            # Calculate quick risk metrics
            leverage = await self._calculate_current_leverage(updated_portfolio)
            var_estimate = await self._estimate_current_var(updated_portfolio)
            drawdown = await self._calculate_current_drawdown(updated_portfolio)
            
            # Check for immediate risk breaches
            breaches = []
            
            if leverage > settings.MAX_LEVERAGE_RATIO:
                breaches.append({
                    'type': 'leverage',
                    'current': leverage,
                    'limit': settings.MAX_LEVERAGE_RATIO
                })
            
            if var_estimate > settings.MAX_VAR_PERCENT:
                breaches.append({
                    'type': 'var',
                    'current': var_estimate,
                    'limit': settings.MAX_VAR_PERCENT
                })
            
            if drawdown > settings.MAX_DRAWDOWN_PERCENT:
                breaches.append({
                    'type': 'drawdown',
                    'current': drawdown,
                    'limit': settings.MAX_DRAWDOWN_PERCENT
                })
            
            # Generate alerts for breaches
            for breach in breaches:
                alert = await self._create_real_time_alert(breach, updated_portfolio)
                if alert:
                    await self.database.store_risk_alert(alert)
            
            return {
                'timestamp': datetime.now(timezone.utc),
                'portfolio_value': updated_portfolio.total_value,
                'leverage': leverage,
                'var_estimate': var_estimate,
                'drawdown': drawdown,
                'breaches': breaches,
                'risk_status': 'CRITICAL' if breaches else 'NORMAL'
            }
            
        except Exception as e:
            logger.error(f"Error in real-time risk monitoring: {e}")
            return {'error': str(e)}
    
    async def get_risk_dashboard_data(self) -> Dict:
        """
        Get comprehensive risk dashboard data
        
        Returns:
            Dictionary with all dashboard metrics
        """
        try:
            # Get current risk metrics
            risk_metrics = await self.calculate_portfolio_risk()
            
            # Get historical data
            historical_metrics = await self.database.get_historical_risk_metrics(days=30)
            
            # Get active alerts
            active_alerts = await self.database.get_active_risk_alerts()
            
            # Get correlation matrix
            correlation_matrix = await self.database.get_latest_correlation_matrix()
            
            # Calculate trend indicators
            trends = await self._calculate_risk_trends(historical_metrics)
            
            dashboard_data = {
                'current_metrics': risk_metrics,
                'historical_data': {
                    'risk_scores': [m.risk_score for m in historical_metrics],
                    'var_1d': [m.var_1d for m in historical_metrics],
                    'drawdowns': [m.current_drawdown for m in historical_metrics],
                    'timestamps': [m.timestamp for m in historical_metrics]
                },
                'active_alerts': active_alerts,
                'correlation_matrix': correlation_matrix,
                'trends': trends,
                'risk_limits': {
                    'max_var': settings.MAX_VAR_PERCENT,
                    'max_drawdown': settings.MAX_DRAWDOWN_PERCENT,
                    'max_leverage': settings.MAX_LEVERAGE_RATIO,
                    'max_position': settings.MAX_SINGLE_POSITION_PERCENT,
                    'max_correlation': settings.MAX_CORRELATION_EXPOSURE
                }
            }
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            return {'error': str(e)}
    
    # Private helper methods
    
    async def _get_portfolio_state(self) -> PortfolioState:
        """Get current portfolio state"""
        try:
            positions = await self.database.get_current_positions()
            account_info = await self.database.get_account_balance()
            correlation_matrix = await self.database.get_latest_correlation_matrix()
            
            # Calculate exposures
            exposure_by_asset = {}
            exposure_by_sector = {}
            total_value = 0
            unrealized_pnl = 0
            
            for position in positions:
                symbol = position['symbol']
                value = position['current_value_usd']
                pnl = position.get('unrealized_pnl', 0)
                
                exposure_by_asset[symbol] = value
                total_value += value
                unrealized_pnl += pnl
                
                # Group by asset class/sector
                asset_class = get_asset_class(symbol)
                exposure_by_sector[asset_class] = exposure_by_sector.get(asset_class, 0) + value
            
            return PortfolioState(
                positions=positions,
                total_value=total_value,
                available_cash=account_info.get('available_balance_usd', 0),
                unrealized_pnl=unrealized_pnl,
                realized_pnl=account_info.get('realized_pnl', 0),
                exposure_by_asset=exposure_by_asset,
                exposure_by_sector=exposure_by_sector,
                correlation_matrix=correlation_matrix or {}
            )
            
        except Exception as e:
            logger.error(f"Error getting portfolio state: {e}")
            raise
    
    async def _calculate_var(self, portfolio_state: PortfolioState, days: int = 1, confidence: float = 0.05) -> float:
        """Calculate Value at Risk"""
        try:
            if not portfolio_state.positions:
                return 0.0
            
            # Get historical returns for portfolio positions
            portfolio_returns = []
            
            for position in portfolio_state.positions:
                symbol = position['symbol']
                weight = position['current_value_usd'] / portfolio_state.total_value
                
                # Get historical volatility (simplified)
                volatility = await self.database.get_symbol_volatility(symbol, days=30)
                
                # Estimate daily returns (normally distributed assumption)
                daily_return_std = volatility / math.sqrt(days)
                portfolio_returns.append(weight * daily_return_std)
            
            # Portfolio volatility (simplified - assumes zero correlation)
            portfolio_volatility = math.sqrt(sum(r**2 for r in portfolio_returns))
            
            # VaR calculation (normal distribution assumption)
            from scipy.stats import norm
            var_multiplier = norm.ppf(confidence)  # 5% confidence = -1.645
            
            var_amount = abs(var_multiplier) * portfolio_volatility * portfolio_state.total_value * math.sqrt(days)
            
            return var_amount
            
        except Exception as e:
            logger.error(f"Error calculating VaR: {e}")
            # Fallback: simple volatility estimate
            return portfolio_state.total_value * 0.02 * math.sqrt(days)  # 2% daily vol estimate
    
    async def _calculate_expected_shortfall(self, portfolio_state: PortfolioState) -> float:
        """Calculate Expected Shortfall (Conditional VaR)"""
        try:
            var_1d = await self._calculate_var(portfolio_state, days=1)
            # ES is typically 1.3x VaR for normal distribution
            return var_1d * 1.3
            
        except Exception as e:
            logger.error(f"Error calculating expected shortfall: {e}")
            return 0.0
    
    async def _calculate_current_drawdown(self, portfolio_state: PortfolioState) -> float:
        """Calculate current portfolio drawdown"""
        try:
            # Get portfolio high water mark
            high_water_mark = await self.database.get_portfolio_high_water_mark()
            
            if high_water_mark > 0:
                current_drawdown = (high_water_mark - portfolio_state.total_value) / high_water_mark
                return max(0, current_drawdown * 100)  # Return as percentage
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error calculating current drawdown: {e}")
            return 0.0
    
    def _calculate_hhi(self, exposures: Dict[str, float]) -> float:
        """Calculate Herfindahl-Hirschman Index for concentration"""
        try:
            if not exposures:
                return 0.0
            
            total_exposure = sum(exposures.values())
            if total_exposure == 0:
                return 0.0
            
            # Calculate HHI
            hhi = sum((exposure / total_exposure) ** 2 for exposure in exposures.values())
            
            return hhi
            
        except Exception as e:
            logger.error(f"Error calculating HHI: {e}")
            return 0.0
    
    async def _calculate_correlation_risk(self, portfolio_state: PortfolioState) -> float:
        """Calculate portfolio correlation risk"""
        try:
            if len(portfolio_state.positions) < 2:
                return 0.0
            
            total_corr_risk = 0.0
            total_pairs = 0
            
            # Calculate weighted average correlation
            for i, pos1 in enumerate(portfolio_state.positions):
                for j, pos2 in enumerate(portfolio_state.positions[i+1:], i+1):
                    symbol1 = pos1['symbol']
                    symbol2 = pos2['symbol']
                    
                    # Get correlation
                    corr_key1 = f"{symbol1}_{symbol2}"
                    corr_key2 = f"{symbol2}_{symbol1}"
                    
                    correlation = portfolio_state.correlation_matrix.get(
                        corr_key1, 
                        portfolio_state.correlation_matrix.get(corr_key2, 0.0)
                    )
                    
                    # Weight by position sizes
                    weight1 = pos1['current_value_usd'] / portfolio_state.total_value
                    weight2 = pos2['current_value_usd'] / portfolio_state.total_value
                    
                    weighted_corr = abs(correlation) * weight1 * weight2
                    total_corr_risk += weighted_corr
                    total_pairs += 1
            
            return (total_corr_risk / total_pairs) * 100 if total_pairs > 0 else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating correlation risk: {e}")
            return 0.0
    
    def _calculate_position_metrics(self, portfolio_state: PortfolioState) -> Dict:
        """Calculate position-related metrics"""
        try:
            if not portfolio_state.positions or portfolio_state.total_value == 0:
                return {'largest_percent': 0, 'over_5pct': 0, 'over_10pct': 0}
            
            position_percentages = [
                (pos['current_value_usd'] / portfolio_state.total_value) * 100 
                for pos in portfolio_state.positions
            ]
            
            return {
                'largest_percent': max(position_percentages) if position_percentages else 0,
                'over_5pct': sum(1 for pct in position_percentages if pct > 5),
                'over_10pct': sum(1 for pct in position_percentages if pct > 10)
            }
            
        except Exception as e:
            logger.error(f"Error calculating position metrics: {e}")
            return {'largest_percent': 0, 'over_5pct': 0, 'over_10pct': 0}
    
    async def _calculate_liquidity_metrics(self, portfolio_state: PortfolioState) -> Dict:
        """Calculate liquidity-related metrics"""
        try:
            if not portfolio_state.positions:
                return {'avg_score': 10.0, 'illiquid_percent': 0.0}
            
            liquidity_scores = []
            illiquid_value = 0.0
            
            for position in portfolio_state.positions:
                symbol = position['symbol']
                value = position['current_value_usd']
                
                # Get liquidity score (simplified)
                liquidity = await self.database.get_symbol_liquidity(symbol)
                score = min(10.0, max(0.0, liquidity / 10000))  # Scale to 0-10
                
                liquidity_scores.append(score)
                
                if score < 3.0:  # Consider illiquid if score < 3
                    illiquid_value += value
            
            avg_score = sum(liquidity_scores) / len(liquidity_scores) if liquidity_scores else 10.0
            illiquid_percent = (illiquid_value / portfolio_state.total_value) * 100 if portfolio_state.total_value > 0 else 0.0
            
            return {
                'avg_score': avg_score,
                'illiquid_percent': illiquid_percent
            }
            
        except Exception as e:
            logger.error(f"Error calculating liquidity metrics: {e}")
            return {'avg_score': 5.0, 'illiquid_percent': 0.0}
    
    def _calculate_risk_score(self, factors: Dict[str, float]) -> float:
        """Calculate overall portfolio risk score (0-100)"""
        try:
            # Risk factor weights
            weights = {
                'var_1d': 0.25,
                'leverage': 0.20,
                'concentration': 0.20,
                'drawdown': 0.15,
                'correlation_risk': 0.10,
                'liquidity': 0.10
            }
            
            # Normalize factors to 0-100 scale
            normalized_factors = {}
            
            # VaR as percentage of portfolio
            var_percent = (factors.get('var_1d', 0) / 1000000) * 100  # Assume 1M portfolio
            normalized_factors['var_1d'] = min(100, var_percent * 10)  # 10% VaR = 100 risk
            
            # Leverage
            normalized_factors['leverage'] = min(100, factors.get('leverage', 1) * 50)  # 2x leverage = 100 risk
            
            # Concentration (HHI)
            normalized_factors['concentration'] = min(100, factors.get('concentration', 0) * 200)  # 0.5 HHI = 100 risk
            
            # Drawdown
            normalized_factors['drawdown'] = min(100, factors.get('drawdown', 0) * 5)  # 20% drawdown = 100 risk
            
            # Correlation risk
            normalized_factors['correlation_risk'] = min(100, factors.get('correlation_risk', 0))
            
            # Liquidity (inverted - lower liquidity = higher risk)
            liquidity_score = factors.get('liquidity', 10)
            normalized_factors['liquidity'] = max(0, (10 - liquidity_score) * 10)
            
            # Calculate weighted score
            weighted_score = sum(
                normalized_factors.get(factor, 0) * weight 
                for factor, weight in weights.items()
            )
            
            return min(100, max(0, weighted_score))
            
        except Exception as e:
            logger.error(f"Error calculating risk score: {e}")
            return 50.0  # Neutral score on error
    
    def _determine_risk_level(self, risk_score: float) -> RiskLevel:
        """Determine risk level from risk score"""
        if risk_score >= 80:
            return RiskLevel.CRITICAL
        elif risk_score >= 60:
            return RiskLevel.HIGH
        elif risk_score >= 30:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    # Risk limit checking methods
    
    async def _check_exposure_limits(self, portfolio_state: PortfolioState) -> List[RiskAlert]:
        """Check position exposure limits"""
        alerts = []
        
        try:
            for position in portfolio_state.positions:
                symbol = position['symbol']
                value = position['current_value_usd']
                percentage = (value / portfolio_state.total_value) * 100 if portfolio_state.total_value > 0 else 0
                
                if percentage > settings.MAX_SINGLE_POSITION_PERCENT:
                    alert = RiskAlert(
                        id=f"exposure_{symbol}_{int(datetime.now().timestamp())}",
                        alert_type=AlertType.EXPOSURE_LIMIT,
                        severity=RiskLevel.HIGH if percentage > settings.MAX_SINGLE_POSITION_PERCENT * 1.5 else RiskLevel.MEDIUM,
                        title=f"Position Size Limit Exceeded",
                        message=f"{symbol} position ({percentage:.1f}%) exceeds limit ({settings.MAX_SINGLE_POSITION_PERCENT}%)",
                        symbol=symbol,
                        current_value=percentage,
                        threshold_value=settings.MAX_SINGLE_POSITION_PERCENT,
                        recommendation=f"Consider reducing {symbol} position by ${value - (portfolio_state.total_value * settings.MAX_SINGLE_POSITION_PERCENT / 100):,.0f}",
                        created_at=datetime.now(timezone.utc)
                    )
                    alerts.append(alert)
            
        except Exception as e:
            logger.error(f"Error checking exposure limits: {e}")
        
        return alerts
    
    async def _check_correlation_limits(self, portfolio_state: PortfolioState) -> List[RiskAlert]:
        """Check correlation limits"""
        alerts = []
        
        try:
            correlation_risk = await self._calculate_correlation_risk(portfolio_state)
            
            if correlation_risk > settings.MAX_CORRELATION_EXPOSURE:
                alert = RiskAlert(
                    id=f"correlation_{int(datetime.now().timestamp())}",
                    alert_type=AlertType.CORRELATION_BREACH,
                    severity=RiskLevel.HIGH,
                    title="High Portfolio Correlation Risk",
                    message=f"Portfolio correlation risk ({correlation_risk:.1f}%) exceeds limit ({settings.MAX_CORRELATION_EXPOSURE}%)",
                    symbol=None,
                    current_value=correlation_risk,
                    threshold_value=settings.MAX_CORRELATION_EXPOSURE,
                    recommendation="Consider diversifying into uncorrelated assets",
                    created_at=datetime.now(timezone.utc)
                )
                alerts.append(alert)
                
        except Exception as e:
            logger.error(f"Error checking correlation limits: {e}")
        
        return alerts
    
    async def _check_var_limits(self, portfolio_state: PortfolioState) -> List[RiskAlert]:
        """Check VaR limits"""
        alerts = []
        
        try:
            var_1d = await self._calculate_var(portfolio_state, days=1)
            var_percent = (var_1d / portfolio_state.total_value) * 100 if portfolio_state.total_value > 0 else 0
            
            if var_percent > settings.MAX_VAR_PERCENT:
                alert = RiskAlert(
                    id=f"var_{int(datetime.now().timestamp())}",
                    alert_type=AlertType.VAR_EXCEEDED,
                    severity=RiskLevel.HIGH,
                    title="Value at Risk Limit Exceeded",
                    message=f"1-day VaR ({var_percent:.1f}%) exceeds limit ({settings.MAX_VAR_PERCENT}%)",
                    symbol=None,
                    current_value=var_percent,
                    threshold_value=settings.MAX_VAR_PERCENT,
                    recommendation="Reduce position sizes or volatility exposure",
                    created_at=datetime.now(timezone.utc)
                )
                alerts.append(alert)
                
        except Exception as e:
            logger.error(f"Error checking VaR limits: {e}")
        
        return alerts
    
    async def _check_drawdown_limits(self, portfolio_state: PortfolioState) -> List[RiskAlert]:
        """Check drawdown limits"""
        alerts = []
        
        try:
            current_drawdown = await self._calculate_current_drawdown(portfolio_state)
            
            if current_drawdown > settings.MAX_DRAWDOWN_PERCENT:
                alert = RiskAlert(
                    id=f"drawdown_{int(datetime.now().timestamp())}",
                    alert_type=AlertType.DRAWDOWN_WARNING,
                    severity=RiskLevel.CRITICAL if current_drawdown > settings.MAX_DRAWDOWN_PERCENT * 1.5 else RiskLevel.HIGH,
                    title="Drawdown Limit Exceeded",
                    message=f"Current drawdown ({current_drawdown:.1f}%) exceeds limit ({settings.MAX_DRAWDOWN_PERCENT}%)",
                    symbol=None,
                    current_value=current_drawdown,
                    threshold_value=settings.MAX_DRAWDOWN_PERCENT,
                    recommendation="Consider stopping trading and reassessing strategy",
                    created_at=datetime.now(timezone.utc)
                )
                alerts.append(alert)
                
        except Exception as e:
            logger.error(f"Error checking drawdown limits: {e}")
        
        return alerts
    
    async def _check_concentration_limits(self, portfolio_state: PortfolioState) -> List[RiskAlert]:
        """Check concentration limits"""
        alerts = []
        
        try:
            hhi = self._calculate_hhi(portfolio_state.exposure_by_asset)
            
            if hhi > 0.5:  # High concentration threshold
                alert = RiskAlert(
                    id=f"concentration_{int(datetime.now().timestamp())}",
                    alert_type=AlertType.CONCENTRATION_RISK,
                    severity=RiskLevel.MEDIUM,
                    title="High Portfolio Concentration",
                    message=f"Portfolio concentration (HHI: {hhi:.2f}) indicates lack of diversification",
                    symbol=None,
                    current_value=hhi,
                    threshold_value=0.5,
                    recommendation="Diversify into more positions to reduce concentration risk",
                    created_at=datetime.now(timezone.utc)
                )
                alerts.append(alert)
                
        except Exception as e:
            logger.error(f"Error checking concentration limits: {e}")
        
        return alerts
    
    async def _check_liquidity_limits(self, portfolio_state: PortfolioState) -> List[RiskAlert]:
        """Check liquidity limits"""
        alerts = []
        
        try:
            liquidity_metrics = await self._calculate_liquidity_metrics(portfolio_state)
            
            if liquidity_metrics['illiquid_percent'] > 30:  # >30% illiquid
                alert = RiskAlert(
                    id=f"liquidity_{int(datetime.now().timestamp())}",
                    alert_type=AlertType.LIQUIDITY_RISK,
                    severity=RiskLevel.MEDIUM,
                    title="High Illiquid Position Exposure",
                    message=f"Illiquid positions ({liquidity_metrics['illiquid_percent']:.1f}%) may be difficult to exit",
                    symbol=None,
                    current_value=liquidity_metrics['illiquid_percent'],
                    threshold_value=30.0,
                    recommendation="Consider reducing exposure to illiquid assets",
                    created_at=datetime.now(timezone.utc)
                )
                alerts.append(alert)
                
        except Exception as e:
            logger.error(f"Error checking liquidity limits: {e}")
        
        return alerts
    
    # Additional helper methods would go here for suggestions, real-time monitoring, etc.
    # (Implementation abbreviated for space - these would include detailed rebalancing logic,
    #  trend analysis, alert management, etc.)