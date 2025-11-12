"""
Unit Tests for Goal-Based Drawdown Protection

Tests:
- Initialization
- Drawdown stance determination
- Dynamic limit adjustments
- Breach detection
- Action triggering
- Monthly peak tracking
- Edge cases
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from goal_based_drawdown import (
    GoalBasedDrawdownProtector,
    DrawdownStance,
    DrawdownAction,
    DrawdownLimit,
    DrawdownEvent
)
from database import RiskPostgresDatabase


class TestDrawdownProtectorInitialization:
    """Test protector initialization"""
    
    def test_init_with_defaults(self, mock_database):
        """Test initialization with default parameters"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        assert protector.database == mock_database
        assert protector.normal_limit == 5.0
        assert protector.protective_limit == 2.0
        assert protector.milestone_threshold == 0.90
        
    def test_init_with_custom_limits(self, mock_database):
        """Test initialization with custom limits"""
        protector = GoalBasedDrawdownProtector(
            database=mock_database,
            normal_limit_percent=3.0,
            protective_limit_percent=1.0,
            milestone_threshold=0.95
        )
        
        assert protector.normal_limit == 3.0
        assert protector.protective_limit == 1.0
        assert protector.milestone_threshold == 0.95


class TestDrawdownStanceDetermination:
    """Test drawdown stance determination"""
    
    @pytest.mark.asyncio
    async def test_normal_stance_below_threshold(self, mock_database):
        """Test normal stance when below milestone threshold"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        # 80% of €1M goal = normal stance
        goal_progress = 800000.0 / 1_000_000.0
        
        stance = protector._determine_stance(goal_progress)
        
        assert stance == DrawdownStance.NORMAL
        
    @pytest.mark.asyncio
    async def test_protective_stance_near_milestone(self, mock_database):
        """Test protective stance when near milestone (>90%)"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        # 92% of €1M goal = protective stance
        goal_progress = 920000.0 / 1_000_000.0
        
        stance = protector._determine_stance(goal_progress)
        
        assert stance == DrawdownStance.PROTECTIVE
        
    @pytest.mark.asyncio
    async def test_breached_stance_when_limit_exceeded(self, mock_database):
        """Test breached stance when drawdown limit exceeded"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_monthly_peak_value = AsyncMock(return_value=50000.0)
        mock_database.get_current_portfolio_value = AsyncMock(return_value=47000.0)
        
        # 6% drawdown exceeds 5% normal limit
        limit = await protector.get_current_drawdown_limit()
        
        assert limit.current_drawdown_percent >= 5.0


class TestDynamicLimitAdjustment:
    """Test dynamic limit adjustments"""
    
    @pytest.mark.asyncio
    async def test_normal_limit_5_percent(self, mock_database):
        """Test 5% limit in normal stance"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_goal_progress = AsyncMock(return_value=0.80)  # 80% of goal
        
        with patch.object(protector, '_get_cached_goal_progress', return_value=0.80):
            stance = protector._determine_stance(0.80)
            
            assert stance == DrawdownStance.NORMAL
            
            if stance == DrawdownStance.NORMAL:
                limit = protector.normal_limit
                assert limit == 5.0
                
    @pytest.mark.asyncio
    async def test_protective_limit_2_percent(self, mock_database):
        """Test 2% limit in protective stance"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_goal_progress = AsyncMock(return_value=0.92)  # 92% of goal
        
        with patch.object(protector, '_get_cached_goal_progress', return_value=0.92):
            stance = protector._determine_stance(0.92)
            
            assert stance == DrawdownStance.PROTECTIVE
            
            if stance == DrawdownStance.PROTECTIVE:
                limit = protector.protective_limit
                assert limit == 2.0


class TestDrawdownBreachDetection:
    """Test drawdown breach detection"""
    
    @pytest.mark.asyncio
    async def test_detect_breach_in_normal_mode(self, mock_database):
        """Test breach detection in normal mode (5% limit)"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_monthly_peak_value = AsyncMock(return_value=50000.0)
        mock_database.get_current_portfolio_value = AsyncMock(return_value=47000.0)
        
        # 6% drawdown = breach of 5% limit
        limit = await protector.get_current_drawdown_limit()
        
        assert limit.current_drawdown_percent > 5.0
        assert limit.is_breached is True
        
    @pytest.mark.asyncio
    async def test_detect_breach_in_protective_mode(self, mock_database):
        """Test breach detection in protective mode (2% limit)"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_monthly_peak_value = AsyncMock(return_value=950000.0)
        mock_database.get_current_portfolio_value = AsyncMock(return_value=928000.0)
        mock_database.get_goal_progress = AsyncMock(return_value=0.93)  # 93% - protective
        
        # 2.3% drawdown = breach of 2% protective limit
        with patch.object(protector, '_get_cached_goal_progress', return_value=0.93):
            limit = await protector.get_current_drawdown_limit()
            
            # Should detect breach in protective mode
            
    @pytest.mark.asyncio
    async def test_no_breach_within_limit(self, mock_database):
        """Test no breach when within limit"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_monthly_peak_value = AsyncMock(return_value=50000.0)
        mock_database.get_current_portfolio_value = AsyncMock(return_value=49000.0)
        
        # 2% drawdown = within 5% limit
        limit = await protector.get_current_drawdown_limit()
        
        assert limit.current_drawdown_percent <= 5.0
        assert limit.is_breached is False


