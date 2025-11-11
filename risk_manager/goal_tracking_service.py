"""
Goal Tracking Service

Tracks financial goals on a daily basis, recording progress and sending alerts
when goals are achieved, at risk, or behind schedule.

Features:
- Daily goal progress snapshots
- Alert system for goal status changes
- Portfolio value tracking
- Monthly return calculations
- Monthly income tracking
"""

import asyncio
from datetime import datetime, date, time, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional
import structlog

from database import RiskPostgresDatabase

logger = structlog.get_logger(__name__)


class GoalTrackingService:
    """
    Service for tracking financial goals and recording daily progress
    
    Monitors:
    - Monthly return targets
    - Monthly income targets  
    - Portfolio value milestones
    
    Runs daily at end-of-day to snapshot progress
    """
    
    def __init__(self, database: RiskPostgresDatabase):
        """
        Initialize goal tracking service
        
        Args:
            database: Database instance for storing goal progress
        """
        self.database = database
        self.running = False
        self.scheduler_task: Optional[asyncio.Task] = None
        
        # Goal targets (configurable)
        self.monthly_return_target = 5.0  # 5% monthly return
        self.monthly_income_target = 2000.0  # $2000 monthly income
        self.portfolio_value_target = 50000.0  # $50k portfolio milestone
        
        # Tracking state
        self.last_snapshot_date: Optional[date] = None
        self.portfolio_value_start_of_month: Optional[float] = None
        self.income_month_to_date: float = 0.0
        
        logger.info("Goal tracking service initialized",
                    monthly_return_target=f"{self.monthly_return_target}%",
                    monthly_income_target=f"${self.monthly_income_target}",
                    portfolio_value_target=f"${self.portfolio_value_target}")
    
    async def start(self):
        """Start the goal tracking service"""
        if self.running:
            logger.warning("Goal tracking service already running")
            return
        
        self.running = True
        logger.info("Starting goal tracking service")
        
        # Initialize tracking state
        await self._initialize_tracking_state()
        
        # Start daily scheduler
        self.scheduler_task = asyncio.create_task(self._daily_scheduler())
        
        logger.info("Goal tracking service started")
    
    async def stop(self):
        """Stop the goal tracking service"""
        if not self.running:
            return
        
        self.running = False
        logger.info("Stopping goal tracking service")
        
        # Cancel scheduler task
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Goal tracking service stopped")
    
    async def _initialize_tracking_state(self):
        """Initialize tracking state from database"""
        try:
            # Get current portfolio value
            portfolio_value = await self._get_current_portfolio_value()
            
            # Check if we need to reset for new month
            today = date.today()
            if today.day == 1 or self.portfolio_value_start_of_month is None:
                self.portfolio_value_start_of_month = portfolio_value
                self.income_month_to_date = 0.0
                logger.info("Reset monthly tracking", 
                           month=today.strftime("%B %Y"),
                           starting_portfolio_value=portfolio_value)
            
            # Get last snapshot date
            self.last_snapshot_date = today - timedelta(days=1)
            
            logger.info("Tracking state initialized",
                       portfolio_value=portfolio_value,
                       portfolio_value_start_of_month=self.portfolio_value_start_of_month,
                       income_month_to_date=self.income_month_to_date)
        
        except Exception as e:
            logger.error("Error initializing tracking state", error=str(e))
    
    async def _daily_scheduler(self):
        """
        Daily scheduler that runs goal tracking at end of trading day
        
        Runs at 11:59 PM UTC every day
        """
        try:
            while self.running:
                # Calculate seconds until next run (11:59 PM UTC)
                now = datetime.now(timezone.utc)
                target_time = datetime.combine(
                    now.date(),
                    time(23, 59, 0),
                    tzinfo=timezone.utc
                )
                
                # If we've passed today's target, schedule for tomorrow
                if now >= target_time:
                    target_time += timedelta(days=1)
                
                sleep_seconds = (target_time - now).total_seconds()
                
                logger.info("Goal tracking scheduled",
                           next_run=target_time.isoformat(),
                           sleep_seconds=sleep_seconds)
                
                await asyncio.sleep(sleep_seconds)
                
                # Run daily goal tracking
                if self.running:
                    await self._run_daily_tracking()
        
        except asyncio.CancelledError:
            logger.info("Goal tracking scheduler cancelled")
            raise
        except Exception as e:
            logger.error("Error in goal tracking scheduler", error=str(e))
    
    async def _run_daily_tracking(self):
        """Run daily goal tracking (called at EOD)"""
        try:
            today = date.today()
            
            # Skip if already ran today
            if self.last_snapshot_date == today:
                logger.info("Goal tracking already ran today", date=today.isoformat())
                return
            
            logger.info("Running daily goal tracking", date=today.isoformat())
            
            # Get current portfolio value
            portfolio_value = await self._get_current_portfolio_value()
            
            # Track monthly return goal
            await self._track_monthly_return_goal(portfolio_value)
            
            # Track monthly income goal
            await self._track_monthly_income_goal()
            
            # Track portfolio value milestone
            await self._track_portfolio_value_goal(portfolio_value)
            
            # Update last snapshot date
            self.last_snapshot_date = today
            
            # Check if new month starts tomorrow
            tomorrow = today + timedelta(days=1)
            if tomorrow.day == 1:
                self.portfolio_value_start_of_month = portfolio_value
                self.income_month_to_date = 0.0
                logger.info("Resetting monthly tracking for new month",
                           new_month=tomorrow.strftime("%B %Y"),
                           starting_portfolio_value=portfolio_value)
            
            logger.info("Daily goal tracking completed successfully")
        
        except Exception as e:
            logger.error("Error in daily goal tracking", error=str(e))
    
    async def _track_monthly_return_goal(self, current_portfolio_value: float):
        """
        Track monthly return goal
        
        Args:
            current_portfolio_value: Current portfolio value
        """
        try:
            if self.portfolio_value_start_of_month is None or self.portfolio_value_start_of_month == 0:
                logger.warning("Cannot calculate monthly return: start of month value not set")
                return
            
            # Calculate actual monthly return (%)
            monthly_return = (
                (current_portfolio_value - self.portfolio_value_start_of_month) 
                / self.portfolio_value_start_of_month 
                * 100
            )
            
            # Update goal progress
            await self.database.update_goal_progress_snapshot(
                goal_type="monthly_return",
                target_value=self.monthly_return_target,
                actual_value=monthly_return
            )
            
            # Send alert if goal achieved
            if monthly_return >= self.monthly_return_target:
                await self._send_goal_alert(
                    goal_type="monthly_return",
                    status="achieved",
                    actual_value=monthly_return,
                    target_value=self.monthly_return_target,
                    message=f"Monthly return goal achieved: {monthly_return:.2f}% (target: {self.monthly_return_target}%)"
                )
            elif monthly_return < self.monthly_return_target * 0.7:  # Behind (< 70%)
                await self._send_goal_alert(
                    goal_type="monthly_return",
                    status="behind",
                    actual_value=monthly_return,
                    target_value=self.monthly_return_target,
                    message=f"Monthly return behind target: {monthly_return:.2f}% (target: {self.monthly_return_target}%)"
                )
            
            logger.info("Monthly return tracked",
                       actual=f"{monthly_return:.2f}%",
                       target=f"{self.monthly_return_target}%",
                       progress=f"{(monthly_return / self.monthly_return_target * 100):.1f}%")
        
        except Exception as e:
            logger.error("Error tracking monthly return goal", error=str(e))
    
    async def _track_monthly_income_goal(self):
        """Track monthly income goal (realized profits)"""
        try:
            # Get realized profits for current month
            # This would query closed positions with realized PnL
            # For now, use tracked income
            actual_income = self.income_month_to_date
            
            # Update goal progress
            await self.database.update_goal_progress_snapshot(
                goal_type="monthly_income",
                target_value=self.monthly_income_target,
                actual_value=actual_income
            )
            
            # Send alert if goal achieved
            if actual_income >= self.monthly_income_target:
                await self._send_goal_alert(
                    goal_type="monthly_income",
                    status="achieved",
                    actual_value=actual_income,
                    target_value=self.monthly_income_target,
                    message=f"Monthly income goal achieved: ${actual_income:.2f} (target: ${self.monthly_income_target})"
                )
            elif actual_income < self.monthly_income_target * 0.7:  # Behind (< 70%)
                await self._send_goal_alert(
                    goal_type="monthly_income",
                    status="behind",
                    actual_value=actual_income,
                    target_value=self.monthly_income_target,
                    message=f"Monthly income behind target: ${actual_income:.2f} (target: ${self.monthly_income_target})"
                )
            
            logger.info("Monthly income tracked",
                       actual=f"${actual_income:.2f}",
                       target=f"${self.monthly_income_target}",
                       progress=f"{(actual_income / self.monthly_income_target * 100):.1f}%")
        
        except Exception as e:
            logger.error("Error tracking monthly income goal", error=str(e))
    
    async def _track_portfolio_value_goal(self, current_portfolio_value: float):
        """
        Track portfolio value milestone goal
        
        Args:
            current_portfolio_value: Current portfolio value
        """
        try:
            # Update goal progress
            await self.database.update_goal_progress_snapshot(
                goal_type="portfolio_value",
                target_value=self.portfolio_value_target,
                actual_value=current_portfolio_value
            )
            
            # Send alert if milestone achieved
            if current_portfolio_value >= self.portfolio_value_target:
                await self._send_goal_alert(
                    goal_type="portfolio_value",
                    status="achieved",
                    actual_value=current_portfolio_value,
                    target_value=self.portfolio_value_target,
                    message=f"Portfolio value milestone achieved: ${current_portfolio_value:.2f} (target: ${self.portfolio_value_target})"
                )
            elif current_portfolio_value < self.portfolio_value_target * 0.85:  # At risk (< 85%)
                await self._send_goal_alert(
                    goal_type="portfolio_value",
                    status="at_risk",
                    actual_value=current_portfolio_value,
                    target_value=self.portfolio_value_target,
                    message=f"Portfolio value at risk: ${current_portfolio_value:.2f} (target: ${self.portfolio_value_target})"
                )
            
            logger.info("Portfolio value tracked",
                       actual=f"${current_portfolio_value:.2f}",
                       target=f"${self.portfolio_value_target}",
                       progress=f"{(current_portfolio_value / self.portfolio_value_target * 100):.1f}%")
        
        except Exception as e:
            logger.error("Error tracking portfolio value goal", error=str(e))
    
    async def _get_current_portfolio_value(self) -> float:
        """
        Get current portfolio value from database
        
        Returns:
            Current portfolio value in USD
        """
        try:
            # Query all open positions
            query = """
                SELECT 
                    COALESCE(SUM(quantity * entry_price), 0) as total_value
                FROM positions
                WHERE status = 'open'
            """
            
            result = await self.database._postgres.fetchrow(query)
            portfolio_value = float(result['total_value']) if result else 0.0
            
            # Add cash balance (if tracked)
            # For now, assume portfolio value is just position values
            
            return portfolio_value
        
        except Exception as e:
            logger.error("Error getting portfolio value", error=str(e))
            return 0.0
    
    async def _send_goal_alert(
        self,
        goal_type: str,
        status: str,
        actual_value: float,
        target_value: float,
        message: str
    ):
        """
        Send alert for goal status change
        
        Args:
            goal_type: Type of goal
            status: Goal status (achieved, at_risk, behind)
            actual_value: Actual value
            target_value: Target value
            message: Alert message
        """
        try:
            # Log the alert
            logger.info("Goal alert",
                       goal_type=goal_type,
                       status=status,
                       actual_value=actual_value,
                       target_value=target_value,
                       message=message)
            
            # In production, this would:
            # - Send email notification
            # - Send Telegram/Slack message
            # - Create system notification
            # - Store in alerts table
            
            # For now, just log
            
        except Exception as e:
            logger.error("Error sending goal alert", error=str(e))
    
    async def record_realized_profit(self, profit: float):
        """
        Record realized profit for monthly income tracking
        
        Args:
            profit: Realized profit amount (positive or negative)
        """
        self.income_month_to_date += profit
        logger.info("Recorded realized profit",
                   profit=profit,
                   month_to_date=self.income_month_to_date)
    
    async def update_goal_targets(
        self,
        monthly_return_target: Optional[float] = None,
        monthly_income_target: Optional[float] = None,
        portfolio_value_target: Optional[float] = None
    ):
        """
        Update goal targets
        
        Args:
            monthly_return_target: New monthly return target (%)
            monthly_income_target: New monthly income target ($)
            portfolio_value_target: New portfolio value target ($)
        """
        if monthly_return_target is not None:
            self.monthly_return_target = monthly_return_target
            logger.info("Updated monthly return target", target=f"{monthly_return_target}%")
        
        if monthly_income_target is not None:
            self.monthly_income_target = monthly_income_target
            logger.info("Updated monthly income target", target=f"${monthly_income_target}")
        
        if portfolio_value_target is not None:
            self.portfolio_value_target = portfolio_value_target
            logger.info("Updated portfolio value target", target=f"${portfolio_value_target}")
    
    async def manual_snapshot(self):
        """Manually trigger a goal tracking snapshot (for testing/debugging)"""
        logger.info("Manual goal tracking snapshot triggered")
        await self._run_daily_tracking()
