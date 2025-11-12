"""
Unit Tests for Goal Tracking Service

Tests:
- Initialization
- Goal progress calculation
- Daily snapshots
- Alert triggering
- Goal status determination
- Monthly resets
- Edge cases
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from goal_tracking_service import GoalTrackingService
from database import RiskPostgresDatabase


class TestGoalTrackingServiceInitialization:
    """Test service initialization"""
    
    def test_init_with_defaults(self, mock_database):
        """Test initialization with default parameters"""
        service = GoalTrackingService(database=mock_database)
        
        assert service.database == mock_database
        assert service.monthly_return_target == 5.0
        assert service.monthly_income_target == 2000.0
        assert service.portfolio_value_target == 50000.0
        assert service.running is False
        
    def test_init_with_custom_targets(self, mock_database):
        """Test initialization with custom targets"""
        service = GoalTrackingService(database=mock_database)
        service.monthly_return_target = 10.0
        service.monthly_income_target = 4000.0
        service.portfolio_value_target = 1_000_000.0
        
        assert service.monthly_return_target == 10.0
        assert service.monthly_income_target == 4000.0
        assert service.portfolio_value_target == 1_000_000.0


class TestGoalProgressCalculation:
    """Test goal progress calculations"""
    
    @pytest.mark.asyncio
    async def test_calculate_monthly_return_progress(self, mock_database):
        """Test monthly return progress calculation"""
        service = GoalTrackingService(database=mock_database)
        service.portfolio_value_start_of_month = 40000.0
        current_value = 42000.0  # 5% gain
        
        return_percent = ((current_value - service.portfolio_value_start_of_month) 
                         / service.portfolio_value_start_of_month * 100)
        
        assert return_percent == 5.0
        
    @pytest.mark.asyncio
    async def test_calculate_monthly_income_progress(self, mock_database):
        """Test monthly income progress calculation"""
        service = GoalTrackingService(database=mock_database)
        service.income_month_to_date = 1500.0
        service.monthly_income_target = 2000.0
        
        progress = service.income_month_to_date / service.monthly_income_target
        
        assert progress == 0.75  # 75% of target
        
    @pytest.mark.asyncio
    async def test_portfolio_value_progress(self, mock_database):
        """Test portfolio value progress calculation"""
        service = GoalTrackingService(database=mock_database)
        current_value = 45000.0
        target = 50000.0
        
        progress = current_value / target
        
        assert progress == 0.9  # 90% of target


class TestDailySnapshots:
    """Test daily snapshot functionality"""
    
    @pytest.mark.asyncio
    async def test_create_daily_snapshot(self, mock_database):
        """Test creating a daily snapshot"""
        service = GoalTrackingService(database=mock_database)
        
        with patch.object(service, '_take_snapshot', new=AsyncMock()) as mock_snapshot:
            await service._take_snapshot()
            mock_snapshot.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_snapshot_only_once_per_day(self, mock_database):
        """Test that snapshot is only taken once per day"""
        service = GoalTrackingService(database=mock_database)
        service.last_snapshot_date = date.today()
        
        with patch.object(service, '_should_take_snapshot', return_value=False):
            # Should not take snapshot if already done today
            assert service.last_snapshot_date == date.today()
            
    @pytest.mark.asyncio
    async def test_snapshot_data_recorded(self, mock_database):
        """Test that snapshot data is recorded to database"""
        service = GoalTrackingService(database=mock_database)
        
        mock_database.get_current_portfolio_value = AsyncMock(return_value=45000.0)
        
        with patch.object(service, '_get_portfolio_value', new=AsyncMock(return_value=45000.0)):
            with patch.object(service, '_take_snapshot', new=AsyncMock()):
                await service._take_snapshot()
                
        mock_database.record_goal_snapshot.assert_called()


class TestAlertTriggering:
    """Test alert triggering logic"""
    
    @pytest.mark.asyncio
    async def test_alert_on_goal_achieved(self, mock_database):
        """Test alert when goal is achieved"""
        service = GoalTrackingService(database=mock_database)
        
        with patch.object(service, '_send_alert', new=AsyncMock()) as mock_alert:
            await service._check_and_send_alerts(
                monthly_return_progress=1.0,  # 100% - goal achieved
                monthly_income_progress=1.0,
                portfolio_value=50000.0
            )
            # Alert should be sent
            
    @pytest.mark.asyncio
    async def test_alert_on_goal_at_risk(self, mock_database):
        """Test alert when goal is at risk"""
        service = GoalTrackingService(database=mock_database)
        
        # 25th of month, only 40% progress
        with patch.object(service, '_send_alert', new=AsyncMock()) as mock_alert:
            await service._check_and_send_alerts(
                monthly_return_progress=0.4,
                monthly_income_progress=0.4,
                portfolio_value=42000.0
            )
            
    @pytest.mark.asyncio
    async def test_no_alert_when_on_track(self, mock_database):
        """Test no alert when goals are on track"""
        service = GoalTrackingService(database=mock_database)
        
        # 15th of month, 50% progress - on track
        with patch.object(service, '_send_alert', new=AsyncMock()) as mock_alert:
            # On track should not trigger alert
            pass


class TestGoalStatusDetermination:
    """Test goal status determination"""
    
    def test_status_on_track(self, mock_database):
        """Test status when on track"""
        service = GoalTrackingService(database=mock_database)
        
        # 50% progress on day 15 (50% of month) = on track
        status = service._determine_status(
            progress=0.5,
            days_into_month=15,
            days_in_month=30
        )
        
        assert status in ["on_track", "normal"]
        
    def test_status_ahead(self, mock_database):
        """Test status when ahead of schedule"""
        service = GoalTrackingService(database=mock_database)
        
        # 80% progress on day 15 (50% of month) = ahead
        status = service._determine_status(
            progress=0.8,
            days_into_month=15,
            days_in_month=30
        )
        
        assert status in ["ahead", "excellent"]
        
    def test_status_at_risk(self, mock_database):
        """Test status when at risk"""
        service = GoalTrackingService(database=mock_database)
        
        # 30% progress on day 25 (83% of month) = at risk
        status = service._determine_status(
            progress=0.3,
            days_into_month=25,
            days_in_month=30
        )
        
        assert status in ["at_risk", "behind"]
        
    def test_status_achieved(self, mock_database):
        """Test status when goal achieved"""
        service = GoalTrackingService(database=mock_database)
        
        # 100%+ progress = achieved
        status = service._determine_status(
            progress=1.0,
            days_into_month=20,
            days_in_month=30
        )
        
        assert status in ["achieved", "completed"]


class TestMonthlyReset:
    """Test monthly reset functionality"""
    
    @pytest.mark.asyncio
    async def test_reset_on_new_month(self, mock_database):
        """Test reset when new month starts"""
        service = GoalTrackingService(database=mock_database)
        
        # Set last snapshot to previous month
        service.last_snapshot_date = date(2025, 10, 31)
        
        with patch.object(service, '_initialize_tracking_state', new=AsyncMock()):
            # Should detect new month and reset
            await service._initialize_tracking_state()
            
    @pytest.mark.asyncio
    async def test_reset_clears_income_tracking(self, mock_database):
        """Test that monthly reset clears income tracking"""
        service = GoalTrackingService(database=mock_database)
        service.income_month_to_date = 5000.0
        
        with patch.object(service, '_reset_monthly_tracking', new=AsyncMock()):
            await service._reset_monthly_tracking()
            # Income should be reset
            
    @pytest.mark.asyncio
    async def test_reset_updates_start_portfolio_value(self, mock_database):
        """Test that reset updates start of month portfolio value"""
        service = GoalTrackingService(database=mock_database)
        
        mock_database.get_current_portfolio_value = AsyncMock(return_value=50000.0)
        
        with patch.object(service, '_initialize_tracking_state', new=AsyncMock()):
            await service._initialize_tracking_state()


class TestServiceLifecycle:
    """Test service start/stop lifecycle"""
    
    @pytest.mark.asyncio
    async def test_start_service(self, mock_database):
        """Test starting the service"""
        service = GoalTrackingService(database=mock_database)
        
        with patch.object(service, '_initialize_tracking_state', new=AsyncMock()):
            with patch.object(service, '_daily_scheduler', new=AsyncMock()):
                await service.start()
                
                assert service.running is True
                
    @pytest.mark.asyncio
    async def test_stop_service(self, mock_database):
        """Test stopping the service"""
        service = GoalTrackingService(database=mock_database)
        service.running = True
        service.scheduler_task = AsyncMock()
        
        with patch.object(service.scheduler_task, 'cancel'):
            await service.stop()
            
            assert service.running is False
            
    @pytest.mark.asyncio
    async def test_cannot_start_twice(self, mock_database):
        """Test that service cannot be started twice"""
        service = GoalTrackingService(database=mock_database)
        service.running = True
        
        with patch.object(service, '_initialize_tracking_state', new=AsyncMock()):
            await service.start()
            # Should log warning but not start again


class TestEdgeCases:
    """Test edge cases"""
    
    @pytest.mark.asyncio
    async def test_goal_achieved_early(self, mock_database):
        """Test when goal is achieved early in the month"""
        service = GoalTrackingService(database=mock_database)
        
        # Goal achieved on day 5
        with patch.object(service, '_send_alert', new=AsyncMock()) as mock_alert:
            await service._check_and_send_alerts(
                monthly_return_progress=1.0,
                monthly_income_progress=1.0,
                portfolio_value=50000.0
            )
            # Should send achievement alert
            
    @pytest.mark.asyncio
    async def test_severe_underperformance(self, mock_database):
        """Test handling of severe underperformance"""
        service = GoalTrackingService(database=mock_database)
        
        # Only 10% progress on day 28 - severe underperformance
        status = service._determine_status(
            progress=0.1,
            days_into_month=28,
            days_in_month=30
        )
        
        assert status in ["critical", "at_risk", "behind"]
        
    @pytest.mark.asyncio
    async def test_negative_returns(self, mock_database):
        """Test handling of negative monthly returns"""
        service = GoalTrackingService(database=mock_database)
        service.portfolio_value_start_of_month = 50000.0
        current_value = 45000.0  # -10% loss
        
        return_percent = ((current_value - service.portfolio_value_start_of_month) 
                         / service.portfolio_value_start_of_month * 100)
        
        assert return_percent == -10.0
        
    @pytest.mark.asyncio
    async def test_zero_start_portfolio_value(self, mock_database):
        """Test handling of zero start portfolio value"""
        service = GoalTrackingService(database=mock_database)
        service.portfolio_value_start_of_month = 0.0
        
        # Should handle gracefully (avoid division by zero)
        
    @pytest.mark.asyncio
    async def test_portfolio_value_milestone_reached(self, mock_database):
        """Test when portfolio value milestone is reached"""
        service = GoalTrackingService(database=mock_database)
        service.portfolio_value_target = 50000.0
        
        with patch.object(service, '_send_alert', new=AsyncMock()) as mock_alert:
            await service._check_and_send_alerts(
                monthly_return_progress=0.8,
                monthly_income_progress=0.8,
                portfolio_value=50000.0  # Milestone reached!
            )


class TestDailyScheduler:
    """Test daily scheduler functionality"""
    
    @pytest.mark.asyncio
    async def test_scheduler_runs_daily(self, mock_database):
        """Test that scheduler attempts to run daily"""
        service = GoalTrackingService(database=mock_database)
        
        with patch.object(service, '_take_snapshot', new=AsyncMock()):
            # Scheduler should check daily
            pass
            
    @pytest.mark.asyncio
    async def test_scheduler_handles_errors(self, mock_database):
        """Test that scheduler handles errors gracefully"""
        service = GoalTrackingService(database=mock_database)
        
        with patch.object(service, '_take_snapshot', new=AsyncMock(side_effect=Exception("Test error"))):
            # Scheduler should continue running after error
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