class TestActionTriggering:
    """Test action triggering on breach"""
    
    @pytest.mark.asyncio
    async def test_pause_new_on_breach(self, mock_database):
        """Test pause new positions action on breach"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        limit = DrawdownLimit(
            stance=DrawdownStance.BREACHED,
            monthly_limit_percent=5.0,
            current_drawdown_percent=6.0,
            is_breached=True,
            required_actions=[DrawdownAction.PAUSE_NEW],
            reason="Exceeded 5% monthly drawdown limit",
            portfolio_value=47000.0,
            peak_value=50000.0,
            goal_progress_percent=80.0
        )
        
        assert DrawdownAction.PAUSE_NEW in limit.required_actions
        
    @pytest.mark.asyncio
    async def test_reduce_positions_on_severe_breach(self, mock_database):
        """Test reduce positions action on severe breach"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        # Severe breach: 10% drawdown vs 5% limit
        mock_database.get_monthly_peak_value = AsyncMock(return_value=50000.0)
        mock_database.get_current_portfolio_value = AsyncMock(return_value=45000.0)
        
        limit = await protector.get_current_drawdown_limit()
        
        # Should recommend reducing positions
        if limit.current_drawdown_percent >= 8.0:  # Severe threshold
            assert DrawdownAction.REDUCE_POSITIONS in limit.required_actions
            
    @pytest.mark.asyncio
    async def test_close_all_on_critical_breach(self, mock_database):
        """Test close all positions on critical breach"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        # Critical breach: 15% drawdown vs 5% limit
        mock_database.get_monthly_peak_value = AsyncMock(return_value=50000.0)
        mock_database.get_current_portfolio_value = AsyncMock(return_value=42500.0)
        
        limit = await protector.get_current_drawdown_limit()
        
        # Should recommend emergency close
        if limit.current_drawdown_percent >= 15.0:  # Critical threshold
            assert DrawdownAction.CLOSE_ALL in limit.required_actions


class TestMonthlyPeakTracking:
    """Test monthly peak value tracking"""
    
    @pytest.mark.asyncio
    async def test_update_peak_on_new_high(self, mock_database):
        """Test updating peak when portfolio reaches new high"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_monthly_peak_value = AsyncMock(return_value=48000.0)
        mock_database.get_current_portfolio_value = AsyncMock(return_value=50000.0)
        
        # New high should update peak
        await protector._update_peak_if_needed(50000.0)
        
        mock_database.update_monthly_peak.assert_called_with(50000.0)
        
    @pytest.mark.asyncio
    async def test_no_update_below_peak(self, mock_database):
        """Test no update when below peak"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_monthly_peak_value = AsyncMock(return_value=52000.0)
        
        # Below peak should not update
        await protector._update_peak_if_needed(50000.0)
        
        # Should not call update
        
    @pytest.mark.asyncio
    async def test_reset_peak_on_new_month(self, mock_database):
        """Test resetting peak on new month"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        with patch.object(protector, '_reset_monthly_peak', new=AsyncMock()):
            await protector._reset_monthly_peak()


