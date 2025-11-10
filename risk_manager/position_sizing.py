"""
Position Sizing Engine

This module implements intelligent position sizing algorithms that consider
volatility, account balance, risk parameters, and market conditions.
"""

import asyncio
import math
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass
import numpy as np
import structlog

sys.path.append('../shared')
from price_prediction_client import PricePredictionClient

from config import settings, get_asset_class, get_risk_multiplier
from database import RiskManagementDatabase

logger = structlog.get_logger()

@dataclass
class PositionSizeRequest:
    """Position sizing request parameters"""
    symbol: str
    strategy_id: str
    signal_strength: float  # 0.0 to 1.0
    current_price: float
    volatility: Optional[float] = None
    stop_loss_percent: Optional[float] = None
    risk_per_trade_percent: Optional[float] = None
    order_side: Optional[str] = None

@dataclass
class PositionSizeResult:
    """Position sizing calculation result"""
    recommended_size_usd: float
    recommended_quantity: float
    position_risk_percent: float
    stop_loss_price: Optional[float]
    max_loss_usd: float
    confidence_score: float
    risk_factors: Dict[str, float]
    warnings: List[str]
    approved: bool
    price_prediction: Optional[Dict] = None

class PositionSizingEngine:
    """
    Advanced position sizing engine with multiple algorithms
    
    Features:
    - Volatility-based sizing
    - Kelly criterion optimization  
    - Risk parity allocation
    - Signal strength adjustment
    - Market condition adaptation
    - Portfolio correlation consideration
    """
    
    def __init__(
        self,
        database: RiskManagementDatabase,
        price_prediction_client: Optional[PricePredictionClient] = None
    ):
        self.database = database
        self.price_prediction_client = price_prediction_client
        
    def set_price_prediction_client(self, client: Optional[PricePredictionClient]) -> None:
        """Attach or replace the price prediction client at runtime."""
        self.price_prediction_client = client

    async def calculate_position_size(self, request: PositionSizeRequest) -> PositionSizeResult:
        """
        Calculate optimal position size using multiple factors
        
        Args:
            request: Position sizing parameters
            
        Returns:
            PositionSizeResult with recommended size and risk metrics
        """
        try:
            logger.info(
                f"Calculating position size for {request.symbol}",
                strategy_id=request.strategy_id,
                signal_strength=request.signal_strength
            )
            
            # Get account information
            account_balance = await self.database.get_account_balance()
            available_balance = account_balance.get('available_balance_usd', 0)
            
            if available_balance < settings.MIN_ACCOUNT_BALANCE:
                return self._create_rejection_result(
                    "Insufficient account balance",
                    request
                )
            
            # Get market data
            volatility = request.volatility or await self.database.get_symbol_volatility(
                request.symbol, settings.VOLATILITY_LOOKBACK_DAYS
            )
            liquidity = await self.database.get_symbol_liquidity(request.symbol)
            
            # Calculate base position size using different methods
            volatility_size = await self._volatility_based_sizing(
                request, available_balance, volatility
            )
            
            kelly_size = await self._kelly_criterion_sizing(
                request, available_balance, volatility
            )
            
            risk_parity_size = await self._risk_parity_sizing(
                request, available_balance, volatility
            )
            
            # Weighted combination of sizing methods
            base_size = (
                volatility_size * 0.4 +
                kelly_size * 0.35 +
                risk_parity_size * 0.25
            )
            
            # Apply signal strength adjustment
            signal_adjusted_size = base_size * self._get_signal_adjustment(request.signal_strength)
            
            # Apply market condition adjustments
            market_adjusted_size = await self._apply_market_conditions(
                signal_adjusted_size, request.symbol
            )
            
            # Apply portfolio constraints
            portfolio_adjusted_size = await self._apply_portfolio_constraints(
                market_adjusted_size, request
            )
            
            # Apply asset class limits
            final_size = await self._apply_asset_class_limits(
                portfolio_adjusted_size, request.symbol, available_balance
            )
            
            # Calculate quantity and stop-loss
            quantity = final_size / request.current_price
            quantity = self._round_to_lot_size(quantity, request.symbol)
            final_size_usd = quantity * request.current_price
            
            # Calculate stop-loss price
            stop_loss_percent = request.stop_loss_percent or self._calculate_optimal_stop_loss(
                volatility, request.symbol
            )
            stop_loss_price = request.current_price * (1 - stop_loss_percent / 100)
            
            # Calculate maximum loss
            max_loss_usd = final_size_usd * (stop_loss_percent / 100)
            
            # Calculate risk factors and confidence
            risk_factors = await self._calculate_risk_factors(request, volatility, liquidity)
            confidence_score = self._calculate_confidence_score(risk_factors)
            
            # Generate warnings
            warnings = await self._generate_warnings(request, final_size_usd, available_balance)
            
            # Determine approval
            approved = await self._evaluate_approval(
                final_size_usd, max_loss_usd, risk_factors, available_balance
            )
            
            result = PositionSizeResult(
                recommended_size_usd=final_size_usd,
                recommended_quantity=quantity,
                position_risk_percent=(max_loss_usd / available_balance) * 100,
                stop_loss_price=stop_loss_price,
                max_loss_usd=max_loss_usd,
                confidence_score=confidence_score,
                risk_factors=risk_factors,
                warnings=warnings,
                approved=approved
            )

            await self._apply_price_prediction_context(request, result)
            
            logger.info(
                f"Position size calculated for {request.symbol}",
                size_usd=final_size_usd,
                quantity=quantity,
                risk_percent=result.position_risk_percent,
                approved=approved
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating position size for {request.symbol}: {e}")
            return self._create_error_result(str(e), request)
    
    async def _volatility_based_sizing(
        self, 
        request: PositionSizeRequest, 
        available_balance: float, 
        volatility: float
    ) -> float:
        """Calculate position size based on volatility targeting"""
        try:
            # Target volatility approach
            target_risk_percent = request.risk_per_trade_percent or settings.DEFAULT_RISK_PER_TRADE
            
            # Adjust for asset volatility
            volatility_multiplier = min(2.0, max(0.1, 0.02 / volatility))  # Inverse relationship
            
            base_size = (available_balance * target_risk_percent / 100) * volatility_multiplier
            
            # Apply volatility constraints
            if volatility > settings.HIGH_VOLATILITY_THRESHOLD:
                base_size *= 0.6  # Reduce size for high volatility
            
            return min(base_size, available_balance * 0.2)  # Max 20% of balance
            
        except Exception as e:
            logger.error(f"Error in volatility-based sizing: {e}")
            return available_balance * 0.01  # Conservative fallback
    
    async def _kelly_criterion_sizing(
        self,
        request: PositionSizeRequest,
        available_balance: float,
        volatility: float
    ) -> float:
        """Calculate position size using Kelly criterion"""
        try:
            # Estimate win rate and average win/loss from strategy performance
            win_rate = await self._estimate_strategy_win_rate(request.strategy_id)
            avg_win_loss_ratio = await self._estimate_win_loss_ratio(request.strategy_id)
            
            # Kelly formula: f = (bp - q) / b
            # where b = odds received on the wager (avg_win_loss_ratio)
            #       p = probability of winning (win_rate)
            #       q = probability of losing (1 - win_rate)
            
            if avg_win_loss_ratio > 0 and win_rate > 0:
                kelly_fraction = (
                    (avg_win_loss_ratio * win_rate - (1 - win_rate)) / avg_win_loss_ratio
                )
                
                # Apply fractional Kelly to reduce risk
                fractional_kelly = max(0, min(0.25, kelly_fraction * 0.25))  # Max 25% of Kelly, cap at 25%
                
                # Adjust for signal strength
                signal_adjusted_kelly = fractional_kelly * request.signal_strength
                
                return available_balance * signal_adjusted_kelly
            else:
                # Fallback to conservative sizing
                return available_balance * 0.02
            
        except Exception as e:
            logger.error(f"Error in Kelly criterion sizing: {e}")
            return available_balance * 0.02
    
    async def _risk_parity_sizing(
        self,
        request: PositionSizeRequest,
        available_balance: float,
        volatility: float
    ) -> float:
        """Calculate position size using risk parity approach"""
        try:
            # Get current portfolio positions
            positions = await self.database.get_current_positions()
            
            # Calculate target risk contribution
            total_strategies = len(set(pos.get('strategy_id') for pos in positions)) + 1
            target_risk_contribution = 1.0 / total_strategies
            
            # Calculate size to achieve target risk contribution
            portfolio_volatility = await self._estimate_portfolio_volatility()
            
            if portfolio_volatility > 0:
                target_position_volatility = target_risk_contribution * portfolio_volatility
                position_size = (available_balance * target_position_volatility) / volatility
                
                return min(position_size, available_balance * 0.15)  # Max 15% for risk parity
            else:
                return available_balance * 0.05  # Default 5% if no portfolio history
            
        except Exception as e:
            logger.error(f"Error in risk parity sizing: {e}")
            return available_balance * 0.05
    
    def _get_signal_adjustment(self, signal_strength: float) -> float:
        """Adjust position size based on signal strength"""
        # Non-linear scaling: stronger signals get disproportionately larger positions
        if signal_strength >= 0.8:
            return 1.0
        elif signal_strength >= 0.6:
            return 0.8
        elif signal_strength >= 0.4:
            return 0.6
        elif signal_strength >= 0.2:
            return 0.4
        else:
            return 0.2
    
    async def _apply_market_conditions(self, base_size: float, symbol: str) -> float:
        """Adjust position size based on current market conditions"""
        try:
            # Time-based adjustments
            current_time = datetime.now(timezone.utc)
            
            # Reduce size during off-hours (simplified - could be more sophisticated)
            if current_time.hour < 6 or current_time.hour > 22:  # UTC
                base_size *= settings.MARKET_HOURS_RISK_REDUCTION
            
            # Market volatility adjustment (would integrate with market data service)
            # For now, use simple heuristics
            market_condition = await self._assess_market_condition()
            
            if market_condition == 'HIGH_VOLATILITY':
                base_size *= 0.7
            elif market_condition == 'BEAR_MARKET':
                base_size *= 0.8
            elif market_condition == 'BULL_MARKET':
                base_size *= 1.1
            
            return base_size
            
        except Exception as e:
            logger.error(f"Error applying market conditions: {e}")
            return base_size
    
    async def _apply_portfolio_constraints(
        self, 
        base_size: float, 
        request: PositionSizeRequest
    ) -> float:
        """Apply portfolio-level constraints and correlation limits"""
        try:
            # Get current portfolio exposure
            exposure = await self.database.get_portfolio_exposure()
            total_portfolio_value = exposure.get('total_value_usd', 0)
            
            # Check single position limit
            max_single_position = total_portfolio_value * (settings.MAX_SINGLE_POSITION_PERCENT / 100)
            
            if base_size > max_single_position:
                logger.warning(
                    f"Position size reduced due to single position limit",
                    original_size=base_size,
                    max_allowed=max_single_position,
                    symbol=request.symbol
                )
                base_size = max_single_position
            
            # Check correlation constraints if enabled
            if settings.ENABLE_CORRELATION_LIMITS:
                base_size = await self._apply_correlation_constraints(
                    base_size, request.symbol, exposure
                )
            
            return base_size
            
        except Exception as e:
            logger.error(f"Error applying portfolio constraints: {e}")
            return base_size
    
    async def _apply_correlation_constraints(
        self,
        base_size: float,
        symbol: str,
        current_exposure: Dict
    ) -> float:
        """Apply correlation-based position size constraints"""
        try:
            # Get correlation matrix
            correlations = await self.database.get_latest_correlation_matrix()
            
            if not correlations:
                return base_size
            
            # Calculate correlation-weighted exposure
            correlated_exposure = 0.0
            
            for existing_symbol, existing_value in current_exposure.get('by_symbol', {}).items():
                if existing_symbol == symbol:
                    continue
                
                # Get correlation between symbols
                correlation_key = f"{symbol}_{existing_symbol}"
                reverse_key = f"{existing_symbol}_{symbol}"
                
                correlation = correlations.get(correlation_key, correlations.get(reverse_key, 0.0))
                
                if abs(correlation) > settings.MAX_CORRELATION_EXPOSURE:
                    correlated_exposure += existing_value * abs(correlation)
            
            # Reduce position size if correlation exposure is too high
            if correlated_exposure > 0:
                total_portfolio_value = current_exposure.get('total_value_usd', 1)
                correlation_limit = total_portfolio_value * (settings.MAX_CORRELATION_EXPOSURE / 100)
                
                if correlated_exposure + base_size > correlation_limit:
                    adjusted_size = max(0, correlation_limit - correlated_exposure)
                    
                    if adjusted_size < base_size:
                        logger.warning(
                            f"Position size reduced due to correlation limits",
                            original_size=base_size,
                            adjusted_size=adjusted_size,
                            symbol=symbol,
                            correlated_exposure=correlated_exposure
                        )
                        return adjusted_size
            
            return base_size
            
        except Exception as e:
            logger.error(f"Error applying correlation constraints: {e}")
            return base_size
    
    async def _apply_asset_class_limits(
        self,
        base_size: float,
        symbol: str,
        available_balance: float
    ) -> float:
        """Apply asset class specific limits"""
        try:
            asset_class = get_asset_class(symbol)
            
            # Get asset class specific limits
            if asset_class == 'CRYPTO':
                max_percent = settings.CRYPTO_MAX_POSITION_PERCENT
            elif asset_class == 'STABLECOIN':
                max_percent = settings.STABLECOIN_MAX_POSITION_PERCENT
            elif asset_class == 'DEFI':
                max_percent = settings.DEFI_MAX_POSITION_PERCENT
            else:
                max_percent = settings.CRYPTO_MAX_POSITION_PERCENT
            
            max_size = available_balance * (max_percent / 100)
            
            if base_size > max_size:
                logger.info(
                    f"Position size capped by asset class limit",
                    asset_class=asset_class,
                    original_size=base_size,
                    max_size=max_size,
                    symbol=symbol
                )
                return max_size
            
            return base_size
            
        except Exception as e:
            logger.error(f"Error applying asset class limits: {e}")
            return base_size
    
    def _calculate_optimal_stop_loss(self, volatility: float, symbol: str) -> float:
        """Calculate optimal stop-loss percentage based on volatility"""
        try:
            # Base stop-loss on volatility
            base_stop = volatility * 100 * 2  # 2x daily volatility
            
            # Apply asset class risk multiplier
            risk_multiplier = get_risk_multiplier(symbol)
            adjusted_stop = base_stop * risk_multiplier
            
            # Ensure within bounds
            return max(
                settings.MIN_STOP_LOSS_PERCENT,
                min(settings.MAX_STOP_LOSS_PERCENT, adjusted_stop)
            )
            
        except Exception as e:
            logger.error(f"Error calculating optimal stop-loss: {e}")
            return settings.DEFAULT_STOP_LOSS_PERCENT
    
    def _round_to_lot_size(self, quantity: float, symbol: str) -> float:
        """Round quantity to appropriate lot size for the symbol"""
        try:
            # Simplified lot size - in reality, would fetch from exchange info
            if symbol in ['BTC', 'ETH']:
                # High-value assets - 6 decimal places
                return round(quantity, 6)
            elif symbol.endswith('USDT') or symbol.endswith('USDC'):
                # Pairs with stablecoins - 4 decimal places
                return round(quantity, 4)
            else:
                # Other assets - 2 decimal places
                return round(quantity, 2)
                
        except Exception as e:
            logger.error(f"Error rounding lot size for {symbol}: {e}")
            return round(quantity, 6)
    
    async def _apply_price_prediction_context(
        self,
        request: PositionSizeRequest,
        result: PositionSizeResult
    ) -> None:
        """Adjust risk perception using forward-looking price predictions."""
        if not self.price_prediction_client:
            return

        try:
            prediction = await self.price_prediction_client.get_prediction(request.symbol)
            if not prediction:
                return

            result.price_prediction = prediction

            predicted_change = float(prediction.get('predicted_change_pct', 0.0))
            predicted_direction = 'BUY' if predicted_change >= 0 else 'SELL'
            signal_side = (request.order_side or '').upper()

            alignment = predicted_direction == signal_side if signal_side else True
            magnitude = abs(predicted_change)
            impact = min(5.0, magnitude / 2.0)  # cap impact

            # Update risk factors (0-10 scale where lower is better)
            if alignment:
                alignment_risk = max(0.0, 5.0 - impact)
                result.confidence_score = min(1.0, result.confidence_score + impact / 50)
            else:
                alignment_risk = min(10.0, 5.0 + impact)
                result.confidence_score = max(0.0, result.confidence_score - impact / 40)
                warning = (
                    f"Price prediction suggests {predicted_direction} with "
                    f"{predicted_change:.2f}% change"
                )
                if warning not in result.warnings:
                    result.warnings.append(warning)

            result.risk_factors['prediction_alignment'] = alignment_risk

            logger.debug(
                "Applied price prediction context to position sizing",
                symbol=request.symbol,
                predicted_change=predicted_change,
                alignment=alignment,
            )

        except Exception as exc:
            logger.warning(
                "Failed to apply price prediction context",
                symbol=request.symbol,
                error=str(exc),
            )

    async def _calculate_risk_factors(
        self,
        request: PositionSizeRequest,
        volatility: float,
        liquidity: float
    ) -> Dict[str, float]:
        """Calculate comprehensive risk factors"""
        try:
            risk_factors = {}
            
            # Volatility risk (0-10 scale)
            risk_factors['volatility_risk'] = min(10, (volatility / 0.1) * 10)
            
            # Liquidity risk (0-10 scale, inverted)
            risk_factors['liquidity_risk'] = max(0, 10 - (liquidity / 100000))
            
            # Market cap risk
            asset_class = get_asset_class(request.symbol)
            risk_factors['asset_class_risk'] = get_risk_multiplier(request.symbol) * 2
            
            # Signal strength risk (inverted)
            risk_factors['signal_risk'] = (1 - request.signal_strength) * 5
            
            # Time risk (higher during off-hours)
            current_hour = datetime.now(timezone.utc).hour
            if current_hour < 6 or current_hour > 22:
                risk_factors['time_risk'] = 3.0
            else:
                risk_factors['time_risk'] = 1.0
            
            # Portfolio concentration risk
            exposure = await self.database.get_portfolio_exposure()
            total_value = exposure.get('total_value_usd', 1)
            symbol_exposure = exposure.get('by_symbol', {}).get(request.symbol, 0)
            concentration = (symbol_exposure / total_value) if total_value > 0 else 0
            risk_factors['concentration_risk'] = concentration * 10
            
            return risk_factors
            
        except Exception as e:
            logger.error(f"Error calculating risk factors: {e}")
            return {'error_risk': 10.0}
    
    def _calculate_confidence_score(self, risk_factors: Dict[str, float]) -> float:
        """Calculate confidence score based on risk factors"""
        try:
            # Weight different risk factors
            weights = {
                'volatility_risk': 0.25,
                'liquidity_risk': 0.20,
                'asset_class_risk': 0.15,
                'signal_risk': 0.20,
                'time_risk': 0.10,
                'concentration_risk': 0.10
            }
            
            weighted_risk = 0.0
            total_weight = 0.0
            
            for factor, risk_value in risk_factors.items():
                if factor in weights:
                    weighted_risk += risk_value * weights[factor]
                    total_weight += weights[factor]
            
            if total_weight > 0:
                average_risk = weighted_risk / total_weight
                # Convert risk (0-10) to confidence (0-1), inverted
                confidence = max(0.1, (10 - average_risk) / 10)
                return confidence
            else:
                return 0.5  # Neutral confidence if no factors
                
        except Exception as e:
            logger.error(f"Error calculating confidence score: {e}")
            return 0.3  # Conservative confidence on error
    
    async def _generate_warnings(
        self,
        request: PositionSizeRequest,
        position_size_usd: float,
        available_balance: float
    ) -> List[str]:
        """Generate risk warnings for the position"""
        warnings = []
        
        try:
            # Size warnings
            position_percent = (position_size_usd / available_balance) * 100
            
            if position_percent > 10:
                warnings.append(f"Large position size: {position_percent:.1f}% of available balance")
            
            # Volatility warnings
            volatility = await self.database.get_symbol_volatility(request.symbol)
            if volatility > settings.HIGH_VOLATILITY_THRESHOLD:
                warnings.append(f"High volatility asset: {volatility*100:.1f}% daily volatility")
            
            # Liquidity warnings
            liquidity = await self.database.get_symbol_liquidity(request.symbol)
            if liquidity < settings.LOW_LIQUIDITY_THRESHOLD:
                warnings.append(f"Low liquidity asset: ${liquidity:,.0f} daily volume")
            
            # Signal strength warnings
            if request.signal_strength < 0.5:
                warnings.append(f"Weak signal strength: {request.signal_strength:.1f}")
            
            # Time-based warnings
            current_hour = datetime.now(timezone.utc).hour
            if current_hour < 6 or current_hour > 22:
                warnings.append("Trading during off-market hours")
            
            # Portfolio warnings
            exposure = await self.database.get_portfolio_exposure()
            asset_class = get_asset_class(request.symbol)
            asset_exposure = exposure.get('by_asset_class', {}).get(asset_class, 0)
            total_exposure = exposure.get('total_value_usd', 1)
            
            if total_exposure > 0 and (asset_exposure / total_exposure) > 0.3:
                warnings.append(f"High {asset_class} exposure in portfolio")
            
        except Exception as e:
            logger.error(f"Error generating warnings: {e}")
            warnings.append("Error in risk assessment")
        
        return warnings
    
    async def _evaluate_approval(
        self,
        position_size_usd: float,
        max_loss_usd: float,
        risk_factors: Dict[str, float],
        available_balance: float
    ) -> bool:
        """Evaluate whether to approve the position"""
        try:
            # Check hard limits
            if position_size_usd < settings.MIN_POSITION_SIZE_USD:
                return False
            
            if position_size_usd > settings.MAX_POSITION_SIZE_USD:
                return False
            
            if max_loss_usd > available_balance * (settings.MAX_PORTFOLIO_RISK_PERCENT / 100):
                return False
            
            # Check risk score
            average_risk = sum(risk_factors.values()) / len(risk_factors) if risk_factors else 10
            
            if average_risk > settings.RISK_SCORE_THRESHOLD:
                return False
            
            # Check account balance
            if available_balance < settings.MIN_ACCOUNT_BALANCE:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error evaluating approval: {e}")
            return False
    
    def _create_rejection_result(self, reason: str, request: PositionSizeRequest) -> PositionSizeResult:
        """Create a rejection result"""
        return PositionSizeResult(
            recommended_size_usd=0.0,
            recommended_quantity=0.0,
            position_risk_percent=0.0,
            stop_loss_price=None,
            max_loss_usd=0.0,
            confidence_score=0.0,
            risk_factors={'rejection_reason': 10.0},
            warnings=[reason],
            approved=False,
            price_prediction=None
        )
    
    def _create_error_result(self, error: str, request: PositionSizeRequest) -> PositionSizeResult:
        """Create an error result"""
        return PositionSizeResult(
            recommended_size_usd=0.0,
            recommended_quantity=0.0,
            position_risk_percent=0.0,
            stop_loss_price=None,
            max_loss_usd=0.0,
            confidence_score=0.0,
            risk_factors={'error': 10.0},
            warnings=[f"Calculation error: {error}"],
            approved=False,
            price_prediction=None
        )
    
    # Helper methods for strategy performance estimation
    
    async def _estimate_strategy_win_rate(self, strategy_id: str) -> float:
        """Estimate strategy win rate from historical data"""
        try:
            # This would query historical trades for the strategy
            # For now, return a default estimate
            return 0.55  # Default 55% win rate
            
        except Exception as e:
            logger.error(f"Error estimating win rate for {strategy_id}: {e}")
            return 0.5  # Neutral estimate
    
    async def _estimate_win_loss_ratio(self, strategy_id: str) -> float:
        """Estimate average win/loss ratio from historical data"""
        try:
            # This would analyze historical trade P&L
            # For now, return a default estimate
            return 1.5  # Default 1.5:1 win/loss ratio
            
        except Exception as e:
            logger.error(f"Error estimating win/loss ratio for {strategy_id}: {e}")
            return 1.0  # Neutral estimate
    
    async def _estimate_portfolio_volatility(self) -> float:
        """Estimate current portfolio volatility"""
        try:
            # This would calculate portfolio volatility from position data
            # For now, return a default estimate
            return 0.03  # Default 3% daily portfolio volatility
            
        except Exception as e:
            logger.error(f"Error estimating portfolio volatility: {e}")
            return 0.05  # Conservative estimate
    
    async def _assess_market_condition(self) -> str:
        """Assess current market conditions"""
        try:
            # This would integrate with market data to assess conditions
            # For now, return a default assessment
            return 'SIDEWAYS'  # Default market condition
            
        except Exception as e:
            logger.error(f"Error assessing market condition: {e}")
            return 'HIGH_VOLATILITY'  # Conservative assumption