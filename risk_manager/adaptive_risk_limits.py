"""
Adaptive Risk Limits Module

Dynamically adjusts portfolio risk limits based on financial goal progress.
Integrates with goal tracking service to implement goal-oriented risk management.

Risk Adjustment Strategy:
- Behind on goals (< 70% progress): Increase risk to 12-15% (aggressive)
- At risk (70-85% progress): Moderate risk adjustment to 10-12%
- On track (85-100% progress): Standard risk at 10%
- Ahead (100-110% progress): Reduce risk to 7-10% (conservative)
- Near portfolio milestone (>90% of target): Reduce risk to 3-5% (protective)

Features:
- Real-time risk limit calculation based on goal progress
- Integration with PortfolioRiskController
- Audit logging of all risk adjustments
- Configurable thresholds and risk bands
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
import structlog

from database import RiskPostgresDatabase
from config import settings

logger = structlog.get_logger(__name__)


class RiskStance(Enum):
    """Risk management stance based on goal progress"""
    PROTECTIVE = "protective"      # Near milestone - very conservative (3-5%)
    CONSERVATIVE = "conservative"  # Ahead of goals - conservative (7-10%)
    BALANCED = "balanced"          # On track - standard (10%)
    MODERATE = "moderate"          # At risk - moderate aggressive (10-12%)
    AGGRESSIVE = "aggressive"      # Behind - aggressive (12-15%)


@dataclass
class RiskAdjustment:
    """Risk limit adjustment result"""
    stance: RiskStance
    risk_limit_percent: float
    base_limit_percent: float
    adjustment_factor: float
    reason: str
    goal_progress: Dict[str, float]
    timestamp: datetime


class AdaptiveRiskLimits:
    """
    Adaptive Risk Limits Manager
    
    Dynamically adjusts MAX_PORTFOLIO_RISK_PERCENT based on financial goal progress.
    Implements goal-oriented risk management strategy.
    """
    
    def __init__(self, database: RiskPostgresDatabase, base_risk_percent: float = 10.0):
        """
        Initialize adaptive risk limits
        
        Args:
            database: Database instance for goal progress queries
            base_risk_percent: Base portfolio risk limit (default 10%)
        """
        self.database = database
        self.base_risk_percent = base_risk_percent
        
        # Risk adjustment thresholds
        self.threshold_behind = 0.70        # < 70% progress = behind
        self.threshold_at_risk = 0.85       # 70-85% = at risk
        self.threshold_on_track = 1.00      # 85-100% = on track
        self.threshold_ahead = 1.10         # 100-110% = ahead
        self.threshold_milestone = 0.90     # >90% of portfolio target = protective
        
        # Risk limit bands (percentage of portfolio)
        self.risk_bands = {
            RiskStance.PROTECTIVE: (3.0, 5.0),      # Near milestone
            RiskStance.CONSERVATIVE: (7.0, 10.0),   # Ahead
            RiskStance.BALANCED: (10.0, 10.0),      # On track
            RiskStance.MODERATE: (10.0, 12.0),      # At risk
            RiskStance.AGGRESSIVE: (12.0, 15.0)     # Behind
        }
        
        # Cache
        self.last_adjustment: Optional[RiskAdjustment] = None
        self.last_update_time: Optional[datetime] = None
        self.cache_duration_seconds = 300  # 5 minutes
        
        logger.info("Adaptive risk limits initialized",
                   base_risk_percent=base_risk_percent,
                   risk_bands=self.risk_bands)
    
    async def calculate_risk_limit(self) -> RiskAdjustment:
        """
        Calculate current portfolio risk limit based on goal progress
        
        Returns:
            RiskAdjustment with recommended risk limit and reasoning
        """
        try:
            # Check cache
            if self._should_use_cache():
                logger.debug("Using cached risk adjustment")
                return self.last_adjustment
            
            # Get current goal progress
            goal_progress = await self._fetch_goal_progress()
            
            if not goal_progress:
                logger.warning("No goal progress data available, using base risk limit")
                return self._create_default_adjustment()
            
            # Determine risk stance based on goal progress
            stance, reason = self._determine_risk_stance(goal_progress)
            
            # Calculate adjusted risk limit
            risk_limit = self._calculate_risk_limit_for_stance(stance, goal_progress)
            
            # Calculate adjustment factor
            adjustment_factor = risk_limit / self.base_risk_percent
            
            # Create adjustment result
            adjustment = RiskAdjustment(
                stance=stance,
                risk_limit_percent=risk_limit,
                base_limit_percent=self.base_risk_percent,
                adjustment_factor=adjustment_factor,
                reason=reason,
                goal_progress=goal_progress,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Update cache
            self.last_adjustment = adjustment
            self.last_update_time = datetime.now(timezone.utc)
            
            # Log adjustment
            await self._log_adjustment(adjustment)
            
            logger.info("Risk limit calculated",
                       stance=stance.value,
                       risk_limit=f"{risk_limit:.1f}%",
                       adjustment_factor=f"{adjustment_factor:.2f}x",
                       reason=reason)
            
            return adjustment
            
        except Exception as e:
            logger.error(f"Error calculating risk limit: {e}", exc_info=True)
            return self._create_default_adjustment()
    
    async def get_current_risk_limit(self) -> float:
        """
        Get current portfolio risk limit percentage
        
        Returns:
            Risk limit as percentage (e.g., 10.0 for 10%)
        """
        adjustment = await self.calculate_risk_limit()
        return adjustment.risk_limit_percent
    
    def _should_use_cache(self) -> bool:
        """Check if cached adjustment is still valid"""
        if not self.last_adjustment or not self.last_update_time:
            return False
        
        elapsed = (datetime.now(timezone.utc) - self.last_update_time).total_seconds()
        return elapsed < self.cache_duration_seconds
    
    async def _fetch_goal_progress(self) -> Dict[str, float]:
        """
        Fetch current goal progress from database
        
        Returns:
            Dict with goal progress percentages (0.0 to 1.0+)
        """
        try:
            # Get all goals status
            goals = await self.database.get_all_goals_status()
            
            if not goals:
                return {}
            
            progress_dict = {}
            for goal in goals:
                goal_type = goal.get('goal_type')
                progress_percent = float(goal.get('progress_percent', 0))
                progress_dict[goal_type] = progress_percent / 100.0  # Convert to decimal
            
            return progress_dict
            
        except Exception as e:
            logger.error(f"Error fetching goal progress: {e}")
            return {}
    
    def _determine_risk_stance(self, goal_progress: Dict[str, float]) -> Tuple[RiskStance, str]:
        """
        Determine risk stance based on goal progress
        
        Args:
            goal_progress: Dict of goal_type -> progress (0.0 to 1.0+)
        
        Returns:
            Tuple of (RiskStance, reason string)
        """
        # Check for portfolio milestone protection
        portfolio_progress = goal_progress.get('portfolio_value', 0.0)
        if portfolio_progress >= self.threshold_milestone:
            return (
                RiskStance.PROTECTIVE,
                f"Portfolio near milestone ({portfolio_progress:.1%}), protecting gains"
            )
        
        # Calculate average progress across all goals
        if not goal_progress:
            return RiskStance.BALANCED, "No goal data, using balanced risk"
        
        avg_progress = sum(goal_progress.values()) / len(goal_progress)
        
        # Count goals by status
        behind_count = sum(1 for p in goal_progress.values() if p < self.threshold_behind)
        at_risk_count = sum(1 for p in goal_progress.values() 
                           if self.threshold_behind <= p < self.threshold_at_risk)
        ahead_count = sum(1 for p in goal_progress.values() if p >= self.threshold_ahead)
        
        # Determine stance based on progress
        if behind_count >= 2 or avg_progress < self.threshold_behind:
            return (
                RiskStance.AGGRESSIVE,
                f"{behind_count} goals behind, avg progress {avg_progress:.1%}, need aggressive approach"
            )
        elif behind_count == 1 or at_risk_count >= 2 or avg_progress < self.threshold_at_risk:
            return (
                RiskStance.MODERATE,
                f"{at_risk_count} goals at risk, avg progress {avg_progress:.1%}, moderate approach"
            )
        elif ahead_count >= 2 or avg_progress >= self.threshold_ahead:
            return (
                RiskStance.CONSERVATIVE,
                f"{ahead_count} goals ahead, avg progress {avg_progress:.1%}, protecting gains"
            )
        elif ahead_count == 1 or avg_progress >= self.threshold_on_track:
            return (
                RiskStance.CONSERVATIVE,
                f"Avg progress {avg_progress:.1%}, slightly conservative"
            )
        else:
            return (
                RiskStance.BALANCED,
                f"Avg progress {avg_progress:.1%}, on track with balanced risk"
            )
    
    def _calculate_risk_limit_for_stance(self, stance: RiskStance, 
                                         goal_progress: Dict[str, float]) -> float:
        """
        Calculate risk limit for given stance
        
        Args:
            stance: Risk stance
            goal_progress: Goal progress data
        
        Returns:
            Risk limit percentage
        """
        min_risk, max_risk = self.risk_bands[stance]
        
        # For balanced stance, use base risk
        if stance == RiskStance.BALANCED:
            return self.base_risk_percent
        
        # For other stances, interpolate based on progress
        avg_progress = sum(goal_progress.values()) / len(goal_progress) if goal_progress else 0.5
        
        if stance == RiskStance.AGGRESSIVE:
            # More behind = higher risk (closer to max_risk)
            factor = max(0.0, 1.0 - avg_progress / self.threshold_behind)
            return min_risk + (max_risk - min_risk) * factor
        
        elif stance == RiskStance.MODERATE:
            # Scale between min and max based on progress
            factor = (avg_progress - self.threshold_behind) / (self.threshold_at_risk - self.threshold_behind)
            factor = max(0.0, min(1.0, 1.0 - factor))
            return min_risk + (max_risk - min_risk) * factor
        
        elif stance == RiskStance.CONSERVATIVE:
            # More ahead = lower risk (closer to min_risk)
            factor = min(1.0, (avg_progress - self.threshold_on_track) / 0.1)
            return max_risk - (max_risk - min_risk) * factor
        
        elif stance == RiskStance.PROTECTIVE:
            # Near milestone = minimum risk
            portfolio_progress = goal_progress.get('portfolio_value', 0.9)
            factor = (portfolio_progress - self.threshold_milestone) / (1.0 - self.threshold_milestone)
            factor = max(0.0, min(1.0, factor))
            return max_risk - (max_risk - min_risk) * factor
        
        return self.base_risk_percent
    
    def _create_default_adjustment(self) -> RiskAdjustment:
        """Create default adjustment when goal data unavailable"""
        return RiskAdjustment(
            stance=RiskStance.BALANCED,
            risk_limit_percent=self.base_risk_percent,
            base_limit_percent=self.base_risk_percent,
            adjustment_factor=1.0,
            reason="Using default risk limit (no goal data)",
            goal_progress={},
            timestamp=datetime.now(timezone.utc)
        )
    
    async def _log_adjustment(self, adjustment: RiskAdjustment):
        """Log risk adjustment to database for audit trail"""
        try:
            # Store adjustment in database
            await self.database.execute("""
                INSERT INTO risk_limit_adjustments 
                (stance, risk_limit_percent, base_limit_percent, adjustment_factor, 
                 reason, goal_progress, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, 
            adjustment.stance.value,
            adjustment.risk_limit_percent,
            adjustment.base_limit_percent,
            adjustment.adjustment_factor,
            adjustment.reason,
            str(adjustment.goal_progress),  # Store as JSON string
            adjustment.timestamp
            )
            
        except Exception as e:
            # Non-critical - log but don't fail
            logger.warning(f"Failed to log risk adjustment: {e}")
    
    def get_risk_stance_description(self, stance: RiskStance) -> str:
        """Get human-readable description of risk stance"""
        descriptions = {
            RiskStance.PROTECTIVE: "Protective (near milestone, preserving capital)",
            RiskStance.CONSERVATIVE: "Conservative (ahead of goals, protecting gains)",
            RiskStance.BALANCED: "Balanced (on track, standard risk)",
            RiskStance.MODERATE: "Moderate (at risk, moderate aggressive)",
            RiskStance.AGGRESSIVE: "Aggressive (behind goals, taking more risk)"
        }
        return descriptions.get(stance, "Unknown")
