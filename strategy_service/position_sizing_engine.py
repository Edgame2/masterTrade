"""
Goal-Oriented Position Sizing Engine

Dynamically calculates position sizes based on financial goals:
- 10% monthly return target
- $10K monthly profit target  
- $1M portfolio target

Uses adaptive risk management, Kelly Criterion, and machine learning
to optimize position sizes for goal achievement.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import uuid

import structlog
from database import Database

logger = structlog.get_logger(__name__)


class GoalOrientedPositionSizer:
    """
    Adaptive position sizing engine that adjusts sizes based on:
    1. Goal progress (ahead/behind schedule)
    2. Current portfolio value
    3. Risk tolerance
    4. Win rate and Sharpe ratio
    5. Time remaining to achieve goal
    """
    
    def __init__(self, database: Database):
        self.db = database
        self.min_position_pct = Decimal("0.01")  # 1% minimum
        self.max_position_pct = Decimal("0.20")  # 20% maximum
        self.default_risk_pct = Decimal("0.02")  # 2% default risk per trade
        
    async def calculate_position_size(
        self,
        strategy_id: str,
        symbol: str,
        current_price: Decimal,
        stop_loss_pct: Decimal,
        confidence: Decimal,
        goal_id: Optional[str] = None
    ) -> Dict:
        """
        Calculate optimal position size for a trade based on goal progress.
        
        Args:
            strategy_id: Strategy generating the signal
            symbol: Trading pair (e.g., 'BTCUSDT')
            current_price: Current market price
            stop_loss_pct: Stop loss distance as % (e.g., 0.02 for 2%)
            confidence: Model confidence in signal (0-1)
            goal_id: Specific goal to optimize for (None = highest priority active goal)
            
        Returns:
            Dict with recommended position size, allocation %, risk amount, reasoning
        """
        try:
            # Get active goal to optimize for
            goal = await self._get_target_goal(goal_id)
            if not goal:
                logger.warning("No active goal found, using default sizing")
                return await self._default_position_size(current_price, stop_loss_pct)
            
            # Get current portfolio value
            portfolio_value = await self._get_portfolio_value()
            if portfolio_value <= 0:
                logger.error("Invalid portfolio value", value=portfolio_value)
                return await self._default_position_size(current_price, stop_loss_pct)
            
            # Calculate goal progress metrics
            progress = await self._calculate_goal_progress(goal, portfolio_value)
            
            # Adjust risk based on progress
            adjusted_risk_pct = self._adjust_risk_for_progress(
                base_risk=Decimal(str(goal["risk_tolerance"])),
                progress_pct=progress["progress_pct"],
                time_progress_pct=progress["time_progress_pct"],
                on_track=progress["on_track"]
            )
            
            # Apply Kelly Criterion for optimal sizing
            kelly_fraction = self._calculate_kelly_fraction(
                win_rate=progress["win_rate"],
                avg_win=progress["avg_win"],
                avg_loss=progress["avg_loss"]
            )
            
            # Confidence-adjusted Kelly
            adjusted_kelly = kelly_fraction * float(confidence) * 0.5  # Half-Kelly for safety
            
            # Calculate base position size from risk
            risk_amount = portfolio_value * adjusted_risk_pct
            position_value = risk_amount / stop_loss_pct
            
            # Apply Kelly adjustment
            position_value = position_value * Decimal(str(adjusted_kelly))
            
            # Calculate allocation percentage
            allocation_pct = position_value / portfolio_value
            
            # Apply min/max limits
            allocation_pct = max(self.min_position_pct, min(allocation_pct, self.max_position_pct))
            position_value = portfolio_value * allocation_pct
            
            # Calculate position size in base currency
            position_size = position_value / current_price
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                goal=goal,
                progress=progress,
                adjusted_risk_pct=adjusted_risk_pct,
                kelly_fraction=kelly_fraction,
                confidence=confidence,
                allocation_pct=allocation_pct
            )
            
            # Store recommendation
            recommendation = {
                "goal_id": goal["id"],
                "strategy_id": strategy_id,
                "symbol": symbol,
                "recommended_size": float(position_size),
                "recommended_allocation": float(allocation_pct),
                "risk_amount": float(risk_amount),
                "confidence_score": float(confidence),
                "reasoning": reasoning,
                "metadata": {
                    "current_price": float(current_price),
                    "stop_loss_pct": float(stop_loss_pct),
                    "portfolio_value": float(portfolio_value),
                    "adjusted_risk_pct": float(adjusted_risk_pct),
                    "kelly_fraction": kelly_fraction,
                    "goal_progress_pct": float(progress["progress_pct"]),
                    "on_track": progress["on_track"]
                }
            }
            
            await self._save_recommendation(recommendation)
            
            logger.info(
                "Position size calculated",
                symbol=symbol,
                size=float(position_size),
                allocation_pct=float(allocation_pct) * 100,
                risk_amount=float(risk_amount)
            )
            
            return recommendation
            
        except Exception as e:
            logger.error("Error calculating position size", error=str(e))
            return await self._default_position_size(current_price, stop_loss_pct)
    
    async def _get_target_goal(self, goal_id: Optional[str]) -> Optional[Dict]:
        """Get the goal to optimize for (specified or highest priority active)."""
        if goal_id:
            query = "SELECT * FROM financial_goals WHERE id = $1 AND status = 'active'"
            record = await self.db._postgres.fetchrow(query, uuid.UUID(goal_id))
        else:
            query = """
                SELECT * FROM financial_goals 
                WHERE status = 'active' 
                ORDER BY priority, created_at 
                LIMIT 1
            """
            record = await self.db._postgres.fetchrow(query)
        
        if record:
            return dict(record)
        return None
    
    async def _get_portfolio_value(self) -> Decimal:
        """Get current total portfolio value."""
        query = """
            SELECT COALESCE(SUM(total_value), 0) as total
            FROM portfolio_balances
            WHERE asset != 'USDT'
        """
        result = await self.db._postgres.fetchval(query)
        
        # Add USDT balance
        usdt_query = "SELECT COALESCE(SUM(free + locked), 0) FROM portfolio_balances WHERE asset = 'USDT'"
        usdt_balance = await self.db._postgres.fetchval(usdt_query)
        
        total = Decimal(str(result or 0)) + Decimal(str(usdt_balance or 0))
        
        # If no balance in DB, use default starting capital
        if total <= 0:
            total = Decimal("10000")  # Default $10K starting capital
        
        return total
    
    async def _calculate_goal_progress(self, goal: Dict, portfolio_value: Decimal) -> Dict:
        """Calculate detailed progress metrics for a goal."""
        goal_id = goal["id"]
        goal_type = goal["goal_type"]
        target_value = Decimal(str(goal["target_value"]))
        start_date = goal["start_date"]
        target_date = goal.get("target_date")
        
        # Get latest progress record
        query = """
            SELECT * FROM goal_progress 
            WHERE goal_id = $1 
            ORDER BY timestamp DESC 
            LIMIT 1
        """
        latest = await self.db._postgres.fetchrow(query, goal_id)
        
        # Calculate current value based on goal type
        if goal_type == "monthly_return_pct":
            # Calculate return this month
            month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            current_value = await self._calculate_monthly_return(month_start, portfolio_value)
        elif goal_type == "monthly_profit_usd":
            # Calculate profit this month
            month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            current_value = await self._calculate_monthly_profit(month_start)
        else:  # portfolio_target_usd
            current_value = portfolio_value
        
        # Calculate progress percentage
        progress_pct = (current_value / target_value * Decimal("100")) if target_value > 0 else Decimal("0")
        
        # Calculate time progress
        now = datetime.now(timezone.utc)
        if target_date:
            total_duration = (target_date - start_date).total_seconds()
            elapsed = (now - start_date).total_seconds()
            time_progress_pct = Decimal(str(elapsed / total_duration * 100)) if total_duration > 0 else Decimal("0")
            days_remaining = (target_date - now).days
        else:
            # For ongoing goals (monthly), use current month progress
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            total_duration = (month_end - month_start).total_seconds()
            elapsed = (now - month_start).total_seconds()
            time_progress_pct = Decimal(str(elapsed / total_duration * 100))
            days_remaining = (month_end - now).days
        
        # Check if on track (value progress >= time progress)
        on_track = progress_pct >= time_progress_pct
        
        # Calculate performance metrics
        win_rate = await self._calculate_win_rate(period_days=30)
        avg_win, avg_loss = await self._calculate_avg_win_loss(period_days=30)
        sharpe_ratio = await self._calculate_sharpe_ratio(period_days=30)
        
        # Calculate required daily return to reach goal
        if days_remaining > 0:
            remaining_value = target_value - current_value
            required_daily_return = (remaining_value / portfolio_value / Decimal(str(days_remaining))) if portfolio_value > 0 else Decimal("0")
        else:
            required_daily_return = Decimal("0")
        
        return {
            "current_value": current_value,
            "target_value": target_value,
            "progress_pct": progress_pct,
            "time_progress_pct": time_progress_pct,
            "on_track": on_track,
            "days_remaining": days_remaining,
            "required_daily_return": required_daily_return,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "sharpe_ratio": sharpe_ratio,
            "portfolio_value": portfolio_value
        }
    
    def _adjust_risk_for_progress(
        self,
        base_risk: Decimal,
        progress_pct: Decimal,
        time_progress_pct: Decimal,
        on_track: bool
    ) -> Decimal:
        """
        Adjust risk based on goal progress.
        - Behind schedule: Slightly increase risk (up to 50% more)
        - Ahead of schedule: Maintain or reduce risk
        - Way ahead: Reduce risk to lock in gains
        """
        gap = progress_pct - time_progress_pct
        
        if gap < Decimal("-20"):  # More than 20% behind
            # Increase risk by up to 50%
            multiplier = Decimal("1.5")
        elif gap < Decimal("-10"):  # 10-20% behind
            multiplier = Decimal("1.3")
        elif gap < Decimal("0"):  # Slightly behind
            multiplier = Decimal("1.1")
        elif gap > Decimal("30"):  # Way ahead (30%+)
            # Reduce risk to protect gains
            multiplier = Decimal("0.7")
        elif gap > Decimal("15"):  # Ahead (15-30%)
            multiplier = Decimal("0.85")
        else:  # On track (0-15% ahead)
            multiplier = Decimal("1.0")
        
        adjusted_risk = base_risk * multiplier
        
        # Enforce absolute limits (1% to 5% per trade)
        adjusted_risk = max(Decimal("0.01"), min(adjusted_risk, Decimal("0.05")))
        
        return adjusted_risk
    
    def _calculate_kelly_fraction(
        self,
        win_rate: Decimal,
        avg_win: Decimal,
        avg_loss: Decimal
    ) -> float:
        """
        Calculate Kelly Criterion for optimal position sizing.
        Kelly% = (Win% * AvgWin - Loss% * AvgLoss) / AvgWin
        """
        if avg_win <= 0 or win_rate <= 0:
            return 0.25  # Default conservative fraction
        
        loss_rate = Decimal("1") - win_rate
        kelly = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
        
        # Clamp to reasonable range (0-50%)
        kelly = max(Decimal("0"), min(kelly, Decimal("0.5")))
        
        return float(kelly)
    
    async def _calculate_monthly_return(self, month_start: datetime, current_portfolio_value: Decimal) -> Decimal:
        """Calculate return % for current month."""
        query = """
            SELECT COALESCE(SUM(total_value), 0) as value
            FROM portfolio_balances
            WHERE updated_at >= $1
        """
        start_value = await self.db._postgres.fetchval(query, month_start)
        
        if not start_value or start_value <= 0:
            start_value = current_portfolio_value  # Use current if no history
        
        monthly_return = ((current_portfolio_value - Decimal(str(start_value))) / Decimal(str(start_value))) if start_value > 0 else Decimal("0")
        return monthly_return
    
    async def _calculate_monthly_profit(self, month_start: datetime) -> Decimal:
        """Calculate total profit $ for current month."""
        query = """
            SELECT COALESCE(SUM(pnl), 0) as profit
            FROM trades
            WHERE executed_at >= $1 AND status = 'filled'
        """
        profit = await self.db._postgres.fetchval(query, month_start)
        return Decimal(str(profit or 0))
    
    async def _calculate_win_rate(self, period_days: int = 30) -> Decimal:
        """Calculate win rate over specified period."""
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
        return Decimal("0.5")  # Default 50% if no history
    
    async def _calculate_avg_win_loss(self, period_days: int = 30) -> Tuple[Decimal, Decimal]:
        """Calculate average win and loss sizes."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        query = """
            SELECT 
                AVG(pnl) FILTER (WHERE pnl > 0) as avg_win,
                ABS(AVG(pnl) FILTER (WHERE pnl < 0)) as avg_loss
            FROM trades
            WHERE executed_at >= $1 AND status = 'filled'
        """
        result = await self.db._postgres.fetchrow(query, cutoff)
        
        avg_win = Decimal(str(result["avg_win"] or 100))
        avg_loss = Decimal(str(result["avg_loss"] or 80))
        
        return avg_win, avg_loss
    
    async def _calculate_sharpe_ratio(self, period_days: int = 30) -> Decimal:
        """Calculate Sharpe ratio for recent performance."""
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
            # Annualized Sharpe (assuming 252 trading days)
            sharpe = (mean / std) * Decimal("252").sqrt() if std > 0 else Decimal("0")
            return sharpe
        return Decimal("0")
    
    def _generate_reasoning(
        self,
        goal: Dict,
        progress: Dict,
        adjusted_risk_pct: Decimal,
        kelly_fraction: float,
        confidence: Decimal,
        allocation_pct: Decimal
    ) -> str:
        """Generate human-readable explanation for position size."""
        goal_type_name = {
            "monthly_return_pct": "monthly return",
            "monthly_profit_usd": "monthly profit",
            "portfolio_target_usd": "portfolio value"
        }.get(goal["goal_type"], "goal")
        
        status = "ahead of" if progress["on_track"] else "behind"
        
        reasoning = f"""Position sized for {goal_type_name} goal ({float(goal['target_value']):.2f}).
