"""
Goal-Based Drawdown Protection

Dynamically adjusts drawdown limits based on financial goal progress:
- Normal operation: 5% monthly drawdown limit
- Approaching milestone (>90% of €1M): 2% monthly drawdown limit (protective mode)
- Actions on breach: Pause new positions, reduce existing positions by 50%
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)


class DrawdownStance(str, Enum):
    """Drawdown protection stance based on goal progress"""
    NORMAL = "normal"  # Standard 5% limit
    PROTECTIVE = "protective"  # Near milestone, 2% limit
    BREACHED = "breached"  # Drawdown limit exceeded


class DrawdownAction(str, Enum):
    """Actions to take when drawdown limit is breached"""
    NONE = "none"  # No action needed
    PAUSE_NEW = "pause_new"  # Pause new position opening
    REDUCE_POSITIONS = "reduce_positions"  # Reduce existing positions by 50%
    CLOSE_ALL = "close_all"  # Emergency: close all positions


@dataclass
class DrawdownLimit:
    """Drawdown limit configuration"""
    stance: DrawdownStance
    monthly_limit_percent: float  # Maximum monthly drawdown percentage
    current_drawdown_percent: float  # Current month's drawdown
    is_breached: bool
    required_actions: List[DrawdownAction]
    reason: str
    portfolio_value: float
    peak_value: float  # This month's peak value
    goal_progress_percent: float  # Progress toward €1M goal


@dataclass
class DrawdownEvent:
    """Record of a drawdown breach event"""
    timestamp: datetime
    stance: DrawdownStance
    monthly_limit_percent: float
    actual_drawdown_percent: float
    portfolio_value: float
    peak_value: float
    actions_taken: List[DrawdownAction]
    reason: str


class GoalBasedDrawdownProtector:
    """
    Implements goal-based drawdown protection with dynamic limits.
    
    Features:
    - Dynamic drawdown limits based on goal progress (5% normal, 2% protective)
    - Monthly drawdown tracking with peak value monitoring
    - Automatic protective actions (pause new, reduce existing, close all)
    - Integration with goal tracking for €1M milestone protection
    - Database logging of all drawdown events for audit trail
    """
    
    def __init__(
        self,
        database,
        normal_limit_percent: float = 5.0,
        protective_limit_percent: float = 2.0,
        milestone_threshold: float = 0.90  # >90% of €1M triggers protective mode
    ):
        """
        Initialize drawdown protector.
        
        Args:
            database: RiskPostgresDatabase instance
            normal_limit_percent: Standard monthly drawdown limit (default 5%)
            protective_limit_percent: Protective monthly drawdown limit near milestone (default 2%)
            milestone_threshold: Progress threshold that triggers protective mode (default 0.90 = 90%)
        """
        self.database = database
        self.normal_limit = normal_limit_percent
        self.protective_limit = protective_limit_percent
        self.milestone_threshold = milestone_threshold
        
        # Cache for goal progress to avoid excessive queries
        self._goal_progress_cache: Optional[float] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_duration = timedelta(minutes=5)
        
        # Track monthly peak for drawdown calculation
        self._monthly_peak: Optional[float] = None
        self._peak_month: Optional[int] = None
        
        logger.info(
            "Goal-based drawdown protector initialized",
            normal_limit=normal_limit_percent,
            protective_limit=protective_limit_percent,
            milestone_threshold=milestone_threshold
        )
    
    async def calculate_drawdown_protection(
        self,
        current_portfolio_value: float
    ) -> DrawdownLimit:
        """
        Calculate drawdown limits and required actions based on goal progress.
        
        Args:
            current_portfolio_value: Current total portfolio value
            
        Returns:
            DrawdownLimit with stance, limits, and required actions
        """
        try:
            # Get goal progress (with caching)
            goal_progress = await self._get_goal_progress()
            
            # Determine protection stance
            stance = self._determine_stance(goal_progress)
            
            # Get appropriate drawdown limit
            if stance == DrawdownStance.PROTECTIVE:
                limit_percent = self.protective_limit
            else:
                limit_percent = self.normal_limit
            
            # Calculate current monthly drawdown
            monthly_peak = await self._get_monthly_peak(current_portfolio_value)
            current_drawdown_percent = self._calculate_drawdown(
                current_portfolio_value,
                monthly_peak
            )
            
            # Determine if breached and what actions to take
            is_breached = current_drawdown_percent > limit_percent
            required_actions = self._determine_actions(
                stance,
                current_drawdown_percent,
                limit_percent,
                is_breached
            )
            
            # Build reason string
            reason = self._build_reason(
                stance,
                goal_progress,
                current_drawdown_percent,
                limit_percent,
                is_breached
            )
            
            # Create result
            result = DrawdownLimit(
                stance=DrawdownStance.BREACHED if is_breached else stance,
                monthly_limit_percent=limit_percent,
                current_drawdown_percent=current_drawdown_percent,
                is_breached=is_breached,
                required_actions=required_actions,
                reason=reason,
                portfolio_value=current_portfolio_value,
                peak_value=monthly_peak,
                goal_progress_percent=goal_progress * 100
            )
            
            # Log event if breached
            if is_breached:
                await self._log_drawdown_event(result, required_actions)
                logger.warning(
                    "Drawdown limit breached",
                    stance=stance.value,
                    limit=limit_percent,
                    actual=current_drawdown_percent,
                    actions=required_actions
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating drawdown protection: {e}")
            # Return safe defaults on error
            return self._create_safe_default(current_portfolio_value)
    
    async def get_current_protection_status(
        self,
        current_portfolio_value: float
    ) -> Dict:
        """
        Get current drawdown protection status in dict format.
        
        Returns dict with:
        - stance, limit, current_drawdown, is_breached, actions, reason
        """
        limit = await self.calculate_drawdown_protection(current_portfolio_value)
        return {
            "stance": limit.stance.value,
            "monthly_limit_percent": limit.monthly_limit_percent,
            "current_drawdown_percent": limit.current_drawdown_percent,
            "is_breached": limit.is_breached,
            "required_actions": [action.value for action in limit.required_actions],
            "reason": limit.reason,
            "portfolio_value": limit.portfolio_value,
            "peak_value": limit.peak_value,
            "goal_progress_percent": limit.goal_progress_percent
        }
    
    async def _get_goal_progress(self) -> float:
        """
        Get progress toward €1M portfolio goal (cached for 5 minutes).
        
        Returns progress as decimal (0.0 to 1.0+)
        """
        # Check cache
        if self._should_use_cache():
            return self._goal_progress_cache
        
        try:
            # Query goal status
            goals = await self.database.get_all_goals_status()
            
            # Find portfolio value goal (€1M target)
            portfolio_goal = None
            for goal in goals:
                if goal.get("name") == "Portfolio Value" or goal.get("target", 0) == 1000000:
                    portfolio_goal = goal
                    break
            
            if not portfolio_goal:
                logger.warning("Portfolio value goal not found, assuming 0% progress")
                progress = 0.0
            else:
                progress = portfolio_goal.get("progress_percent", 0) / 100.0
            
            # Update cache
            self._goal_progress_cache = progress
            self._cache_timestamp = datetime.utcnow()
            
            return progress
            
        except Exception as e:
            logger.error(f"Error fetching goal progress: {e}")
            # Return cached value if available, else 0
            return self._goal_progress_cache if self._goal_progress_cache is not None else 0.0
    
    def _should_use_cache(self) -> bool:
        """Check if cached goal progress is still valid"""
        if self._goal_progress_cache is None or self._cache_timestamp is None:
            return False
        
        elapsed = datetime.utcnow() - self._cache_timestamp
        return elapsed < self._cache_duration
    
    def _determine_stance(self, goal_progress: float) -> DrawdownStance:
        """
        Determine protection stance based on goal progress.
        
        Args:
            goal_progress: Progress toward €1M goal (0.0 to 1.0+)
            
        Returns:
            PROTECTIVE if >90% of €1M, else NORMAL
        """
        if goal_progress >= self.milestone_threshold:
            return DrawdownStance.PROTECTIVE
        else:
            return DrawdownStance.NORMAL
    
    async def _get_monthly_peak(self, current_value: float) -> float:
        """
        Get or update monthly peak portfolio value.
        
        Resets at start of new month.
        """
        current_month = datetime.utcnow().month
        
        # Reset peak at start of new month
        if self._peak_month != current_month:
            self._monthly_peak = current_value
            self._peak_month = current_month
            logger.info(
                "Monthly peak reset for new month",
                month=current_month,
                peak=current_value
            )
        
        # Update peak if current value is higher
        if self._monthly_peak is None or current_value > self._monthly_peak:
            self._monthly_peak = current_value
        
        return self._monthly_peak
    
    def _calculate_drawdown(self, current_value: float, peak_value: float) -> float:
        """
        Calculate drawdown percentage from peak.
        
        Returns percentage (e.g., 3.5 for 3.5% drawdown)
        """
        if peak_value <= 0:
            return 0.0
        
        drawdown = ((peak_value - current_value) / peak_value) * 100
        return max(0.0, drawdown)  # Can't be negative
    
    def _determine_actions(
        self,
        stance: DrawdownStance,
        current_drawdown: float,
        limit: float,
        is_breached: bool
    ) -> List[DrawdownAction]:
        """
        Determine required actions based on drawdown breach severity.
        
        Actions:
        - No breach: No action
        - Minor breach (<1.5x limit): Pause new positions
        - Moderate breach (1.5x-2x limit): Pause new + reduce existing by 50%
        - Severe breach (>2x limit): Close all positions (emergency)
        """
        if not is_breached:
            return [DrawdownAction.NONE]
        
        breach_severity = current_drawdown / limit
        
        if breach_severity > 2.0:
            # Severe breach: Emergency close all
            return [DrawdownAction.CLOSE_ALL]
        elif breach_severity > 1.5:
            # Moderate breach: Pause new + reduce existing
            return [DrawdownAction.PAUSE_NEW, DrawdownAction.REDUCE_POSITIONS]
        else:
            # Minor breach: Just pause new positions
            return [DrawdownAction.PAUSE_NEW]
    
    def _build_reason(
        self,
        stance: DrawdownStance,
        goal_progress: float,
        current_drawdown: float,
        limit: float,
        is_breached: bool
    ) -> str:
        """Build human-readable reason string"""
        progress_pct = goal_progress * 100
        
        if stance == DrawdownStance.PROTECTIVE:
            base = f"Protective mode active (portfolio at {progress_pct:.1f}% of €1M goal)"
        else:
            base = f"Normal protection mode (portfolio at {progress_pct:.1f}% of €1M goal)"
        
        status = f", current drawdown: {current_drawdown:.2f}% vs {limit:.1f}% limit"
        
        if is_breached:
            return base + status + " - LIMIT BREACHED"
        else:
            return base + status + " - within limits"
    
    async def _log_drawdown_event(
        self,
        limit: DrawdownLimit,
        actions: List[DrawdownAction]
    ):
        """Log drawdown breach event to database"""
        try:
            # Insert into drawdown_events table
            query = """
                INSERT INTO drawdown_events (
                    stance, monthly_limit_percent, actual_drawdown_percent,
                    portfolio_value, peak_value, actions_taken, reason, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """
            actions_str = ",".join([action.value for action in actions])
            
            await self.database._postgres.pool.execute(
                query,
                limit.stance.value,
                limit.monthly_limit_percent,
                limit.current_drawdown_percent,
                limit.portfolio_value,
                limit.peak_value,
                actions_str,
                limit.reason,
                datetime.utcnow()
            )
            
            logger.info("Drawdown event logged to database")
            
        except Exception as e:
            # Non-critical - log but don't fail
            logger.error(f"Failed to log drawdown event: {e}")
    
    def _create_safe_default(self, current_value: float) -> DrawdownLimit:
        """Create conservative default on error"""
        return DrawdownLimit(
            stance=DrawdownStance.NORMAL,
            monthly_limit_percent=self.normal_limit,
            current_drawdown_percent=0.0,
            is_breached=False,
            required_actions=[DrawdownAction.NONE],
            reason="Error calculating drawdown - using safe defaults",
            portfolio_value=current_value,
            peak_value=current_value,
            goal_progress_percent=0.0
        )
    
    def get_protection_description(self, stance: DrawdownStance) -> str:
        """Get human-readable description for protection stance"""
        if stance == DrawdownStance.NORMAL:
            return f"Normal protection: {self.normal_limit}% monthly drawdown limit"
        elif stance == DrawdownStance.PROTECTIVE:
            return f"Protective mode: {self.protective_limit}% monthly drawdown limit (approaching €1M milestone)"
        elif stance == DrawdownStance.BREACHED:
            return "ALERT: Drawdown limit breached - protective actions activated"
        else:
            return "Unknown protection stance"
