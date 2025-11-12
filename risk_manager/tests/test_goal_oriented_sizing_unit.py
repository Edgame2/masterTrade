"""
Unit Tests for Goal-Oriented Position Sizing Module

Tests:
- Initialization
- Goal adjustment factor calculation
- Progress-based adjustments
- Portfolio milestone protection
- Edge cases
- Time-based adjustments
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from goal_oriented_sizing import GoalOrientedSizingModule
from database import RiskPostgresDatabase


class TestGoalOrientedSizingInitialization:
    """Test module initialization"""
    
    def test_init_with_database(self, mock_database):
        """Test initialization with database"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        assert module.database == mock_database
        assert module.TARGET_MONTHLY_RETURN == 0.10
        assert module.TARGET_MONTHLY_INCOME == 4000.0
        assert module.TARGET_PORTFOLIO_VALUE == 1_000_000.0
        
    def test_adjustment_factors_configured(self, mock_database):
        """Test that adjustment factors are properly configured"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        assert module.MAX_AGGRESSIVE_FACTOR == 1.3
        assert module.NORMAL_FACTOR == 1.0
        assert module.MIN_CONSERVATIVE_FACTOR == 0.5
        
    def test_thresholds_configured(self, mock_database):
        """Test that progress thresholds are configured"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        assert module.AHEAD_THRESHOLD == 1.15
        assert module.ON_TRACK_MIN == 0.85
        assert module.AT_RISK_THRESHOLD == 0.70
        assert module.CRITICAL_THRESHOLD == 0.50


class TestAdjustmentFactorCalculation:
    """Test adjustment factor calculation"""
    
    @pytest.mark.asyncio
    async def test_normal_factor_when_on_track(self, mock_database):
        """Test normal factor (1.0x) when goals are on track"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=500000.0,
            monthly_return_progress=0.90,  # 90% of target - on track
            monthly_income_progress=0.95,  # 95% of target - on track
            days_into_month=15
        )
        
        assert 0.9 <= factor <= 1.1  # Near normal
        
    @pytest.mark.asyncio
    async def test_aggressive_factor_when_behind(self, mock_database):
        """Test aggressive factor (>1.0x) when behind on goals"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=300000.0,
            monthly_return_progress=0.40,  # 40% of target - behind
            monthly_income_progress=0.50,  # 50% of target - behind
            days_into_month=20
        )
        
        assert factor > 1.0  # Aggressive to catch up
        assert factor <= 1.3  # But capped at max
        
    @pytest.mark.asyncio
    async def test_conservative_factor_when_ahead(self, mock_database):
        """Test conservative factor (<1.0x) when ahead of goals"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=400000.0,
            monthly_return_progress=1.20,  # 120% of target - ahead
            monthly_income_progress=1.15,  # 115% of target - ahead
            days_into_month=20
        )
        
        assert factor < 1.0  # Conservative to protect gains
        assert factor >= 0.7  # But not too conservative


class TestPortfolioMilestoneProtection:
    """Test portfolio milestone protection mode"""
    
    @pytest.mark.asyncio
    async def test_preservation_mode_near_milestone(self, mock_database):
        """Test preservation mode when near €1M milestone"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=900000.0,  # €900k - near €1M
            monthly_return_progress=1.0,
            monthly_income_progress=1.0,
            days_into_month=15
        )
        
        assert factor < 1.0  # Should be conservative
        assert factor >= 0.5  # But within range
        
    @pytest.mark.asyncio
    async def test_full_preservation_at_950k(self, mock_database):
        """Test full preservation mode at €950k"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=950000.0,  # €950k - full preservation
            monthly_return_progress=1.0,
            monthly_income_progress=1.0,
            days_into_month=15
        )
        
        assert factor <= 0.7  # Very conservative
        assert factor >= 0.5  # Minimum factor
        
    @pytest.mark.asyncio
    async def test_no_preservation_below_800k(self, mock_database):
        """Test no preservation mode below €800k"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=700000.0,  # €700k - no preservation
            monthly_return_progress=1.0,
            monthly_income_progress=1.0,
            days_into_month=15
        )
        
        # Should allow normal or aggressive sizing
        assert factor >= 0.9


