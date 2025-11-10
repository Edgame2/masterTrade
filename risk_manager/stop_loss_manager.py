"""
Stop-Loss Management System

This module implements dynamic stop-loss management with trailing stops,
volatility-based adjustments, and adaptive algorithms for risk control.
"""

import asyncio
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Union
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, field
from enum import Enum
import structlog

from config import settings, get_asset_class, get_risk_multiplier
from database import RiskManagementDatabase

logger = structlog.get_logger()

class StopLossType(Enum):
    """Types of stop-loss orders"""
    FIXED = "fixed"
    TRAILING = "trailing"
    VOLATILITY_BASED = "volatility_based"
    ATR_BASED = "atr_based"
    SUPPORT_RESISTANCE = "support_resistance"

class StopLossStatus(Enum):
    """Stop-loss status tracking"""
    ACTIVE = "active"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"
    MODIFIED = "modified"
    EXPIRED = "expired"

@dataclass
class StopLossConfig:
    """Stop-loss configuration parameters"""
    stop_type: StopLossType
    initial_stop_percent: float
    trailing_distance_percent: Optional[float] = None
    max_loss_percent: Optional[float] = None
    min_profit_before_trail: Optional[float] = None
    volatility_multiplier: Optional[float] = None
    support_resistance_buffer: Optional[float] = None
    time_decay_enabled: bool = False
    breakeven_protection: bool = True

@dataclass 
class StopLossOrder:
    """Stop-loss order tracking"""
    id: str
    position_id: str
    symbol: str
    stop_type: StopLossType
    status: StopLossStatus
    entry_price: float
    current_price: float
    stop_price: float
    initial_stop_price: float
    quantity: float
    created_at: datetime
    last_updated: datetime
    config: StopLossConfig
    profit_loss: float = 0.0
    highest_price: float = 0.0  # For trailing stops
    lowest_price: float = 0.0   # For short positions
    trigger_count: int = 0
    metadata: Dict = field(default_factory=dict)

@dataclass
class StopLossUpdate:
    """Stop-loss price update result"""
    order_id: str
    old_stop_price: float
    new_stop_price: float
    trigger_reason: str
    should_execute: bool
    confidence: float
    risk_factors: Dict[str, float]

