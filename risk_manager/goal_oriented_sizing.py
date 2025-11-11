"""
Goal-Oriented Position Sizing Module

This module implements goal-based position sizing adjustments for the MasterTrade system.
It adjusts position sizes based on progress toward financial goals:
- 10% monthly return target
- €4k monthly income target
- €1M portfolio value target

The module integrates with the existing PositionSizingEngine to provide dynamic
position size adjustments based on current goal progress.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any
from decimal import Decimal
import structlog

from database import RiskPostgresDatabase

logger = structlog.get_logger()


class GoalOrientedSizingModule:
    """
    Calculate position size adjustments based on financial goal progress
    
    Adjustment Strategy:
    - Behind on goals: Increase position size (1.1x to 1.3x) to accelerate progress
    - On track: Normal sizing (1.0x)
    - Ahead of goals: Reduce sizing (0.7x to 0.9x) to protect gains
    - Near €1M target: Capital preservation mode (0.5x to 0.7x)
    
    Goal Thresholds:
    - Monthly Return: 10% target
    - Monthly Income: €4,000 target
    - Portfolio Value: €1,000,000 target
    """
    
    # Goal targets
    TARGET_MONTHLY_RETURN = 0.10  # 10%
    TARGET_MONTHLY_INCOME = 4000.0  # €4,000
    TARGET_PORTFOLIO_VALUE = 1_000_000.0  # €1M
    
    # Adjustment factors
    MAX_AGGRESSIVE_FACTOR = 1.3  # Maximum increase when behind
    NORMAL_FACTOR = 1.0  # On track
    MIN_CONSERVATIVE_FACTOR = 0.5  # Maximum reduction for capital preservation
    
    # Progress thresholds
    AHEAD_THRESHOLD = 1.15  # 115% of target - ahead of goal
    ON_TRACK_MIN = 0.85  # 85% of target - minimum for on-track
    AT_RISK_THRESHOLD = 0.70  # 70% of target - goal at risk
    CRITICAL_THRESHOLD = 0.50  # 50% of target - critical situation
    
    # Portfolio milestones for preservation mode
    PRESERVATION_START = 800_000.0  # Start reducing risk at €800k
    PRESERVATION_FULL = 950_000.0  # Full preservation mode at €950k
    
    def __init__(self, database: RiskPostgresDatabase):
        """
        Initialize goal-oriented sizing module
        
        Args:
            database: Risk manager database instance
        """
        self.database = database
        logger.info("Goal-oriented sizing module initialized")
        
    async def calculate_goal_adjustment_factor(
        self,
        current_portfolio_value: float,
        monthly_return_progress: float,
        monthly_income_progress: float,
        days_into_month: Optional[int] = None
    ) -> float:
        """
        Calculate position size adjustment based on goal progress
        
        Args:
            current_portfolio_value: Current portfolio value in EUR
            monthly_return_progress: Progress toward monthly return goal (0.0 to 1.5+)
            monthly_income_progress: Progress toward monthly income goal (0.0 to 1.5+)
            days_into_month: Days elapsed in current month (for time-based adjustments)
            
        Returns:
            Adjustment factor between 0.5 and 1.3
        """
        try:
            # Calculate days into month if not provided
            if days_into_month is None:
                now = datetime.now(timezone.utc)
                days_into_month = now.day
                days_in_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                days_in_month = days_in_month.day
            else:
                days_in_month = 30  # Default assumption
                
            month_progress_ratio = days_into_month / days_in_month
            
            # Calculate individual adjustment factors
            return_factor = self._calculate_return_factor(
                monthly_return_progress,
                month_progress_ratio
            )
            
            income_factor = self._calculate_income_factor(
                monthly_income_progress,
                month_progress_ratio
            )
            
            portfolio_factor = self._calculate_portfolio_factor(
                current_portfolio_value
            )
            
            # Combine factors with weights
            # Portfolio preservation takes priority as we approach €1M
            if current_portfolio_value >= self.PRESERVATION_START:
                # Weight heavily toward portfolio preservation
                combined_factor = (
                    portfolio_factor * 0.6 +
                    return_factor * 0.25 +
                    income_factor * 0.15
                )
            else:
                # Balanced weighting for growth phase
                combined_factor = (
                    return_factor * 0.4 +
                    income_factor * 0.35 +
                    portfolio_factor * 0.25
                )
            
            # Ensure factor stays within bounds
            final_factor = max(
                self.MIN_CONSERVATIVE_FACTOR,
                min(self.MAX_AGGRESSIVE_FACTOR, combined_factor)
            )
            
            logger.info(
                "Goal adjustment factor calculated",
                portfolio_value=current_portfolio_value,
                return_progress=monthly_return_progress,
                income_progress=monthly_income_progress,
                days_into_month=days_into_month,
                return_factor=return_factor,
                income_factor=income_factor,
                portfolio_factor=portfolio_factor,
                final_factor=final_factor
            )
            
            return final_factor
            
        except Exception as e:
            logger.error("Error calculating goal adjustment factor", error=str(e))
            return self.NORMAL_FACTOR  # Fallback to normal sizing
            
    def _calculate_return_factor(
        self,
        progress: float,
        month_progress: float
    ) -> float:
        """
        Calculate adjustment based on monthly return progress
        
        Args:
            progress: Current progress (0.0 = 0%, 1.0 = 100% of target)
            month_progress: Fraction of month elapsed (0.0 to 1.0)
            
        Returns:
            Adjustment factor for return goal
        """
        # Expected progress based on time
        expected_progress = month_progress
        
        # Calculate variance from expected
        variance = progress - expected_progress
        
        if progress >= self.AHEAD_THRESHOLD:
            # Significantly ahead - reduce risk
            return 0.75
            
        elif progress >= self.ON_TRACK_MIN:
            # On track - normal sizing
            return 1.0
            
        elif progress >= self.AT_RISK_THRESHOLD:
            # Slightly behind - modest increase
            return 1.15
            
        elif progress >= self.CRITICAL_THRESHOLD:
            # Behind - more aggressive
            return 1.25
            
        else:
            # Critical situation - maximum aggression (with caution)
            # But not too aggressive to avoid excessive risk
            return 1.20  # Slightly less than max to avoid desperation trades
            
    def _calculate_income_factor(
        self,
        progress: float,
        month_progress: float
    ) -> float:
        """
        Calculate adjustment based on monthly income progress
        
        Args:
            progress: Current progress (0.0 = €0, 1.0 = €4k target)
            month_progress: Fraction of month elapsed
            
        Returns:
            Adjustment factor for income goal
        """
        # Income should accumulate linearly through month
        expected_progress = month_progress
        
        if progress >= self.AHEAD_THRESHOLD:
            # Ahead on income - can afford to be conservative
            return 0.80
            
        elif progress >= self.ON_TRACK_MIN:
            # On track for income target
            return 1.0
            
        elif progress >= self.AT_RISK_THRESHOLD:
            # Need to increase activity for income
            return 1.1
            
        elif progress >= self.CRITICAL_THRESHOLD:
            # Behind on income - increase position frequency
            return 1.2
            
        else:
            # Critical - need significant income
            return 1.25
            
    def _calculate_portfolio_factor(
        self,
        current_value: float
    ) -> float:
        """
        Calculate adjustment based on portfolio value and preservation strategy
        
        Args:
            current_value: Current portfolio value in EUR
            
        Returns:
            Adjustment factor for portfolio milestone
        """
        if current_value >= self.PRESERVATION_FULL:
            # At or above €950k - maximum capital preservation
            return 0.5
            
        elif current_value >= self.PRESERVATION_START:
            # Between €800k and €950k - gradual risk reduction
            # Linear interpolation between 1.0 and 0.5
            progress_to_preservation = (
                (current_value - self.PRESERVATION_START) /
                (self.PRESERVATION_FULL - self.PRESERVATION_START)
            )
            return 1.0 - (0.5 * progress_to_preservation)
            
        elif current_value >= 500_000:
            # €500k to €800k - balanced growth mode
            return 1.0
            
        elif current_value >= 250_000:
            # €250k to €500k - growth mode
            return 1.05
            
        elif current_value >= 100_000:
            # €100k to €250k - accelerated growth
            return 1.1
            
        else:
            # Below €100k - aggressive growth needed but controlled
            return 1.15
            
    async def get_goal_status(self) -> Dict[str, Any]:
        """
        Get current status of all financial goals
        
        Returns:
            Dictionary with goal progress and status
        """
        try:
            # Fetch current goal progress from database
            progress_data = await self.database.get_current_goal_progress()
            
            now = datetime.now(timezone.utc)
            days_into_month = now.day
            
            return {
                "timestamp": now.isoformat(),
                "days_into_month": days_into_month,
                "monthly_return": {
                    "target": self.TARGET_MONTHLY_RETURN,
                    "current": progress_data.get("monthly_return_progress", 0.0),
                    "status": self._get_status_label(
                        progress_data.get("monthly_return_progress", 0.0)
                    )
                },
                "monthly_income": {
                    "target": self.TARGET_MONTHLY_INCOME,
                    "current": progress_data.get("monthly_income_progress", 0.0),
                    "status": self._get_status_label(
                        progress_data.get("monthly_income_progress", 0.0)
                    )
                },
                "portfolio_value": {
                    "target": self.TARGET_PORTFOLIO_VALUE,
                    "current": progress_data.get("portfolio_value", 0.0),
                    "progress": progress_data.get("portfolio_value", 0.0) / self.TARGET_PORTFOLIO_VALUE,
                    "preservation_mode": progress_data.get("portfolio_value", 0.0) >= self.PRESERVATION_START
                }
            }
            
        except Exception as e:
            logger.error("Error getting goal status", error=str(e))
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
    def _get_status_label(self, progress: float) -> str:
        """Get human-readable status label for progress"""
        if progress >= self.AHEAD_THRESHOLD:
            return "ahead"
        elif progress >= self.ON_TRACK_MIN:
            return "on_track"
        elif progress >= self.AT_RISK_THRESHOLD:
            return "at_risk"
        elif progress >= self.CRITICAL_THRESHOLD:
            return "behind"
        else:
            return "critical"
            
    async def log_adjustment_decision(
        self,
        portfolio_value: float,
        adjustment_factor: float,
        reason: str
    ):
        """
        Log position sizing adjustment decision for audit trail
        
        Args:
            portfolio_value: Current portfolio value
            adjustment_factor: Applied adjustment factor
            reason: Reason for adjustment
        """
        try:
            await self.database.log_goal_adjustment(
                portfolio_value=portfolio_value,
                adjustment_factor=adjustment_factor,
                reason=reason
            )
        except Exception as e:
            logger.error("Error logging adjustment decision", error=str(e))
