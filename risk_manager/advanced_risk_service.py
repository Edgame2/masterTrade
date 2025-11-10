"""
Advanced Risk Management Service Integration

Integrates the Advanced Risk Controller into the existing risk management
service, providing seamless coordination between all risk components.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional
import structlog

from database import RiskManagementDatabase
from position_sizing import PositionSizingEngine
from stop_loss_manager import StopLossManager
from portfolio_risk_controller import PortfolioRiskController
from advanced_risk_controller import (
    AdvancedRiskController, RiskApprovalResult, 
    PortfolioLimits, DrawdownControl
)
from config import settings

logger = structlog.get_logger()


class AdvancedRiskManagementService:
    """
    Unified Risk Management Service with Advanced Controls
    
    Coordinates all risk management components:
    - Position sizing
    - Stop-loss management
    - Portfolio risk monitoring
    - Advanced risk controls
    - Periodic position adjustments
    """
    
    def __init__(self):
        # Initialize database
        self.database = RiskManagementDatabase()
        
        # Initialize core components
        self.position_sizing = PositionSizingEngine(self.database)
        self.stop_loss_manager = StopLossManager(self.database)
        self.portfolio_controller = PortfolioRiskController(self.database)
        
        # Initialize advanced risk controller
        self.advanced_controller = AdvancedRiskController(
            database=self.database,
            position_sizing=self.position_sizing,
            stop_loss_manager=self.stop_loss_manager,
            portfolio_controller=self.portfolio_controller
        )
        
        # Background tasks
        self._adjustment_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info("Advanced Risk Management Service initialized")
    
    
    async def start(self):
        """Start background risk monitoring and adjustment tasks"""
        self._running = True
        
        # Start periodic position adjustment task
        self._adjustment_task = asyncio.create_task(self._periodic_adjustments())
        
        logger.info("Advanced Risk Management Service started")
    
    
    async def stop(self):
        """Stop background tasks"""
        self._running = False
        
        if self._adjustment_task:
            self._adjustment_task.cancel()
            try:
                await self._adjustment_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Advanced Risk Management Service stopped")
    
    
    async def approve_trade(
        self,
        symbol: str,
        strategy_id: str,
        signal_strength: float,
        requested_size_usd: float,
        current_price: float,
        volatility: Optional[float] = None
    ) -> RiskApprovalResult:
        """
        Comprehensive trade approval with all risk checks
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            strategy_id: Strategy requesting the trade
            signal_strength: Confidence in signal (0.0 to 1.0)
            requested_size_usd: Requested position size in USD
            current_price: Current market price
            volatility: Optional volatility (will be fetched if not provided)
        
        Returns:
            RiskApprovalResult with approval decision and adjustments
        """
        logger.info(
            f"Trade approval requested: {symbol}",
            strategy_id=strategy_id,
            signal_strength=signal_strength,
            requested_size_usd=requested_size_usd
        )
        
        try:
            # Use advanced risk controller for comprehensive approval
            result = await self.advanced_controller.approve_new_position(
                symbol=symbol,
                strategy_id=strategy_id,
                signal_strength=signal_strength,
                requested_size_usd=requested_size_usd,
                current_price=current_price,
                volatility=volatility
            )
            
            # Log approval decision
            if result.approved:
                logger.info(
                    f"Trade APPROVED: {symbol}",
                    size_adjustment=result.position_size_adjustment,
                    risk_score=result.risk_score,
                    stop_loss=result.stop_loss_params.adjusted_stop_percent
                )
            else:
                logger.warning(
                    f"Trade REJECTED: {symbol}",
                    rejections=result.rejections,
                    risk_score=result.risk_score
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in trade approval: {e}", exc_info=True)
            # Return rejection on error
            return RiskApprovalResult(
                approved=False,
                position_size_adjustment=0.0,
                stop_loss_params=await self.advanced_controller._get_stop_loss_params(symbol, volatility),
                risk_score=100.0,
                risk_factors={'error': 1.0},
                warnings=[],
                rejections=[f"Trade approval error: {str(e)}"],
                recommendations=["System error - review logs"],
                metadata={}
            )
    
    
    async def get_position_size_recommendation(
        self,
        symbol: str,
        strategy_id: str,
        signal_strength: float,
        current_price: float
    ) -> Dict[str, any]:
        """
        Get position size recommendation without full approval process
        
        Useful for strategy services to estimate position sizes
        """
        try:
            # Get basic position size from position sizing engine
            from position_sizing import PositionSizeRequest
            
            request = PositionSizeRequest(
                symbol=symbol,
                strategy_id=strategy_id,
                signal_strength=signal_strength,
                current_price=current_price
            )
            
            base_result = await self.position_sizing.calculate_position_size(request)
            
            # Get risk adjustments from advanced controller
            approval = await self.advanced_controller.approve_new_position(
                symbol=symbol,
                strategy_id=strategy_id,
                signal_strength=signal_strength,
                requested_size_usd=base_result.recommended_size_usd,
                current_price=current_price
            )
            
            # Calculate final recommendation
            final_size_usd = base_result.recommended_size_usd * approval.position_size_adjustment
            final_quantity = final_size_usd / current_price
            
            return {
                'symbol': symbol,
                'base_size_usd': base_result.recommended_size_usd,
                'base_quantity': base_result.recommended_quantity,
                'adjustment_factor': approval.position_size_adjustment,
                'final_size_usd': final_size_usd,
                'final_quantity': final_quantity,
                'stop_loss_percent': approval.stop_loss_params.adjusted_stop_percent,
                'stop_loss_price': current_price * (1 - approval.stop_loss_params.adjusted_stop_percent),
                'max_loss_usd': final_size_usd * approval.stop_loss_params.adjusted_stop_percent,
                'risk_score': approval.risk_score,
                'approved': approval.approved,
                'warnings': approval.warnings,
                'recommendations': approval.recommendations,
                'regime': approval.stop_loss_params.regime.value
            }
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}", exc_info=True)
            return {
                'error': str(e),
                'final_size_usd': 0.0,
                'final_quantity': 0.0,
                'approved': False
            }
    
    
    async def update_stop_loss(
        self,
        position_id: str,
        new_stop_price: Optional[float] = None
    ) -> Dict[str, any]:
        """
        Update stop-loss for a position
        
        If new_stop_price not provided, will calculate optimal stop based on current conditions
        """
        try:
            # Get position
            position = await self.database.get_position(position_id)
            if not position:
                return {'success': False, 'error': 'Position not found'}
            
            # If no new stop provided, calculate dynamic stop
            if new_stop_price is None:
                volatility = await self.database.get_symbol_volatility(
                    position['symbol'], settings.VOLATILITY_LOOKBACK_DAYS
                )
                stop_params = await self.advanced_controller._get_stop_loss_params(
                    position['symbol'], volatility
                )
                new_stop_price = position['current_price'] * (1 - stop_params.adjusted_stop_percent)
            
            # Update stop-loss
            result = await self.stop_loss_manager.update_stop_loss(
                position_id, new_stop_price
            )
            
            return {
                'success': True,
                'position_id': position_id,
                'old_stop': result.old_stop_price,
                'new_stop': result.new_stop_price,
                'trigger_reason': result.trigger_reason
            }
            
        except Exception as e:
            logger.error(f"Error updating stop-loss: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    
    async def get_risk_status(self) -> Dict[str, any]:
        """
        Get comprehensive risk status for monitoring
        
        Returns current risk metrics, limits, circuit breaker status, etc.
        """
        try:
            dashboard_data = await self.advanced_controller.get_risk_dashboard_data()
            return {
                'success': True,
                'data': dashboard_data
            }
        except Exception as e:
            logger.error(f"Error getting risk status: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    
    async def override_circuit_breaker(self, level: str, reason: str) -> Dict[str, any]:
        """
        Manual override of circuit breaker (use with extreme caution)
        
        Args:
            level: 'none', 'warning', 'level_1', 'level_2', 'level_3'
            reason: Reason for override (logged for audit)
        
        Returns:
            Success status
        """
        logger.warning(
            f"Circuit breaker manual override requested: {level}",
            reason=reason
        )
        
        try:
            # This should be restricted to administrators only
            # Implementation would depend on your security model
            
            # For now, just log the request
            await self.database.log_admin_action(
                action='circuit_breaker_override',
                level=level,
                reason=reason,
                timestamp=datetime.now(timezone.utc)
            )
            
            return {
                'success': True,
                'message': f'Circuit breaker override to {level} recorded',
                'warning': 'Manual overrides should be used with extreme caution'
            }
            
        except Exception as e:
            logger.error(f"Error overriding circuit breaker: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    
    async def update_portfolio_limits(self, limits: Dict[str, float]) -> Dict[str, any]:
        """
        Update portfolio risk limits
        
        Args:
            limits: Dictionary of limit values to update
        
        Returns:
            Success status and new limits
        """
        try:
            current_limits = self.advanced_controller.portfolio_limits
            
            # Update provided limits
            if 'max_portfolio_leverage' in limits:
                current_limits.max_portfolio_leverage = limits['max_portfolio_leverage']
            if 'max_portfolio_var_percent' in limits:
                current_limits.max_portfolio_var_percent = limits['max_portfolio_var_percent']
            if 'max_drawdown_percent' in limits:
                current_limits.max_drawdown_percent = limits['max_drawdown_percent']
            if 'max_single_position_percent' in limits:
                current_limits.max_single_position_percent = limits['max_single_position_percent']
            if 'max_correlated_exposure_percent' in limits:
                current_limits.max_correlated_exposure_percent = limits['max_correlated_exposure_percent']
            if 'max_sector_exposure_percent' in limits:
                current_limits.max_sector_exposure_percent = limits['max_sector_exposure_percent']
            
            # Log the change
            logger.info("Portfolio limits updated", limits=limits)
            
            # Persist to database
            await self.database.save_portfolio_limits(current_limits)
            
            return {
                'success': True,
                'message': 'Portfolio limits updated',
                'new_limits': {
                    'max_leverage': current_limits.max_portfolio_leverage,
                    'max_var': current_limits.max_portfolio_var_percent,
                    'max_drawdown': current_limits.max_drawdown_percent,
                    'max_single_position': current_limits.max_single_position_percent,
                    'max_correlated_exposure': current_limits.max_correlated_exposure_percent,
                    'max_sector_exposure': current_limits.max_sector_exposure_percent
                }
            }
            
        except Exception as e:
            logger.error(f"Error updating limits: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    
    async def _periodic_adjustments(self):
        """
        Background task to periodically adjust positions based on risk conditions
        
        Runs every 5 minutes to:
        - Check drawdown status
        - Adjust stop-losses based on volatility changes
        - Reduce positions if limits breached
        - Issue risk alerts
        """
        adjustment_interval = 300  # 5 minutes
        
        while self._running:
            try:
                logger.debug("Running periodic risk adjustments")
                
                # Perform adjustments
                adjustments = await self.advanced_controller.adjust_existing_positions()
                
                # Log significant adjustments
                if (adjustments['stops_tightened'] or 
                    adjustments['positions_reduced'] or 
                    adjustments['positions_closed']):
                    logger.info(
                        "Periodic risk adjustments completed",
                        stops_tightened=len(adjustments['stops_tightened']),
                        positions_reduced=len(adjustments['positions_reduced']),
                        positions_closed=len(adjustments['positions_closed'])
                    )
                
                # Store adjustment history
                await self.database.save_adjustment_history(adjustments)
                
            except Exception as e:
                logger.error(f"Error in periodic adjustments: {e}", exc_info=True)
            
            # Wait for next interval
            await asyncio.sleep(adjustment_interval)
    
    
    async def force_adjustment_check(self) -> Dict[str, any]:
        """
        Manually trigger position adjustment check
        
        Returns:
            Summary of adjustments made
        """
        try:
            logger.info("Manual position adjustment check triggered")
            adjustments = await self.advanced_controller.adjust_existing_positions()
            return {
                'success': True,
                'adjustments': adjustments
            }
        except Exception as e:
            logger.error(f"Error in manual adjustment check: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    
    async def get_correlation_analysis(self, symbols: Optional[List[str]] = None) -> Dict[str, any]:
        """
        Get correlation analysis for portfolio or specific symbols
        
        Args:
            symbols: Optional list of symbols to analyze. If None, analyzes entire portfolio.
        
        Returns:
            Correlation metrics and visualization data
        """
        try:
            if symbols is None:
                # Analyze entire portfolio
                positions = await self.database.get_all_active_positions()
                symbols = [pos['symbol'] for pos in positions]
            
            if not symbols:
                return {
                    'success': True,
                    'message': 'No positions to analyze',
                    'symbols': [],
                    'correlation_matrix': []
                }
            
            # Get correlation risk assessment
            correlation_risk = await self.advanced_controller._assess_correlation_risk(
                '', positions  # Empty symbol for portfolio-wide
            )
            
            return {
                'success': True,
                'symbols': symbols,
                'avg_correlation': correlation_risk.portfolio_correlation,
                'diversification_ratio': correlation_risk.diversification_ratio,
                'effective_assets': correlation_risk.effective_assets,
                'correlation_risk_score': correlation_risk.correlation_risk_score,
                'correlation_clusters': correlation_risk.correlation_clusters,
                'recommendations': correlation_risk.recommendations
            }
            
        except Exception as e:
            logger.error(f"Error in correlation analysis: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}


# Global service instance (initialized in main.py)
advanced_risk_service: Optional[AdvancedRiskManagementService] = None


def get_advanced_risk_service() -> AdvancedRiskManagementService:
    """Get the global advanced risk service instance"""
    global advanced_risk_service
    if advanced_risk_service is None:
        advanced_risk_service = AdvancedRiskManagementService()
    return advanced_risk_service