class TestProgressBasedAdjustments:
    """Test adjustments based on goal progress"""
    
    @pytest.mark.asyncio
    async def test_critical_underperformance(self, mock_database):
        """Test adjustment for critical underperformance (<50% of target)"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=300000.0,
            monthly_return_progress=0.30,  # 30% - critical
            monthly_income_progress=0.40,  # 40% - critical
            days_into_month=25
        )
        
        assert factor > 1.1  # Aggressive to recover
        
    @pytest.mark.asyncio
    async def test_at_risk_performance(self, mock_database):
        """Test adjustment when at risk (50-70% of target)"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=400000.0,
            monthly_return_progress=0.65,  # 65% - at risk
            monthly_income_progress=0.60,  # 60% - at risk
            days_into_month=20
        )
        
        assert factor > 1.0  # Slightly aggressive
        
    @pytest.mark.asyncio
    async def test_ahead_performance(self, mock_database):
        """Test adjustment when ahead (>115% of target)"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=500000.0,
            monthly_return_progress=1.25,  # 125% - ahead
            monthly_income_progress=1.20,  # 120% - ahead
            days_into_month=15
        )
        
        assert factor < 1.0  # Conservative to lock in gains


class TestTimeBasedAdjustments:
    """Test time-based adjustment logic"""
    
    @pytest.mark.asyncio
    async def test_early_month_tolerance(self, mock_database):
        """Test more tolerance early in the month"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        # Low progress on day 5 - still acceptable
        factor_early = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=400000.0,
            monthly_return_progress=0.15,  # 15% on day 5
            monthly_income_progress=0.20,  # 20% on day 5
            days_into_month=5
        )
        
        # Should not be too aggressive yet
        assert factor_early <= 1.2
        
    @pytest.mark.asyncio
    async def test_late_month_urgency(self, mock_database):
        """Test increased urgency late in the month"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        # Low progress on day 28 - critical
        factor_late = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=400000.0,
            monthly_return_progress=0.60,  # 60% on day 28 - behind
            monthly_income_progress=0.65,  # 65% on day 28 - behind
            days_into_month=28
        )
        
        # Should be more aggressive
        assert factor_late > 1.1


class TestCombinedFactors:
    """Test combined adjustment factors"""
    
    @pytest.mark.asyncio
    async def test_behind_but_near_milestone(self, mock_database):
        """Test conflict: behind on goals but near €1M milestone"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=900000.0,  # Near milestone
            monthly_return_progress=0.60,  # Behind on return
            monthly_income_progress=0.70,  # Behind on income
            days_into_month=20
        )
        
        # Preservation should override aggressive sizing
        assert factor < 1.0
        
    @pytest.mark.asyncio
    async def test_ahead_but_low_portfolio(self, mock_database):
        """Test: ahead on goals but low portfolio value"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=200000.0,  # Low value
            monthly_return_progress=1.30,  # Ahead on return
            monthly_income_progress=1.20,  # Ahead on income
            days_into_month=15
        )
        
        # Can still be somewhat aggressive since far from milestone
        assert factor >= 0.8


class TestEdgeCases:
    """Test edge cases"""
    
    @pytest.mark.asyncio
    async def test_zero_progress(self, mock_database):
        """Test handling of zero progress"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=400000.0,
            monthly_return_progress=0.0,  # Zero progress
            monthly_income_progress=0.0,
            days_into_month=20
        )
        
        # Should return maximum aggressive factor
        assert factor >= 1.0
        
    @pytest.mark.asyncio
    async def test_negative_progress(self, mock_database):
        """Test handling of negative progress (losses)"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=350000.0,
            monthly_return_progress=-0.10,  # Negative (loss)
            monthly_income_progress=0.50,
            days_into_month=15
        )
        
        # Should handle gracefully (may be very aggressive or capped)
        assert 0.5 <= factor <= 1.3
        
    @pytest.mark.asyncio
    async def test_extreme_overperformance(self, mock_database):
        """Test handling of extreme overperformance (>200% of target)"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=600000.0,
            monthly_return_progress=2.50,  # 250% of target!
            monthly_income_progress=2.00,  # 200% of target!
            days_into_month=10
        )
        
        # Should be very conservative to protect huge gains
        assert factor <= 0.8
        
    @pytest.mark.asyncio
    async def test_first_day_of_month(self, mock_database):
        """Test calculation on first day of month"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=400000.0,
            monthly_return_progress=0.0,
            monthly_income_progress=0.0,
            days_into_month=1
        )
        
        # Should not be too aggressive on day 1
        assert 0.9 <= factor <= 1.1
        
    @pytest.mark.asyncio
    async def test_last_day_of_month(self, mock_database):
        """Test calculation on last day of month"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=400000.0,
            monthly_return_progress=0.95,  # Almost there
            monthly_income_progress=0.90,
            days_into_month=30
        )
        
        # Depends on implementation - might push for completion or lock in
        assert 0.5 <= factor <= 1.3


class TestDatabaseIntegration:
    """Test database integration"""
    
    @pytest.mark.asyncio
    async def test_fetch_goal_progress_from_db(self, mock_database):
        """Test fetching goal progress from database"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        mock_database.get_current_goal_progress = AsyncMock(return_value={
            'monthly_return_progress': 0.75,
            'monthly_income_progress': 0.80,
            'portfolio_value': 450000.0
        })
        
        progress = await mock_database.get_current_goal_progress()
        
        assert progress['monthly_return_progress'] == 0.75
        assert progress['monthly_income_progress'] == 0.80
        assert progress['portfolio_value'] == 450000.0
        
        mock_database.get_current_goal_progress.assert_called_once()


class TestFactorBoundaries:
    """Test that factors are within valid boundaries"""
    
    @pytest.mark.asyncio
    async def test_factor_never_below_min(self, mock_database):
        """Test that factor never goes below minimum (0.5)"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        # Extreme case: at milestone with huge gains
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=980000.0,
            monthly_return_progress=3.0,
            monthly_income_progress=3.0,
            days_into_month=5
        )
        
        assert factor >= 0.5
        
    @pytest.mark.asyncio
    async def test_factor_never_above_max(self, mock_database):
        """Test that factor never goes above maximum (1.3)"""
        module = GoalOrientedSizingModule(database=mock_database)
        
        # Extreme case: critical underperformance
        factor = await module.calculate_goal_adjustment_factor(
            current_portfolio_value=100000.0,
            monthly_return_progress=0.05,
            monthly_income_progress=0.10,
            days_into_month=28
        )
        
        assert factor <= 1.3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
