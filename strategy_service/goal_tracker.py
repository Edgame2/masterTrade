"""
Goal Tracking Service

Monitors progress towards financial goals and automatically adjusts
trading parameters to maximize goal achievement probability.

Goals:
- 10% monthly return
- $10K monthly profit
- $1M portfolio target
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional
import uuid

import structlog
from database import Database

logger = structlog.get_logger(__name__)


class GoalTracker:
    """
    Monitors and tracks progress towards financial goals.
    Automatically adjusts risk parameters and position sizing to optimize goal achievement.
    """
    
    def __init__(self, database: Database):
        self.db = database
        self.tracking_interval_minutes = 60  # Update progress hourly
        self.adjustment_cooldown_hours = 24  # Wait 24h between adjustments
        
    async def start_tracking(self):
        """Start continuous goal tracking loop."""
        logger.info("Goal tracking service started")
        
        while True:
            try:
                await self.update_all_goals()
                await asyncio.sleep(self.tracking_interval_minutes * 60)
            except Exception as e:
                logger.error("Error in goal tracking loop", error=str(e))
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def update_all_goals(self):
        """Update progress for all active goals."""
        goals = await self._get_active_goals()
        
        for goal in goals:
            try:
                await self.update_goal_progress(goal["id"])
            except Exception as e:
                logger.error("Error updating goal", goal_id=goal["id"], error=str(e))
    
    async def update_goal_progress(self, goal_id: str):
        """Update progress tracking for a specific goal."""
        goal = await self._get_goal(goal_id)
        if not goal:
            logger.warning("Goal not found", goal_id=goal_id)
            return
        
        # Get current portfolio value
        portfolio_value = await self._get_portfolio_value()
        
        # Calculate current value based on goal type
        if goal["goal_type"] == "monthly_return_pct":
            current_value = await self._calculate_monthly_return(portfolio_value)
        elif goal["goal_type"] == "monthly_profit_usd":
            current_value = await self._calculate_monthly_profit()
        else:  # portfolio_target_usd
            current_value = portfolio_value
        
        # Calculate progress metrics
        target_value = Decimal(str(goal["target_value"]))
        progress_pct = (current_value / target_value * Decimal("100")) if target_value > 0 else Decimal("0")
        
        # Calculate time progress
        now = datetime.now(timezone.utc)
        start_date = goal["start_date"]
        target_date = goal.get("target_date")
        
        if target_date:
            total_duration = (target_date - start_date).total_seconds()
            elapsed = (now - start_date).total_seconds()
            time_progress_pct = (elapsed / total_duration * 100) if total_duration > 0 else 0
            days_remaining = (target_date - now).days
        else:
            # Monthly goal - calculate within current month
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            total_duration = (month_end - month_start).total_seconds()
            elapsed = (now - month_start).total_seconds()
            time_progress_pct = (elapsed / total_duration * 100)
            days_remaining = (month_end - now).days
        
        # Check if on track
        on_track = progress_pct >= time_progress_pct
        
        # Calculate required daily return
        remaining_value = target_value - current_value
        required_daily_return = (remaining_value / portfolio_value / Decimal(str(max(days_remaining, 1)))) if portfolio_value > 0 else Decimal("0")
        
        # Get performance metrics
        realized_pnl, unrealized_pnl = await self._get_pnl()
        active_positions = await self._get_active_positions_count()
        win_rate = await self._calculate_win_rate()
        sharpe_ratio = await self._calculate_sharpe_ratio()
        
        # Save progress snapshot
        await self._save_progress_snapshot(
            goal_id=goal_id,
            current_value=current_value,
            progress_pct=progress_pct,
            portfolio_value=portfolio_value,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            active_positions=active_positions,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            days_remaining=days_remaining,
            required_daily_return=required_daily_return,
            on_track=on_track
        )
        
        # Update goal current value
        await self._update_goal_current_value(goal_id, current_value)
        
        # Check if adjustment needed
        if not on_track:
            await self._consider_adjustment(goal, progress_pct, time_progress_pct)
        
        # Check for milestone achievements
        await self._check_milestones(goal_id, current_value)
        
        # Check if goal achieved
        if current_value >= target_value:
            await self._mark_goal_achieved(goal_id)
        
        logger.info(
            "Goal progress updated",
            goal_id=goal_id,
            goal_type=goal["goal_type"],
            current_value=float(current_value),
            target_value=float(target_value),
            progress_pct=float(progress_pct),
            on_track=on_track
        )
    
    async def _get_active_goals(self) -> List[Dict]:
        """Get all active goals."""
        query = "SELECT * FROM financial_goals WHERE status = 'active' ORDER BY priority"
        records = await self.db._postgres.fetch(query)
        return [dict(r) for r in records]
    
    async def _get_goal(self, goal_id: str) -> Optional[Dict]:
        """Get a specific goal."""
        query = "SELECT * FROM financial_goals WHERE id = $1"
        record = await self.db._postgres.fetchrow(query, uuid.UUID(goal_id))
        return dict(record) if record else None
    
    async def _get_portfolio_value(self) -> Decimal:
        """Get current total portfolio value."""
        query = """
            SELECT COALESCE(SUM(total_value), 0) as total
            FROM portfolio_balances
        """
        result = await self.db._postgres.fetchval(query)
        
        total = Decimal(str(result or 0))
        if total <= 0:
            total = Decimal("10000")  # Default starting capital
        
        return total
    
    async def _calculate_monthly_return(self, current_portfolio_value: Decimal) -> Decimal:
        """Calculate return % for current month."""
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Get portfolio value at start of month
        query = """
            SELECT COALESCE(SUM(total_value), $1) as value
            FROM portfolio_balances
            WHERE updated_at <= $2
            ORDER BY updated_at DESC
            LIMIT 1
        """
        start_value = await self.db._postgres.fetchval(query, float(current_portfolio_value), month_start)
        start_value = Decimal(str(start_value or current_portfolio_value))
        
        if start_value <= 0:
            return Decimal("0")
        
        monthly_return = (current_portfolio_value - start_value) / start_value
        return monthly_return
    
    async def _calculate_monthly_profit(self) -> Decimal:
        """Calculate total profit $ for current month."""
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        query = """
            SELECT COALESCE(SUM(pnl), 0) as profit
            FROM trades
            WHERE executed_at >= $1 AND status = 'filled'
        """
        profit = await self.db._postgres.fetchval(query, month_start)
        return Decimal(str(profit or 0))
    
    async def _get_pnl(self) -> tuple[Decimal, Decimal]:
        """Get realized and unrealized P&L."""
        # Realized P&L (closed trades)
        realized_query = """
            SELECT COALESCE(SUM(pnl), 0) as realized
            FROM trades
            WHERE status = 'filled'
        """
        realized = await self.db._postgres.fetchval(realized_query)
        
        # Unrealized P&L (open positions)
        # TODO: Calculate based on current prices vs entry prices
        unrealized = Decimal("0")  # Placeholder
        
        return Decimal(str(realized or 0)), unrealized
    
    async def _get_active_positions_count(self) -> int:
        """Get number of active positions."""
        query = """
            SELECT COUNT(*) 
            FROM orders 
            WHERE status IN ('open', 'partially_filled')
        """
        count = await self.db._postgres.fetchval(query)
        return int(count or 0)
    
    async def _calculate_win_rate(self, period_days: int = 30) -> Decimal:
        """Calculate win rate over period."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        
        query = """
            SELECT 
                COUNT(*) FILTER (WHERE pnl > 0) as wins,
                COUNT(*) as total
            FROM trades
            WHERE executed_at >= $1 AND status = 'filled'
        """
        result = await self.db._postgres.fetchrow(query, cutoff)
        
        if result and result["total"] > 0:
            return Decimal(str(result["wins"])) / Decimal(str(result["total"]))
        return Decimal("0.5")
    
    async def _calculate_sharpe_ratio(self, period_days: int = 30) -> Decimal:
        """Calculate Sharpe ratio."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        
        query = """
            SELECT 
                AVG(pnl) as mean_return,
                STDDEV(pnl) as std_dev
            FROM trades
            WHERE executed_at >= $1 AND status = 'filled'
        """
        result = await self.db._postgres.fetchrow(query, cutoff)
        
        if result and result["std_dev"] and float(result["std_dev"]) > 0:
            mean = Decimal(str(result["mean_return"] or 0))
            std = Decimal(str(result["std_dev"]))
            sharpe = (mean / std) * Decimal("252").sqrt() if std > 0 else Decimal("0")
            return sharpe
        return Decimal("0")
    
    async def _save_progress_snapshot(
        self,
        goal_id: str,
        current_value: Decimal,
        progress_pct: Decimal,
        portfolio_value: Decimal,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal,
        active_positions: int,
        win_rate: Decimal,
        sharpe_ratio: Decimal,
        days_remaining: int,
        required_daily_return: Decimal,
        on_track: bool
    ):
        """Save progress snapshot to database."""
        query = """
            INSERT INTO goal_progress (
                goal_id, current_value, progress_pct, portfolio_value,
                realized_pnl, unrealized_pnl, active_positions, win_rate,
                sharpe_ratio, days_remaining, required_daily_return, on_track
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """
        await self.db._postgres.execute(
            query,
            uuid.UUID(goal_id),
            float(current_value),
            float(progress_pct),
            float(portfolio_value),
            float(realized_pnl),
            float(unrealized_pnl),
            active_positions,
            float(win_rate),
            float(sharpe_ratio),
            days_remaining,
            float(required_daily_return),
            on_track
        )
    
    async def _update_goal_current_value(self, goal_id: str, current_value: Decimal):
        """Update goal's current value."""
        query = """
            UPDATE financial_goals 
            SET current_value = $2, updated_at = NOW()
            WHERE id = $1
        """
        await self.db._postgres.execute(query, uuid.UUID(goal_id), float(current_value))
    
    async def _consider_adjustment(self, goal: Dict, progress_pct: Decimal, time_progress_pct: Decimal):
        """Consider making an adjustment to improve goal achievement."""
        gap = time_progress_pct - progress_pct
        
        # Check if recent adjustment exists
        recent_adjustment = await self._get_recent_adjustment(goal["id"])
        if recent_adjustment:
            hours_since = (datetime.now(timezone.utc) - recent_adjustment["applied_at"]).total_seconds() / 3600
            if hours_since < self.adjustment_cooldown_hours:
                return  # Too soon for another adjustment
        
        # Determine adjustment type based on gap
        if gap > 20:  # Significantly behind
            adjustment_type = "risk_increase"
            new_risk = min(float(goal["risk_tolerance"]) * 1.5, 0.05)  # Increase risk by 50%, max 5%
            reason = f"Behind schedule by {float(gap):.1f}%. Increasing risk tolerance to catch up."
        elif gap > 10:  # Moderately behind
            adjustment_type = "position_size_up"
            new_risk = min(float(goal["risk_tolerance"]) * 1.25, 0.04)  # Increase by 25%, max 4%
            reason = f"Behind schedule by {float(gap):.1f}%. Increasing position sizes."
        else:
            return  # No adjustment needed for small gaps
        
        # Apply adjustment
        await self._apply_adjustment(
            goal_id=goal["id"],
            adjustment_type=adjustment_type,
            previous_value=float(goal["risk_tolerance"]),
            new_value=new_risk,
            reason=reason
        )
        
        logger.info(
            "Adjustment applied",
            goal_id=goal["id"],
            adjustment_type=adjustment_type,
            gap=float(gap)
        )
    
    async def _get_recent_adjustment(self, goal_id: str) -> Optional[Dict]:
        """Get most recent adjustment for goal."""
        query = """
            SELECT * FROM goal_adjustments
            WHERE goal_id = $1 AND status = 'active'
            ORDER BY applied_at DESC
            LIMIT 1
        """
        record = await self.db._postgres.fetchrow(query, uuid.UUID(goal_id))
        return dict(record) if record else None
    
    async def _apply_adjustment(
        self,
        goal_id: str,
        adjustment_type: str,
        previous_value: float,
        new_value: float,
        reason: str
    ):
        """Apply an adjustment to goal parameters."""
        # Save adjustment record
        query = """
            INSERT INTO goal_adjustments (
                goal_id, adjustment_type, reason, previous_value, new_value
            )
            VALUES ($1, $2, $3, $4, $5)
        """
        await self.db._postgres.execute(
            query,
            uuid.UUID(goal_id),
            adjustment_type,
            reason,
            previous_value,
            new_value
        )
        
        # Update goal risk tolerance
        update_query = """
            UPDATE financial_goals
            SET risk_tolerance = $2, updated_at = NOW()
            WHERE id = $1
        """
        await self.db._postgres.execute(update_query, uuid.UUID(goal_id), new_value)
    
    async def _check_milestones(self, goal_id: str, current_value: Decimal):
        """Check if any milestones have been achieved."""
        query = """
            SELECT * FROM goal_milestones
            WHERE goal_id = $1 AND achieved = FALSE AND milestone_value <= $2
        """
        milestones = await self.db._postgres.fetch(query, uuid.UUID(goal_id), float(current_value))
        
        for milestone in milestones:
            # Mark milestone as achieved
            update_query = """
                UPDATE goal_milestones
                SET achieved = TRUE, achieved_at = NOW()
                WHERE id = $1
            """
            await self.db._postgres.execute(update_query, milestone["id"])
            
            logger.info(
                "Milestone achieved",
                goal_id=goal_id,
                milestone=milestone["milestone_name"],
                value=float(current_value)
            )
            
            # Execute reward action if specified
            if milestone["reward_action"]:
                await self._execute_milestone_reward(goal_id, milestone["reward_action"])
    
    async def _execute_milestone_reward(self, goal_id: str, reward_action: str):
        """Execute reward action for milestone achievement."""
        # TODO: Implement reward actions (e.g., increase_allocation, bonus_trade)
        logger.info("Milestone reward executed", goal_id=goal_id, action=reward_action)
    
    async def _mark_goal_achieved(self, goal_id: str):
        """Mark a goal as achieved."""
        query = """
            UPDATE financial_goals
            SET status = 'achieved', achieved_at = NOW(), updated_at = NOW()
            WHERE id = $1
        """
        await self.db._postgres.execute(query, uuid.UUID(goal_id))
        
        logger.info("Goal achieved!", goal_id=goal_id)
    
    async def get_goal_summary(self, goal_id: Optional[str] = None) -> Dict:
        """Get summary of goal progress."""
        if goal_id:
            query = "SELECT * FROM v_current_goal_status WHERE id = $1"
            record = await self.db._postgres.fetchrow(query, uuid.UUID(goal_id))
            records = [record] if record else []
        else:
            query = "SELECT * FROM v_current_goal_status"
            records = await self.db._postgres.fetch(query)
        
        goals = []
        for record in records:
            goals.append({
                "id": str(record["id"]),
                "goal_type": record["goal_type"],
                "target_value": float(record["target_value"]),
                "current_value": float(record["current_value"]),
                "progress_pct": float(record["progress_pct"]),
                "status": record["status"],
                "priority": record["priority"],
                "on_track": record["on_track"],
                "required_daily_return": float(record["required_daily_return"]),
                "days_remaining": record["days_remaining"],
                "portfolio_value": float(record["latest_portfolio_value"]),
                "win_rate": float(record["latest_win_rate"]),
                "sharpe_ratio": float(record["latest_sharpe_ratio"])
            })
        
        return {
            "goals": goals,
            "total_active": len(goals),
            "on_track_count": sum(1 for g in goals if g["on_track"]),
            "behind_count": sum(1 for g in goals if not g["on_track"])
        }


async def main():
    """Test goal tracker."""
    from database import Database
    
    db = Database()
    await db.connect()
    
    try:
        tracker = GoalTracker(db)
        
        # Update all goals once
        await tracker.update_all_goals()
        
        # Get summary
        summary = await tracker.get_goal_summary()
        
        print("\n=== Goal Tracking Summary ===")
        print(f"Total Active Goals: {summary['total_active']}")
        print(f"On Track: {summary['on_track_count']}")
        print(f"Behind Schedule: {summary['behind_count']}")
        print("\nGoals:")
        for goal in summary["goals"]:
            print(f"\n- {goal['goal_type']}: {goal['progress_pct']:.1f}% complete")
            print(f"  Target: {goal['target_value']:.2f}, Current: {goal['current_value']:.2f}")
            print(f"  Status: {'✓ On track' if goal['on_track'] else '✗ Behind schedule'}")
            print(f"  Required daily return: {goal['required_daily_return']*100:.2f}%")
        
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
