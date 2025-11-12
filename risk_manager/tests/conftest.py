"""
Shared pytest fixtures for goal-oriented system tests
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def mock_database():
    """Mock RiskPostgresDatabase"""
    db = Mock()
    
    # Goal tracking methods
    db.get_current_goal_progress = AsyncMock(return_value={
        'monthly_return_progress': 0.50,  # 50% of target
        'monthly_income_progress': 0.75,  # 75% of target
        'portfolio_value': 45000.0,
        'monthly_return_actual': 0.025,  # 2.5% actual
        'monthly_income_actual': 1500.0  # $1500 actual
    })
    
    db.record_goal_snapshot = AsyncMock(return_value=True)
    db.get_goal_history = AsyncMock(return_value=[])
    db.update_goal_targets = AsyncMock(return_value=True)
    db.record_profit = AsyncMock(return_value=True)
    
    # Drawdown methods
    db.get_monthly_peak_value = AsyncMock(return_value=50000.0)
    db.update_monthly_peak = AsyncMock(return_value=True)
    db.record_drawdown_event = AsyncMock(return_value=True)
    db.get_current_portfolio_value = AsyncMock(return_value=48000.0)
    
    return db


@pytest.fixture
def fixed_datetime():
    """Fixed datetime for testing"""
    return datetime(2025, 11, 12, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def goal_progress_data():
    """Sample goal progress data"""
    return {
        'monthly_return_progress': 0.60,
        'monthly_income_progress': 0.80,
        'portfolio_value': 450000.0,
        'monthly_return_actual': 0.06,
        'monthly_income_actual': 3200.0,
        'days_into_month': 12
    }
