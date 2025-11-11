"""
Goal-Based Strategy Selector

Adjusts strategy selection and activation based on financial goal progress.
Integrates with risk_manager's goal tracking system to make intelligent
strategy selection decisions.

Strategy Selection Logic:
- Behind on goals (<70% progress): Prefer aggressive, high-return strategies
- At risk (70-85% progress): Balance between growth and safety
- On track (85-100% progress): Maintain current approach
- Ahead (>100% progress): Prioritize capital preservation, reduce risk

This module queries goal status from the risk_manager service and adjusts
strategy scores accordingly before activation decisions.
"""

import asyncio
import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class GoalProgress:
    """Container for goal progress information"""
    goal_type: str
    target_value: float
    current_value: float
    progress_percent: float
    status: str  # achieved, on_track, at_risk, behind


@dataclass
class StrategyAdjustment:
    """Adjustment factors for strategy selection"""
    aggressiveness_multiplier: float  # 0.5 to 1.5
    risk_tolerance_adjustment: float  # -0.2 to +0.2
    min_sharpe_adjustment: float  # -0.5 to +0.5
    prefer_volatility: bool  # Prefer high or low volatility strategies
    

class GoalBasedStrategySelector:
    """
    Goal-based strategy selector that adjusts strategy preferences
    based on financial goal progress
    """
    
    def __init__(
        self,
        risk_manager_url: str = "http://risk_manager:8003",
        update_interval_seconds: int = 3600  # Update every hour
    ):
        """
        Initialize goal-based selector
        
        Args:
            risk_manager_url: URL of risk manager service
            update_interval_seconds: How often to refresh goal status
        """
        self.risk_manager_url = risk_manager_url
        self.update_interval = update_interval_seconds
        
        # Cached goal progress
        self.goal_progress: Dict[str, GoalProgress] = {}
        self.last_update: Optional[datetime] = None
        
        # Strategy adjustment factors
        self.current_adjustment: Optional[StrategyAdjustment] = None
        
        logger.info(
            "Goal-based strategy selector initialized",
            risk_manager_url=risk_manager_url,
            update_interval=update_interval_seconds
        )
    
    async def get_goal_progress(self) -> Dict[str, GoalProgress]:
        """
        Fetch current goal progress from risk manager
        
        Returns:
            Dictionary mapping goal_type to GoalProgress
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.risk_manager_url}/goals/status"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error(
                            "Failed to fetch goal status",
                            status=response.status,
                            url=url
                        )
                        return self.goal_progress  # Return cached
                    
                    data = await response.json()
                    
                    if not data.get("success"):
                        logger.warning("Goal status request unsuccessful")
                        return self.goal_progress
                    
                    # Parse goal progress
                    new_progress = {}
                    for goal in data.get("goals", []):
                        goal_progress = GoalProgress(
                            goal_type=goal["goal_type"],
                            target_value=goal["target_value"],
                            current_value=goal["current_value"],
                            progress_percent=goal["progress_percent"],
                            status=goal["status"]
                        )
                        new_progress[goal["goal_type"]] = goal_progress
                    
                    self.goal_progress = new_progress
                    self.last_update = datetime.now(timezone.utc)
                    
                    logger.info(
                        "Goal progress updated",
                        goals_count=len(new_progress),
                        timestamp=self.last_update.isoformat()
                    )
                    
                    return new_progress
        
        except asyncio.TimeoutError:
            logger.error("Timeout fetching goal status from risk manager")
            return self.goal_progress
        
        except Exception as e:
            logger.error(f"Error fetching goal progress: {e}")
            return self.goal_progress
    
    async def should_update_goals(self) -> bool:
        """Check if goal progress needs updating"""
        if not self.last_update:
            return True
        
        time_since_update = (datetime.now(timezone.utc) - self.last_update).total_seconds()
        return time_since_update >= self.update_interval
    
    async def calculate_strategy_adjustment(self) -> StrategyAdjustment:
        """
        Calculate strategy adjustment factors based on goal progress
        
        Returns:
            StrategyAdjustment with multipliers and preferences
        """
        try:
            # Update goals if needed
            if await self.should_update_goals():
                await self.get_goal_progress()
            
            if not self.goal_progress:
                # Default: neutral adjustment
                return StrategyAdjustment(
                    aggressiveness_multiplier=1.0,
                    risk_tolerance_adjustment=0.0,
                    min_sharpe_adjustment=0.0,
                    prefer_volatility=False
                )
            
            # Calculate average progress across all goals
            total_progress = sum(g.progress_percent for g in self.goal_progress.values())
            avg_progress = total_progress / len(self.goal_progress)
            
            # Count goals by status
            behind_count = sum(1 for g in self.goal_progress.values() if g.status == "behind")
            at_risk_count = sum(1 for g in self.goal_progress.values() if g.status == "at_risk")
            on_track_count = sum(1 for g in self.goal_progress.values() if g.status == "on_track")
            achieved_count = sum(1 for g in self.goal_progress.values() if g.status == "achieved")
            
            # Decision logic based on goal progress
            if behind_count >= 2 or avg_progress < 70:
                # Multiple goals behind or severely behind: Be aggressive
                adjustment = StrategyAdjustment(
                    aggressiveness_multiplier=1.3,  # 30% more aggressive
                    risk_tolerance_adjustment=0.15,  # Allow more risk
                    min_sharpe_adjustment=-0.3,  # Accept lower Sharpe
                    prefer_volatility=True  # Prefer high volatility for catch-up
                )
                logger.info(
                    "AGGRESSIVE strategy adjustment",
                    behind_count=behind_count,
                    avg_progress=f"{avg_progress:.1f}%"
                )
            
            elif behind_count == 1 or at_risk_count >= 2 or 70 <= avg_progress < 85:
                # Some goals at risk: Moderately aggressive
                adjustment = StrategyAdjustment(
                    aggressiveness_multiplier=1.15,  # 15% more aggressive
                    risk_tolerance_adjustment=0.08,  # Slightly more risk
                    min_sharpe_adjustment=-0.15,  # Slightly lower Sharpe OK
                    prefer_volatility=True
                )
                logger.info(
                    "MODERATE AGGRESSIVE strategy adjustment",
                    behind_count=behind_count,
                    at_risk_count=at_risk_count,
                    avg_progress=f"{avg_progress:.1f}%"
                )
            
            elif achieved_count >= 2 or avg_progress >= 110:
                # Multiple goals achieved or well ahead: Protect capital
                adjustment = StrategyAdjustment(
                    aggressiveness_multiplier=0.7,  # 30% less aggressive
                    risk_tolerance_adjustment=-0.15,  # Reduce risk
                    min_sharpe_adjustment=0.3,  # Require higher Sharpe
                    prefer_volatility=False  # Prefer low volatility
                )
                logger.info(
                    "CONSERVATIVE strategy adjustment",
                    achieved_count=achieved_count,
                    avg_progress=f"{avg_progress:.1f}%"
                )
            
            elif achieved_count == 1 or avg_progress >= 100:
                # Some goals achieved: Slightly conservative
                adjustment = StrategyAdjustment(
                    aggressiveness_multiplier=0.85,  # 15% less aggressive
                    risk_tolerance_adjustment=-0.08,  # Slightly less risk
                    min_sharpe_adjustment=0.15,  # Slightly higher Sharpe
                    prefer_volatility=False
                )
                logger.info(
                    "SLIGHT CONSERVATIVE strategy adjustment",
                    achieved_count=achieved_count,
                    avg_progress=f"{avg_progress:.1f}%"
                )
            
            else:
                # On track: Neutral/balanced approach
                adjustment = StrategyAdjustment(
                    aggressiveness_multiplier=1.0,
                    risk_tolerance_adjustment=0.0,
                    min_sharpe_adjustment=0.0,
                    prefer_volatility=False
                )
                logger.info(
                    "NEUTRAL strategy adjustment",
                    on_track_count=on_track_count,
                    avg_progress=f"{avg_progress:.1f}%"
                )
            
            self.current_adjustment = adjustment
            return adjustment
        
        except Exception as e:
            logger.error(f"Error calculating strategy adjustment: {e}")
            # Return neutral adjustment on error
            return StrategyAdjustment(
                aggressiveness_multiplier=1.0,
                risk_tolerance_adjustment=0.0,
                min_sharpe_adjustment=0.0,
                prefer_volatility=False
            )
    
    async def adjust_strategy_score(
        self,
        strategy_id: str,
        base_score: float,
        strategy_metrics: Dict
    ) -> float:
        """
        Adjust a strategy's score based on goal progress
        
        Args:
            strategy_id: Strategy identifier
            base_score: Original strategy score
            strategy_metrics: Strategy performance metrics
        
        Returns:
            Adjusted score
        """
        try:
            # Get current adjustment factors
            adjustment = await self.calculate_strategy_adjustment()
            
            # Extract strategy characteristics
            sharpe_ratio = strategy_metrics.get("sharpe_ratio", 1.0)
            volatility = strategy_metrics.get("volatility", 0.0)
            max_drawdown = abs(strategy_metrics.get("max_drawdown", 0.0))
            
            # Calculate adjustment multiplier
            score_multiplier = adjustment.aggressiveness_multiplier
            
            # Bonus/penalty for volatility preference
            if adjustment.prefer_volatility and volatility > 0.02:  # High volatility
                score_multiplier *= 1.1
            elif not adjustment.prefer_volatility and volatility < 0.015:  # Low volatility
                score_multiplier *= 1.1
            
            # Sharpe ratio adjustment
            sharpe_threshold = 0.5 + adjustment.min_sharpe_adjustment
            if sharpe_ratio < sharpe_threshold:
                # Penalize strategies below adjusted Sharpe threshold
                score_multiplier *= 0.85
            
            # Drawdown considerations
            if max_drawdown > 0.30 and not adjustment.prefer_volatility:
                # High drawdown not acceptable when being conservative
                score_multiplier *= 0.7
            
            adjusted_score = base_score * score_multiplier
            
            logger.debug(
                "Strategy score adjusted",
                strategy_id=strategy_id,
                base_score=base_score,
                adjusted_score=adjusted_score,
                multiplier=score_multiplier
            )
            
            return adjusted_score
        
        except Exception as e:
            logger.error(f"Error adjusting strategy score: {e}")
            return base_score  # Return unadjusted on error
    
    async def get_strategy_recommendations(
        self,
        strategies: List[Dict]
    ) -> List[Tuple[str, float, str]]:
        """
        Get strategy recommendations with goal-based adjustments
        
        Args:
            strategies: List of strategy dicts with id, score, and metrics
        
        Returns:
            List of (strategy_id, adjusted_score, reasoning) tuples
        """
        try:
            recommendations = []
            
            # Get current adjustment
            adjustment = await self.calculate_strategy_adjustment()
            
            for strategy in strategies:
                strategy_id = strategy.get("id", "unknown")
                base_score = strategy.get("score", 0.0)
                metrics = strategy.get("metrics", {})
                
                # Adjust score
                adjusted_score = await self.adjust_strategy_score(
                    strategy_id,
                    base_score,
                    metrics
                )
                
                # Generate reasoning
                if adjustment.aggressiveness_multiplier > 1.1:
                    reasoning = "Aggressive (goals behind)"
                elif adjustment.aggressiveness_multiplier < 0.9:
                    reasoning = "Conservative (goals ahead)"
                else:
                    reasoning = "Balanced (goals on track)"
                
                recommendations.append((strategy_id, adjusted_score, reasoning))
            
            # Sort by adjusted score
            recommendations.sort(key=lambda x: x[1], reverse=True)
            
            logger.info(
                "Strategy recommendations generated",
                total_strategies=len(recommendations),
                top_score=recommendations[0][1] if recommendations else 0
            )
            
            return recommendations
        
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return []
    
    def get_current_adjustment_summary(self) -> Dict:
        """Get summary of current adjustment factors"""
        if not self.current_adjustment:
            return {
                "status": "not_initialized",
                "message": "No adjustment calculated yet"
            }
        
        adj = self.current_adjustment
        
        # Determine overall stance
        if adj.aggressiveness_multiplier > 1.1:
            stance = "aggressive"
        elif adj.aggressiveness_multiplier < 0.9:
            stance = "conservative"
        else:
            stance = "balanced"
        
        return {
            "status": "active",
            "stance": stance,
            "aggressiveness_multiplier": adj.aggressiveness_multiplier,
            "risk_tolerance_adjustment": adj.risk_tolerance_adjustment,
            "min_sharpe_adjustment": adj.min_sharpe_adjustment,
            "prefer_volatility": adj.prefer_volatility,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "goal_progress": {
                goal_type: {
                    "progress": f"{progress.progress_percent:.1f}%",
                    "status": progress.status
                }
                for goal_type, progress in self.goal_progress.items()
            }
        }