Currently {status} schedule ({float(progress['progress_pct']):.1f}% progress, {float(progress['time_progress_pct']):.1f}% time elapsed).
Risk adjusted to {float(adjusted_risk_pct)*100:.1f}% per trade.
Kelly fraction: {kelly_fraction:.2%}, Signal confidence: {float(confidence):.2%}.
Recommended allocation: {float(allocation_pct)*100:.1f}% of portfolio.
Win rate: {float(progress['win_rate'])*100:.1f}%, Sharpe ratio: {float(progress['sharpe_ratio']):.2f}."""
        
        return reasoning
    
    async def _save_recommendation(self, recommendation: Dict) -> bool:
        """Save position sizing recommendation to database."""
        try:
            query = """
                INSERT INTO position_sizing_recommendations (
                    goal_id, strategy_id, symbol, recommended_size, recommended_allocation,
                    risk_amount, confidence_score, reasoning, metadata, valid_until
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW() + INTERVAL '1 hour')
                RETURNING id
            """
            import json
            await self.db._postgres.fetchval(
                query,
                uuid.UUID(recommendation["goal_id"]),
                uuid.UUID(recommendation["strategy_id"]) if recommendation.get("strategy_id") else None,
                recommendation["symbol"],
                recommendation["recommended_size"],
                recommendation["recommended_allocation"],
                recommendation["risk_amount"],
                recommendation["confidence_score"],
                recommendation["reasoning"],
                json.dumps(recommendation["metadata"])
            )
            return True
        except Exception as e:
            logger.error("Failed to save recommendation", error=str(e))
            return False
    
    async def _default_position_size(self, current_price: Decimal, stop_loss_pct: Decimal) -> Dict:
        """Fallback to conservative default position sizing."""
        portfolio_value = await self._get_portfolio_value()
        risk_amount = portfolio_value * self.default_risk_pct
        position_value = risk_amount / stop_loss_pct
        allocation_pct = position_value / portfolio_value
        allocation_pct = max(self.min_position_pct, min(allocation_pct, Decimal("0.05")))  # Max 5% fallback
        
        position_size = (portfolio_value * allocation_pct) / current_price
        
        return {
            "goal_id": None,
            "strategy_id": None,
            "symbol": "UNKNOWN",
            "recommended_size": float(position_size),
            "recommended_allocation": float(allocation_pct),
            "risk_amount": float(risk_amount),
            "confidence_score": 0.5,
            "reasoning": "Default conservative sizing (no active goal found)",
            "metadata": {
                "current_price": float(current_price),
                "stop_loss_pct": float(stop_loss_pct),
                "portfolio_value": float(portfolio_value)
            }
        }


async def main():
    """Test the goal-oriented position sizing engine."""
    from database import Database
    
    db = Database()
    await db.connect()
    
    try:
        sizer = GoalOrientedPositionSizer(db)
        
        # Test position sizing
        recommendation = await sizer.calculate_position_size(
            strategy_id=str(uuid.uuid4()),
            symbol="BTCUSDT",
            current_price=Decimal("45000"),
            stop_loss_pct=Decimal("0.02"),  # 2% stop loss
            confidence=Decimal("0.75")  # 75% confidence
        )
        
        print("\n=== Position Sizing Recommendation ===")
        print(f"Symbol: {recommendation['symbol']}")
        print(f"Recommended Size: {recommendation['recommended_size']:.8f}")
        print(f"Allocation: {recommendation['recommended_allocation']*100:.2f}%")
        print(f"Risk Amount: ${recommendation['risk_amount']:.2f}")
        print(f"Confidence: {recommendation['confidence_score']*100:.1f}%")
        print(f"\nReasoning:\n{recommendation['reasoning']}")
        
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
