"""
Trade-Level Attribution - Decompose P&L by trade characteristics

Attributes individual trade performance to:
- Entry/exit quality
- Timing
- Holding period
- Market conditions
- Strategy components
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


class AttributionCategory(Enum):
    """Categories for trade attribution"""
    ENTRY_QUALITY = "entry_quality"  # Entry timing
    EXIT_QUALITY = "exit_quality"  # Exit timing
    HOLDING_PERIOD = "holding_period"  # Time in trade
    MARKET_CONDITION = "market_condition"  # Regime
    SIGNAL_TYPE = "signal_type"  # What signal triggered
    TIMEFRAME = "timeframe"  # What timeframe
    SIZE = "size"  # Position size
    COST = "cost"  # Fees and slippage


@dataclass
class TradeAttribution:
    """Attribution for a single trade"""
    
    trade_id: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    
    # Overall P&L
    total_pnl: float
    total_pnl_pct: float
    
    # P&L components
    price_pnl: float  # From price movement
    cost_pnl: float  # From fees/slippage
    funding_pnl: float  # From funding rates
    
    # Entry attribution
    entry_quality_score: float  # 0-1, how good was entry
    entry_slippage: float
    entry_timing_alpha: float  # Early/late vs optimal
    
    # Exit attribution
    exit_quality_score: float  # 0-1, how good was exit
    exit_slippage: float
    exit_timing_alpha: float  # Early/late vs optimal
    
    # Holding period attribution
    holding_days: float
    optimal_holding_days: float  # Based on MAE/MFE
    holding_efficiency: float  # Actual vs optimal
    
    # Market condition attribution
    market_regime: str
    regime_alpha: float  # Performance vs avg in regime
    
    # Strategy component attribution
    signal_type: str
    timeframe: str
    
    # MAE/MFE analysis
    mae_pct: float  # Maximum adverse excursion
    mfe_pct: float  # Maximum favorable excursion
    mae_to_pnl_ratio: float
    mfe_to_pnl_ratio: float


@dataclass
class ComponentContribution:
    """Contribution from a strategy component"""
    
    component_name: str
    component_type: str  # entry, exit, holding, regime, signal
    
    # Performance
    total_pnl: float
    contribution_pct: float
    
    # Quality
    avg_score: float  # Average quality score
    consistency: float  # Std dev of scores
    
    # Volume
    num_trades: int
    avg_pnl_per_trade: float


class TradeAttributor:
    """
    Performs trade-level attribution analysis
    
    Breaks down each trade's P&L into components to understand
    what drives performance.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def attribute_trade(
        self,
        trade: Dict,
        market_data: pd.DataFrame,
        regime_performance: Optional[Dict[str, float]] = None
    ) -> TradeAttribution:
        """
        Attribute a single trade
        
        Args:
            trade: Trade dictionary with entry/exit info
            market_data: OHLCV data for analysis
            regime_performance: Dict of regime -> avg performance
        
        Returns:
            Complete trade attribution
        """
        # Extract trade info
        trade_id = trade.get('trade_id', 'unknown')
        entry_time = trade.get('entry_time')
        exit_time = trade.get('exit_time')
        entry_price = trade.get('entry_price')
        exit_price = trade.get('exit_price')
        side = trade.get('side', 'long')  # long or short
        size = trade.get('size', 1.0)
        
        # P&L components
        total_pnl = trade.get('pnl', 0)
        total_pnl_pct = trade.get('pnl_pct', 0)
        
        price_pnl = trade.get('gross_pnl', total_pnl)
        cost_pnl = trade.get('fees', 0) + trade.get('slippage', 0)
        funding_pnl = trade.get('funding', 0)
        
        # Entry analysis
        entry_quality_score = self._calculate_entry_quality(
            trade, market_data
        )
        entry_slippage = trade.get('entry_slippage', 0)
        entry_timing_alpha = self._calculate_entry_timing_alpha(
            trade, market_data
        )
        
        # Exit analysis
        exit_quality_score = self._calculate_exit_quality(
            trade, market_data
        )
        exit_slippage = trade.get('exit_slippage', 0)
        exit_timing_alpha = self._calculate_exit_timing_alpha(
            trade, market_data
        )
        
        # Holding period
        if entry_time and exit_time:
            holding_days = (exit_time - entry_time).total_seconds() / 86400
        else:
            holding_days = 0
        
        optimal_holding = self._calculate_optimal_holding(trade, market_data)
        holding_efficiency = optimal_holding / holding_days if holding_days > 0 else 0
        
        # Market regime
        market_regime = trade.get('regime', 'unknown')
        regime_alpha = 0.0
        if regime_performance and market_regime in regime_performance:
            avg_regime_perf = regime_performance[market_regime]
            regime_alpha = total_pnl_pct - avg_regime_perf
        
        # Strategy components
        signal_type = trade.get('signal_type', 'unknown')
        timeframe = trade.get('timeframe', 'unknown')
        
        # MAE/MFE
        mae_pct = trade.get('mae_pct', 0)
        mfe_pct = trade.get('mfe_pct', 0)
        mae_to_pnl = abs(mae_pct / total_pnl_pct) if total_pnl_pct != 0 else 0
        mfe_to_pnl = abs(mfe_pct / total_pnl_pct) if total_pnl_pct != 0 else 0
        
        attribution = TradeAttribution(
            trade_id=trade_id,
            entry_time=entry_time,
            exit_time=exit_time,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            price_pnl=price_pnl,
            cost_pnl=cost_pnl,
            funding_pnl=funding_pnl,
            entry_quality_score=entry_quality_score,
            entry_slippage=entry_slippage,
            entry_timing_alpha=entry_timing_alpha,
            exit_quality_score=exit_quality_score,
            exit_slippage=exit_slippage,
            exit_timing_alpha=exit_timing_alpha,
            holding_days=holding_days,
            optimal_holding_days=optimal_holding,
            holding_efficiency=holding_efficiency,
            market_regime=market_regime,
            regime_alpha=regime_alpha,
            signal_type=signal_type,
            timeframe=timeframe,
            mae_pct=mae_pct,
            mfe_pct=mfe_pct,
            mae_to_pnl_ratio=mae_to_pnl,
            mfe_to_pnl_ratio=mfe_to_pnl
        )
        
        return attribution
    
    def attribute_trades(
        self,
        trades: List[Dict],
        market_data: pd.DataFrame
    ) -> List[TradeAttribution]:
        """Attribute multiple trades"""
        
        # Calculate regime performance for context
        regime_performance = self._calculate_regime_performance(trades)
        
        attributions = []
        for trade in trades:
            try:
                attribution = self.attribute_trade(
                    trade, market_data, regime_performance
                )
                attributions.append(attribution)
            except Exception as e:
                self.logger.error(f"Error attributing trade {trade.get('trade_id')}: {e}")
        
        return attributions
    
    def aggregate_by_component(
        self,
        attributions: List[TradeAttribution],
        component_type: AttributionCategory
    ) -> Dict[str, ComponentContribution]:
        """
        Aggregate attributions by component type
        
        Args:
            attributions: List of trade attributions
            component_type: What to aggregate by
        
        Returns:
            Dict of component_name -> contribution
        """
        # Group by component
        components: Dict[str, List[TradeAttribution]] = {}
        
        for attr in attributions:
            if component_type == AttributionCategory.ENTRY_QUALITY:
                # Bucket by entry quality
                if attr.entry_quality_score >= 0.7:
                    key = "high_quality_entry"
                elif attr.entry_quality_score >= 0.4:
                    key = "medium_quality_entry"
                else:
                    key = "low_quality_entry"
            elif component_type == AttributionCategory.EXIT_QUALITY:
                if attr.exit_quality_score >= 0.7:
                    key = "high_quality_exit"
                elif attr.exit_quality_score >= 0.4:
                    key = "medium_quality_exit"
                else:
                    key = "low_quality_exit"
            elif component_type == AttributionCategory.MARKET_CONDITION:
                key = attr.market_regime
            elif component_type == AttributionCategory.SIGNAL_TYPE:
                key = attr.signal_type
            elif component_type == AttributionCategory.TIMEFRAME:
                key = attr.timeframe
            elif component_type == AttributionCategory.HOLDING_PERIOD:
                if attr.holding_days < 1:
                    key = "intraday"
                elif attr.holding_days < 7:
                    key = "short_term"
                else:
                    key = "long_term"
            else:
                key = "other"
            
            if key not in components:
                components[key] = []
            components[key].append(attr)
        
        # Aggregate each component
        contributions = {}
        total_pnl = sum(attr.total_pnl for attr in attributions)
        
        for component_name, component_attrs in components.items():
            component_pnl = sum(attr.total_pnl for attr in component_attrs)
            num_trades = len(component_attrs)
            
            # Quality score (depends on component type)
            if component_type == AttributionCategory.ENTRY_QUALITY:
                scores = [attr.entry_quality_score for attr in component_attrs]
            elif component_type == AttributionCategory.EXIT_QUALITY:
                scores = [attr.exit_quality_score for attr in component_attrs]
            elif component_type == AttributionCategory.HOLDING_PERIOD:
                scores = [attr.holding_efficiency for attr in component_attrs]
            else:
                scores = [1.0] * num_trades  # Default
            
            avg_score = np.mean(scores) if scores else 0
            consistency = np.std(scores) if len(scores) > 1 else 0
            
            contributions[component_name] = ComponentContribution(
                component_name=component_name,
                component_type=component_type.value,
                total_pnl=component_pnl,
                contribution_pct=component_pnl / total_pnl * 100 if total_pnl != 0 else 0,
                avg_score=avg_score,
                consistency=consistency,
                num_trades=num_trades,
                avg_pnl_per_trade=component_pnl / num_trades if num_trades > 0 else 0
            )
        
        return contributions
    
    def _calculate_entry_quality(
        self,
        trade: Dict,
        market_data: pd.DataFrame
    ) -> float:
        """
        Calculate entry quality (0-1 score)
        
        Good entry = entered near support/bottom for longs,
                     near resistance/top for shorts
        """
        entry_time = trade.get('entry_time')
        entry_price = trade.get('entry_price')
        side = trade.get('side', 'long')
        
        if not entry_time or not entry_price:
            return 0.5  # Unknown
        
        # Get surrounding prices (day before and after)
        try:
            entry_idx = market_data.index.get_loc(entry_time, method='nearest')
            window_start = max(0, entry_idx - 24)  # 24 periods before
            window_end = min(len(market_data), entry_idx + 24)  # 24 periods after
            
            window_data = market_data.iloc[window_start:window_end]
            low = window_data['low'].min()
            high = window_data['high'].max()
            
            if high == low:
                return 0.5
            
            # Normalize entry price within window
            if side == 'long':
                # Good long entry = near bottom of range
                score = (high - entry_price) / (high - low)
            else:  # short
                # Good short entry = near top of range
                score = (entry_price - low) / (high - low)
            
            return max(0, min(1, score))
        
        except Exception as e:
            self.logger.debug(f"Error calculating entry quality: {e}")
            return 0.5
    
    def _calculate_exit_quality(
        self,
        trade: Dict,
        market_data: pd.DataFrame
    ) -> float:
        """
        Calculate exit quality (0-1 score)
        
        Good exit = exited near top for longs, near bottom for shorts
        """
        exit_time = trade.get('exit_time')
        exit_price = trade.get('exit_price')
        side = trade.get('side', 'long')
        
        if not exit_time or not exit_price:
            return 0.5
        
        try:
            exit_idx = market_data.index.get_loc(exit_time, method='nearest')
            window_start = max(0, exit_idx - 24)
            window_end = min(len(market_data), exit_idx + 24)
            
            window_data = market_data.iloc[window_start:window_end]
            low = window_data['low'].min()
            high = window_data['high'].max()
            
            if high == low:
                return 0.5
            
            # Normalize exit price
            if side == 'long':
                # Good long exit = near top
                score = (exit_price - low) / (high - low)
            else:  # short
                # Good short exit = near bottom
                score = (high - exit_price) / (high - low)
            
            return max(0, min(1, score))
        
        except Exception as e:
            self.logger.debug(f"Error calculating exit quality: {e}")
            return 0.5
    
    def _calculate_entry_timing_alpha(
        self,
        trade: Dict,
        market_data: pd.DataFrame
    ) -> float:
        """
        Calculate timing alpha for entry
        
        How much better/worse was entry vs average entry in window
        """
        # Simplified: compare to average price in entry day
        entry_time = trade.get('entry_time')
        entry_price = trade.get('entry_price')
        side = trade.get('side', 'long')
        
        if not entry_time or not entry_price:
            return 0.0
        
        try:
            # Get day's prices
            day_data = market_data[market_data.index.date == entry_time.date()]
            if len(day_data) == 0:
                return 0.0
            
            avg_price = day_data['close'].mean()
            
            if side == 'long':
                # Lower entry price = positive alpha
                alpha = (avg_price - entry_price) / avg_price
            else:  # short
                # Higher entry price = positive alpha
                alpha = (entry_price - avg_price) / avg_price
            
            return alpha
        
        except:
            return 0.0
    
    def _calculate_exit_timing_alpha(
        self,
        trade: Dict,
        market_data: pd.DataFrame
    ) -> float:
        """Calculate timing alpha for exit"""
        exit_time = trade.get('exit_time')
        exit_price = trade.get('exit_price')
        side = trade.get('side', 'long')
        
        if not exit_time or not exit_price:
            return 0.0
        
        try:
            day_data = market_data[market_data.index.date == exit_time.date()]
            if len(day_data) == 0:
                return 0.0
            
            avg_price = day_data['close'].mean()
            
            if side == 'long':
                # Higher exit price = positive alpha
                alpha = (exit_price - avg_price) / avg_price
            else:  # short
                # Lower exit price = positive alpha
                alpha = (avg_price - exit_price) / avg_price
            
            return alpha
        
        except:
            return 0.0
    
    def _calculate_optimal_holding(
        self,
        trade: Dict,
        market_data: pd.DataFrame
    ) -> float:
        """
        Calculate optimal holding period based on MFE
        
        Returns days to reach MFE
        """
        # Would need tick data to be precise
        # Simplified: use MFE to estimate
        mfe_pct = abs(trade.get('mfe_pct', 0))
        pnl_pct = abs(trade.get('pnl_pct', 0))
        holding_days = trade.get('holding_days', 0)
        
        if pnl_pct == 0 or holding_days == 0:
            return holding_days
        
        # Estimate: optimal = holding * (pnl / mfe)
        # If captured all of MFE, ratio = 1, optimal = holding
        # If captured half of MFE, optimal would be less
        ratio = pnl_pct / mfe_pct if mfe_pct > 0 else 1.0
        optimal = holding_days * ratio
        
        return optimal
    
    def _calculate_regime_performance(
        self,
        trades: List[Dict]
    ) -> Dict[str, float]:
        """Calculate average performance by regime"""
        regime_pnls = {}
        regime_counts = {}
        
        for trade in trades:
            regime = trade.get('regime', 'unknown')
            pnl_pct = trade.get('pnl_pct', 0)
            
            if regime not in regime_pnls:
                regime_pnls[regime] = 0
                regime_counts[regime] = 0
            
            regime_pnls[regime] += pnl_pct
            regime_counts[regime] += 1
        
        # Average
        regime_performance = {
            regime: pnls / regime_counts[regime] if regime_counts[regime] > 0 else 0
            for regime, pnls in regime_pnls.items()
        }
        
        return regime_performance