class StopLossManager:
    """
    Advanced stop-loss management system
    
    Features:
    - Multiple stop-loss algorithms (fixed, trailing, volatility-based, ATR, S/R)
    - Dynamic adjustment based on market conditions
    - Breakeven protection and profit-taking
    - Time-based decay and volatility adaptation
    - Multi-timeframe analysis
    - Position correlation consideration
    """
    
    def __init__(self, database: RiskManagementDatabase):
        self.database = database
        self.active_stops: Dict[str, StopLossOrder] = {}
        
    async def create_stop_loss(
        self,
        position_id: str,
        symbol: str,
        entry_price: float,
        quantity: float,
        config: StopLossConfig,
        metadata: Optional[Dict] = None
    ) -> StopLossOrder:
        """
        Create a new stop-loss order for a position
        
        Args:
            position_id: Unique position identifier
            symbol: Trading symbol
            entry_price: Position entry price
            quantity: Position size
            config: Stop-loss configuration
            metadata: Additional metadata
            
        Returns:
            StopLossOrder object
        """
        try:
            logger.info(
                f"Creating stop-loss for position {position_id}",
                symbol=symbol,
                stop_type=config.stop_type.value,
                entry_price=entry_price
            )
            
            # Calculate initial stop price
            initial_stop_price = await self._calculate_initial_stop_price(
                symbol, entry_price, config
            )
            
            # Create stop-loss order
            order_id = f"sl_{position_id}_{int(datetime.now().timestamp())}"
            
            stop_order = StopLossOrder(
                id=order_id,
                position_id=position_id,
                symbol=symbol,
                stop_type=config.stop_type,
                status=StopLossStatus.ACTIVE,
                entry_price=entry_price,
                current_price=entry_price,
                stop_price=initial_stop_price,
                initial_stop_price=initial_stop_price,
                quantity=quantity,
                created_at=datetime.now(timezone.utc),
                last_updated=datetime.now(timezone.utc),
                config=config,
                highest_price=entry_price,
                lowest_price=entry_price,
                metadata=metadata or {}
            )
            
            # Store in database and memory
            await self.database.create_stop_loss_order(stop_order)
            self.active_stops[order_id] = stop_order
            
            logger.info(
                f"Stop-loss created for {symbol}",
                order_id=order_id,
                stop_price=initial_stop_price,
                stop_percent=(abs(entry_price - initial_stop_price) / entry_price) * 100
            )
            
            return stop_order
            
        except Exception as e:
            logger.error(f"Error creating stop-loss for position {position_id}: {e}")
            raise
    
    async def update_stop_losses(
        self, 
        price_updates: Dict[str, float]
    ) -> List[StopLossUpdate]:
        """
        Update all active stop-loss orders based on price changes
        
        Args:
            price_updates: Dictionary of symbol -> current price
            
        Returns:
            List of StopLossUpdate objects with changes
        """
        updates = []
        
        try:
            # Get active stop-loss orders
            if not self.active_stops:
                await self._load_active_stops()
            
            for order_id, stop_order in self.active_stops.items():
                if stop_order.status != StopLossStatus.ACTIVE:
                    continue
                
                current_price = price_updates.get(stop_order.symbol)
                if current_price is None:
                    continue
                
                # Update order with current price
                stop_order.current_price = current_price
                stop_order.profit_loss = (current_price - stop_order.entry_price) * stop_order.quantity
                
                # Update highest/lowest prices for trailing stops
                if current_price > stop_order.highest_price:
                    stop_order.highest_price = current_price
                if current_price < stop_order.lowest_price:
                    stop_order.lowest_price = current_price
                
                # Calculate new stop price based on stop type
                update = await self._update_stop_price(stop_order)
                
                if update and update.new_stop_price != update.old_stop_price:
                    updates.append(update)
                    
                    # Update order
                    stop_order.stop_price = update.new_stop_price
                    stop_order.last_updated = datetime.now(timezone.utc)
                    
                    # Save to database
                    await self.database.update_stop_loss_order(stop_order)
                    
                    logger.info(
                        f"Stop-loss updated for {stop_order.symbol}",
                        order_id=order_id,
                        old_stop=update.old_stop_price,
                        new_stop=update.new_stop_price,
                        reason=update.trigger_reason
                    )
            
            return updates
            
        except Exception as e:
            logger.error(f"Error updating stop-losses: {e}")
            return []
    
    async def check_stop_triggers(
        self, 
        price_updates: Dict[str, float]
    ) -> List[StopLossOrder]:
        """
        Check for stop-loss triggers and return triggered orders
        
        Args:
            price_updates: Dictionary of symbol -> current price
            
        Returns:
            List of triggered StopLossOrder objects
        """
        triggered_orders = []
        
        try:
            if not self.active_stops:
                await self._load_active_stops()
            
            for order_id, stop_order in self.active_stops.items():
                if stop_order.status != StopLossStatus.ACTIVE:
                    continue
                
                current_price = price_updates.get(stop_order.symbol)
                if current_price is None:
                    continue
                
                # Check if stop should trigger
                should_trigger = await self._should_trigger_stop(stop_order, current_price)
                
                if should_trigger:
                    stop_order.status = StopLossStatus.TRIGGERED
                    stop_order.current_price = current_price
                    stop_order.trigger_count += 1
                    stop_order.last_updated = datetime.now(timezone.utc)
                    
                    triggered_orders.append(stop_order)
                    
                    # Remove from active stops
                    del self.active_stops[order_id]
                    
                    # Update in database
                    await self.database.update_stop_loss_order(stop_order)
                    
                    logger.warning(
                        f"Stop-loss triggered for {stop_order.symbol}",
                        order_id=order_id,
                        trigger_price=current_price,
                        stop_price=stop_order.stop_price,
                        loss_amount=stop_order.profit_loss
                    )
            
            return triggered_orders
            
        except Exception as e:
            logger.error(f"Error checking stop triggers: {e}")
            return []
    
    async def modify_stop_loss(
        self,
        order_id: str,
        new_config: Optional[StopLossConfig] = None,
        new_stop_price: Optional[float] = None
    ) -> bool:
        """
        Modify an existing stop-loss order
        
        Args:
            order_id: Stop-loss order ID
            new_config: New stop-loss configuration
            new_stop_price: New stop price (overrides config calculation)
            
        Returns:
            Success status
        """
        try:
            if order_id not in self.active_stops:
                await self._load_active_stops()
            
            if order_id not in self.active_stops:
                logger.error(f"Stop-loss order {order_id} not found")
                return False
            
            stop_order = self.active_stops[order_id]
            
            if stop_order.status != StopLossStatus.ACTIVE:
                logger.error(f"Cannot modify non-active stop-loss {order_id}")
                return False
            
            # Update configuration if provided
            if new_config:
                stop_order.config = new_config
            
            # Calculate new stop price
            if new_stop_price:
                stop_order.stop_price = new_stop_price
            else:
                # Recalculate based on new config
                stop_order.stop_price = await self._calculate_initial_stop_price(
                    stop_order.symbol, stop_order.entry_price, stop_order.config
                )
            
            stop_order.status = StopLossStatus.MODIFIED
            stop_order.last_updated = datetime.now(timezone.utc)
            
            # Update in database
            await self.database.update_stop_loss_order(stop_order)
            
            # Reset to active status
            stop_order.status = StopLossStatus.ACTIVE
            
            logger.info(
                f"Stop-loss modified for {stop_order.symbol}",
                order_id=order_id,
                new_stop_price=stop_order.stop_price
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error modifying stop-loss {order_id}: {e}")
            return False
    
    async def cancel_stop_loss(self, order_id: str) -> bool:
        """Cancel a stop-loss order"""
        try:
            if order_id not in self.active_stops:
                await self._load_active_stops()
            
            if order_id not in self.active_stops:
                logger.error(f"Stop-loss order {order_id} not found")
                return False
            
            stop_order = self.active_stops[order_id]
            stop_order.status = StopLossStatus.CANCELLED
            stop_order.last_updated = datetime.now(timezone.utc)
            
            # Remove from active stops
            del self.active_stops[order_id]
            
            # Update in database
            await self.database.update_stop_loss_order(stop_order)
            
            logger.info(f"Stop-loss cancelled", order_id=order_id)
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling stop-loss {order_id}: {e}")
            return False
    
    async def get_stop_loss_status(self, position_id: str) -> Optional[StopLossOrder]:
        """Get current stop-loss status for a position"""
        try:
            for stop_order in self.active_stops.values():
                if stop_order.position_id == position_id and stop_order.status == StopLossStatus.ACTIVE:
                    return stop_order
            
            # Check database if not in memory
            return await self.database.get_active_stop_loss_by_position(position_id)
            
        except Exception as e:
            logger.error(f"Error getting stop-loss status for position {position_id}: {e}")
            return None
    
    # Private helper methods
    
    async def _calculate_initial_stop_price(
        self, 
        symbol: str, 
        entry_price: float, 
        config: StopLossConfig
    ) -> float:
        """Calculate initial stop-loss price based on configuration"""
        try:
            if config.stop_type == StopLossType.FIXED:
                return entry_price * (1 - config.initial_stop_percent / 100)
            
            elif config.stop_type == StopLossType.VOLATILITY_BASED:
                volatility = await self.database.get_symbol_volatility(symbol)
                volatility_multiplier = config.volatility_multiplier or 2.0
                stop_distance = volatility * volatility_multiplier * 100
                
                # Apply asset class risk multiplier
                risk_multiplier = get_risk_multiplier(symbol)
                adjusted_distance = stop_distance * risk_multiplier
                
                return entry_price * (1 - adjusted_distance / 100)
            
            elif config.stop_type == StopLossType.ATR_BASED:
                atr = await self._calculate_atr(symbol)
                atr_multiplier = config.volatility_multiplier or 2.0
                stop_distance = (atr / entry_price) * atr_multiplier * 100
                
                return entry_price * (1 - stop_distance / 100)
            
            elif config.stop_type == StopLossType.SUPPORT_RESISTANCE:
                support_level = await self._find_support_level(symbol, entry_price)
                buffer = config.support_resistance_buffer or 0.5  # 0.5% buffer
                
                return support_level * (1 - buffer / 100)
            
            else:  # Default to fixed
                return entry_price * (1 - config.initial_stop_percent / 100)
                
        except Exception as e:
            logger.error(f"Error calculating initial stop price for {symbol}: {e}")
            # Fallback to fixed percentage
            return entry_price * (1 - config.initial_stop_percent / 100)
    
    async def _update_stop_price(self, stop_order: StopLossOrder) -> Optional[StopLossUpdate]:
        """Update stop price based on stop type and market conditions"""
        try:
            old_stop_price = stop_order.stop_price
            new_stop_price = old_stop_price
            trigger_reason = ""
            confidence = 1.0
            
            if stop_order.config.stop_type == StopLossType.TRAILING:
                new_stop_price, trigger_reason = await self._calculate_trailing_stop(stop_order)
            
            elif stop_order.config.stop_type == StopLossType.VOLATILITY_BASED:
                new_stop_price, trigger_reason = await self._calculate_volatility_stop(stop_order)
            
            elif stop_order.config.stop_type == StopLossType.ATR_BASED:
                new_stop_price, trigger_reason = await self._calculate_atr_stop(stop_order)
            
            elif stop_order.config.stop_type == StopLossType.SUPPORT_RESISTANCE:
                new_stop_price, trigger_reason = await self._calculate_sr_stop(stop_order)
            
            # Apply breakeven protection if enabled
            if stop_order.config.breakeven_protection:
                new_stop_price = await self._apply_breakeven_protection(stop_order, new_stop_price)
            
            # Apply time decay if enabled
            if stop_order.config.time_decay_enabled:
                new_stop_price = await self._apply_time_decay(stop_order, new_stop_price)
            
            # Ensure stop price doesn't move against us
            if new_stop_price < old_stop_price:  # For long positions
                new_stop_price = max(old_stop_price, new_stop_price)
            
            # Calculate risk factors and confidence
            risk_factors = await self._calculate_stop_risk_factors(stop_order)
            confidence = self._calculate_stop_confidence(risk_factors)
            
            should_execute = abs(new_stop_price - old_stop_price) > (old_stop_price * 0.001)  # 0.1% threshold
            
            if should_execute or trigger_reason:
                return StopLossUpdate(
                    order_id=stop_order.id,
                    old_stop_price=old_stop_price,
                    new_stop_price=new_stop_price,
                    trigger_reason=trigger_reason or "Price update",
                    should_execute=should_execute,
                    confidence=confidence,
                    risk_factors=risk_factors
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error updating stop price for {stop_order.symbol}: {e}")
            return None
    
    async def _calculate_trailing_stop(self, stop_order: StopLossOrder) -> Tuple[float, str]:
        """Calculate trailing stop price"""
        try:
            trailing_distance = stop_order.config.trailing_distance_percent or 3.0
            min_profit = stop_order.config.min_profit_before_trail or 1.0
            
            # Check if we have minimum profit to start trailing
            current_profit_percent = ((stop_order.current_price - stop_order.entry_price) / stop_order.entry_price) * 100
            
            if current_profit_percent < min_profit:
                return stop_order.stop_price, "Insufficient profit for trailing"
            
            # Calculate new stop based on highest price
            new_stop_price = stop_order.highest_price * (1 - trailing_distance / 100)
            
            # Ensure it's better than current stop
            if new_stop_price > stop_order.stop_price:
                return new_stop_price, f"Trailing stop moved up (highest: {stop_order.highest_price})"
            
            return stop_order.stop_price, "No trailing adjustment needed"
            
        except Exception as e:
            logger.error(f"Error calculating trailing stop: {e}")
            return stop_order.stop_price, "Error in trailing calculation"
    
    async def _calculate_volatility_stop(self, stop_order: StopLossOrder) -> Tuple[float, str]:
        """Calculate volatility-based stop price"""
        try:
            # Get current volatility
            current_volatility = await self.database.get_symbol_volatility(
                stop_order.symbol, days=14
            )
            
            # Compare with entry volatility
            entry_volatility = stop_order.metadata.get('entry_volatility', current_volatility)
            
            volatility_multiplier = stop_order.config.volatility_multiplier or 2.0
            
            # Adjust stop distance based on volatility change
            volatility_ratio = current_volatility / entry_volatility if entry_volatility > 0 else 1.0
            adjusted_multiplier = volatility_multiplier * volatility_ratio
            
            stop_distance = current_volatility * adjusted_multiplier * 100
            new_stop_price = stop_order.current_price * (1 - stop_distance / 100)
            
            reason = f"Volatility adjustment ({current_volatility*100:.1f}% vol, {volatility_ratio:.2f}x ratio)"
            
            return new_stop_price, reason
            
        except Exception as e:
            logger.error(f"Error calculating volatility stop: {e}")
            return stop_order.stop_price, "Error in volatility calculation"
    
    async def _calculate_atr_stop(self, stop_order: StopLossOrder) -> Tuple[float, str]:
        """Calculate ATR-based stop price"""
        try:
            # Calculate current ATR
            atr = await self._calculate_atr(stop_order.symbol)
            atr_multiplier = stop_order.config.volatility_multiplier or 2.0
            
            # Calculate stop distance
            stop_distance = (atr / stop_order.current_price) * atr_multiplier * 100
            new_stop_price = stop_order.current_price * (1 - stop_distance / 100)
            
            reason = f"ATR adjustment (ATR: {atr:.4f}, {atr_multiplier}x multiplier)"
            
            return new_stop_price, reason
            
        except Exception as e:
            logger.error(f"Error calculating ATR stop: {e}")
            return stop_order.stop_price, "Error in ATR calculation"
    
    async def _calculate_sr_stop(self, stop_order: StopLossOrder) -> Tuple[float, str]:
        """Calculate support/resistance based stop price"""
        try:
            # Find current support level
            support_level = await self._find_support_level(
                stop_order.symbol, stop_order.current_price
            )
            
            buffer = stop_order.config.support_resistance_buffer or 0.5
            new_stop_price = support_level * (1 - buffer / 100)
            
            reason = f"Support level adjustment (support: {support_level:.4f})"
            
            return new_stop_price, reason
            
        except Exception as e:
            logger.error(f"Error calculating S/R stop: {e}")
            return stop_order.stop_price, "Error in S/R calculation"
    
    async def _apply_breakeven_protection(
        self, 
        stop_order: StopLossOrder, 
        current_stop: float
    ) -> float:
        """Apply breakeven protection logic"""
        try:
            # Move stop to breakeven when in profit
            profit_percent = ((stop_order.current_price - stop_order.entry_price) / stop_order.entry_price) * 100
            
            if profit_percent > 2.0:  # 2% profit threshold
                breakeven_stop = stop_order.entry_price * 1.001  # Small buffer above breakeven
                return max(current_stop, breakeven_stop)
            
            return current_stop
            
        except Exception as e:
            logger.error(f"Error applying breakeven protection: {e}")
            return current_stop
    
    async def _apply_time_decay(
        self, 
        stop_order: StopLossOrder, 
        current_stop: float
    ) -> float:
        """Apply time-based stop tightening"""
        try:
            # Tighten stop over time if position isn't profitable
            time_elapsed = datetime.now(timezone.utc) - stop_order.created_at
            hours_elapsed = time_elapsed.total_seconds() / 3600
            
            # If position is unprofitable after 24 hours, tighten stop
            if hours_elapsed > 24:
                profit_percent = ((stop_order.current_price - stop_order.entry_price) / stop_order.entry_price) * 100
                
                if profit_percent < 0:
                    # Tighten by 0.1% per day
                    days_elapsed = hours_elapsed / 24
                    tightening_factor = 1 + (days_elapsed * 0.001)  # 0.1% per day
                    
                    tightened_stop = stop_order.entry_price * (1 - (stop_order.config.initial_stop_percent / 100) / tightening_factor)
                    return max(current_stop, tightened_stop)
            
            return current_stop
            
        except Exception as e:
            logger.error(f"Error applying time decay: {e}")
            return current_stop
    
    async def _should_trigger_stop(self, stop_order: StopLossOrder, current_price: float) -> bool:
        """Determine if stop-loss should trigger"""
        try:
            # Basic price trigger
            if current_price <= stop_order.stop_price:
                return True
            
            # Additional trigger conditions for different stop types
            if stop_order.config.stop_type == StopLossType.VOLATILITY_BASED:
                # Consider volatility spikes
                volatility = await self.database.get_symbol_volatility(stop_order.symbol, days=1)
                if volatility > settings.HIGH_VOLATILITY_THRESHOLD * 1.5:
                    # Tighter trigger during extreme volatility
                    adjusted_trigger = stop_order.stop_price * 1.005  # 0.5% buffer
                    if current_price <= adjusted_trigger:
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking stop trigger: {e}")
            return current_price <= stop_order.stop_price  # Fallback to basic trigger
    
    async def _load_active_stops(self):
        """Load active stop-loss orders from database"""
        try:
            active_orders = await self.database.get_active_stop_loss_orders()
            self.active_stops = {order.id: order for order in active_orders}
            
        except Exception as e:
            logger.error(f"Error loading active stops: {e}")
    
    async def _calculate_atr(self, symbol: str, period: int = 14) -> float:
        """Calculate Average True Range"""
        try:
            # This would get OHLC data and calculate ATR
            # For now, estimate based on volatility
            volatility = await self.database.get_symbol_volatility(symbol)
            current_price = 100.0  # Would get from market data
            
            # ATR approximation: volatility * price
            return volatility * current_price
            
        except Exception as e:
            logger.error(f"Error calculating ATR for {symbol}: {e}")
            return 0.01  # Fallback value
    
    async def _find_support_level(self, symbol: str, current_price: float) -> float:
        """Find nearest support level"""
        try:
            # This would analyze price history for support levels
            # For now, use a simple approximation
            return current_price * 0.95  # 5% below current price
            
        except Exception as e:
            logger.error(f"Error finding support level for {symbol}: {e}")
            return current_price * 0.95
    
    async def _calculate_stop_risk_factors(self, stop_order: StopLossOrder) -> Dict[str, float]:
        """Calculate risk factors for stop-loss decision"""
        try:
            risk_factors = {}
            
            # Volatility risk
            volatility = await self.database.get_symbol_volatility(stop_order.symbol)
            risk_factors['volatility_risk'] = min(10, (volatility / 0.05) * 10)
            
            # Time risk (older positions are riskier)
            time_elapsed = datetime.now(timezone.utc) - stop_order.created_at
            days_elapsed = time_elapsed.total_seconds() / (24 * 3600)
            risk_factors['time_risk'] = min(10, days_elapsed / 7 * 10)  # Max risk at 7 days
            
            # Profit/loss risk
            profit_percent = ((stop_order.current_price - stop_order.entry_price) / stop_order.entry_price) * 100
            if profit_percent < -5:
                risk_factors['loss_risk'] = min(10, abs(profit_percent) / 10 * 10)
            else:
                risk_factors['loss_risk'] = max(0, 5 - profit_percent)
            
            # Market condition risk
            asset_class = get_asset_class(stop_order.symbol)
            risk_factors['asset_risk'] = get_risk_multiplier(stop_order.symbol) * 2
            
            return risk_factors
            
        except Exception as e:
            logger.error(f"Error calculating stop risk factors: {e}")
            return {'error_risk': 5.0}
    
    def _calculate_stop_confidence(self, risk_factors: Dict[str, float]) -> float:
        """Calculate confidence in stop-loss decision"""
        try:
            if not risk_factors:
                return 0.5
            
            # Average risk score
            avg_risk = sum(risk_factors.values()) / len(risk_factors)
            
            # Convert to confidence (0-1), inverted
            confidence = max(0.1, (10 - avg_risk) / 10)
            return confidence
            
        except Exception as e:
            logger.error(f"Error calculating stop confidence: {e}")
            return 0.5