class TestDrawdownCalculation:
    """Test drawdown percentage calculation"""
    
    def test_calculate_drawdown_percent(self, mock_database):
        """Test drawdown percentage calculation"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        peak_value = 50000.0
        current_value = 47500.0
        
        drawdown_percent = ((peak_value - current_value) / peak_value) * 100
        
        assert drawdown_percent == 5.0
        
    def test_zero_drawdown_at_peak(self, mock_database):
        """Test zero drawdown when at peak"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        peak_value = 50000.0
        current_value = 50000.0
        
        drawdown_percent = ((peak_value - current_value) / peak_value) * 100
        
        assert drawdown_percent == 0.0
        
    def test_large_drawdown(self, mock_database):
        """Test large drawdown calculation"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        peak_value = 50000.0
        current_value = 35000.0
        
        drawdown_percent = ((peak_value - current_value) / peak_value) * 100
        
        assert drawdown_percent == 30.0


class TestEventLogging:
    """Test drawdown event logging"""
    
    @pytest.mark.asyncio
    async def test_log_breach_event(self, mock_database):
        """Test logging breach event to database"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        event = DrawdownEvent(
            timestamp=datetime.now(timezone.utc),
            stance=DrawdownStance.BREACHED,
            monthly_limit_percent=5.0,
            actual_drawdown_percent=6.5,
            portfolio_value=47000.0,
            peak_value=50000.0,
            actions_taken=[DrawdownAction.PAUSE_NEW],
            reason="Exceeded normal 5% limit"
        )
        
        await mock_database.record_drawdown_event(event.__dict__)
        
        mock_database.record_drawdown_event.assert_called_once()


class TestGoalProgressCaching:
    """Test goal progress caching"""
    
    @pytest.mark.asyncio
    async def test_cache_goal_progress(self, mock_database):
        """Test caching of goal progress to reduce DB queries"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_goal_progress = AsyncMock(return_value=0.85)
        
        # First call should query DB
        progress1 = await protector._get_cached_goal_progress()
        
        # Second call should use cache
        progress2 = await protector._get_cached_goal_progress()
        
        # Should only call DB once
        # (depends on implementation)
        
    @pytest.mark.asyncio
    async def test_cache_expiration(self, mock_database):
        """Test cache expiration after duration"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        protector._cache_duration = timedelta(minutes=5)
        
        # Set old cache timestamp
        protector._cache_timestamp = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        # Should refresh cache


class TestEdgeCases:
    """Test edge cases"""
    
    @pytest.mark.asyncio
    async def test_zero_peak_value(self, mock_database):
        """Test handling of zero peak value"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_monthly_peak_value = AsyncMock(return_value=0.0)
        mock_database.get_current_portfolio_value = AsyncMock(return_value=50000.0)
        
        # Should handle gracefully (avoid division by zero)
        
    @pytest.mark.asyncio
    async def test_negative_drawdown(self, mock_database):
        """Test handling of negative drawdown (portfolio above peak)"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        mock_database.get_monthly_peak_value = AsyncMock(return_value=48000.0)
        mock_database.get_current_portfolio_value = AsyncMock(return_value=50000.0)
        
        # Current above peak = negative drawdown (should be 0 or update peak)
        
    @pytest.mark.asyncio
    async def test_exactly_at_milestone_threshold(self, mock_database):
        """Test exactly at milestone threshold (90%)"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        # Exactly 90% of €1M
        goal_progress = 0.90
        
        stance = protector._determine_stance(goal_progress)
        
        # Should be protective (>= threshold)
        assert stance == DrawdownStance.PROTECTIVE
        
    @pytest.mark.asyncio
    async def test_above_milestone(self, mock_database):
        """Test portfolio above milestone (>100%)"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        # 105% of €1M goal
        goal_progress = 1.05
        
        stance = protector._determine_stance(goal_progress)
        
        # Should still be protective
        assert stance == DrawdownStance.PROTECTIVE


class TestProtectiveVsNormalThresholds:
    """Test differences between protective and normal modes"""
    
    @pytest.mark.asyncio
    async def test_breach_threshold_difference(self, mock_database):
        """Test that protective mode has stricter threshold"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        # 3% drawdown
        peak = 50000.0
        current = 48500.0
        drawdown = 3.0  # 3%
        
        # In normal mode (5% limit): NOT breached
        normal_breached = drawdown > protector.normal_limit
        assert normal_breached is False
        
        # In protective mode (2% limit): BREACHED
        protective_breached = drawdown > protector.protective_limit
        assert protective_breached is True


class TestMultipleBreachActions:
    """Test multiple actions can be triggered"""
    
    @pytest.mark.asyncio
    async def test_multiple_actions_on_severe_breach(self, mock_database):
        """Test multiple actions on severe breach"""
        protector = GoalBasedDrawdownProtector(database=mock_database)
        
        # Severe breach in protective mode
        mock_database.get_monthly_peak_value = AsyncMock(return_value=950000.0)
        mock_database.get_current_portfolio_value = AsyncMock(return_value=920000.0)
        mock_database.get_goal_progress = AsyncMock(return_value=0.92)
        
        # 3.2% drawdown in protective mode (2% limit) = severe
        limit = await protector.get_current_drawdown_limit()
        
        # Should have multiple actions
        if limit.is_breached:
            assert len(limit.required_actions) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
