"""
A/B Testing Framework

Implements A/B testing for trading strategies with:
- Champion vs Challenger testing
- Traffic splitting
- Statistical significance testing
- Automatic promotion based on performance
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging
import random

logger = logging.getLogger(__name__)


class TestStatus(Enum):
    """A/B test status"""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TestVariant(Enum):
    """Test variant identifier"""
    CONTROL = "control"  # Champion
    TREATMENT = "treatment"  # Challenger


@dataclass
class ABTest:
    """A/B test configuration"""
    test_id: str
    name: str
    strategy_id: str
    
    # Versions being tested
    control_version: str  # Champion
    treatment_version: str  # Challenger
    
    # Traffic allocation (0.0 to 1.0)
    traffic_split: float = 0.5  # 50/50 by default
    
    # Test configuration
    min_sample_size: int = 100  # Minimum trades per variant
    min_duration_hours: int = 24  # Minimum test duration
    confidence_level: float = 0.95  # For significance testing
    
    # Status
    status: TestStatus = TestStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    
    # Results
    control_trades: int = 0
    treatment_trades: int = 0
    control_pnl: float = 0.0
    treatment_pnl: float = 0.0
    control_wins: int = 0
    treatment_wins: int = 0
    
    # Decision
    winner: Optional[TestVariant] = None
    is_significant: bool = False
    p_value: Optional[float] = None
    
    def get_control_win_rate(self) -> float:
        """Get control win rate"""
        if self.control_trades == 0:
            return 0.0
        return self.control_wins / self.control_trades
    
    def get_treatment_win_rate(self) -> float:
        """Get treatment win rate"""
        if self.treatment_trades == 0:
            return 0.0
        return self.treatment_wins / self.treatment_trades
    
    def get_control_avg_pnl(self) -> float:
        """Get control average PnL per trade"""
        if self.control_trades == 0:
            return 0.0
        return self.control_pnl / self.control_trades
    
    def get_treatment_avg_pnl(self) -> float:
        """Get treatment average PnL per trade"""
        if self.treatment_trades == 0:
            return 0.0
        return self.treatment_pnl / self.treatment_trades
    
    def is_ready_for_evaluation(self) -> bool:
        """Check if test has enough data for evaluation"""
        if self.status != TestStatus.RUNNING:
            return False
        
        # Check sample size
        if self.control_trades < self.min_sample_size or self.treatment_trades < self.min_sample_size:
            return False
        
        # Check duration
        if self.started_at:
            elapsed_hours = (datetime.utcnow() - self.started_at).total_seconds() / 3600
            if elapsed_hours < self.min_duration_hours:
                return False
        
        return True


@dataclass
class ChampionChallengerTest(ABTest):
    """
    Champion-Challenger test with automatic promotion.
    
    Champion: Current production version
    Challenger: New version being tested
    
    If challenger significantly outperforms champion, it becomes the new champion.
    """
    
    auto_promote: bool = True  # Automatically promote winner
    promotion_threshold_pct: float = 5.0  # Challenger must be 5% better
    
    def should_promote_challenger(self) -> bool:
        """Check if challenger should be promoted"""
        if not self.is_ready_for_evaluation():
            return False
        
        if not self.is_significant:
            return False
        
        if self.winner != TestVariant.TREATMENT:
            return False
        
        # Check if improvement exceeds threshold
        control_avg = self.get_control_avg_pnl()
        treatment_avg = self.get_treatment_avg_pnl()
        
        if control_avg <= 0:
            return treatment_avg > 0
        
        improvement_pct = ((treatment_avg - control_avg) / abs(control_avg)) * 100
        
        return improvement_pct >= self.promotion_threshold_pct


class ABTestManager:
    """
    Manages A/B tests for trading strategies.
    
    Features:
    - Traffic splitting
    - Automatic variant assignment
    - Performance tracking
    - Statistical significance testing
    - Automatic promotion
    """
    
    def __init__(self):
        self.tests: Dict[str, ABTest] = {}
        logger.info("ABTestManager initialized")
    
    def create_test(
        self,
        test_id: str,
        name: str,
        strategy_id: str,
        control_version: str,
        treatment_version: str,
        traffic_split: float = 0.5,
        min_sample_size: int = 100,
        min_duration_hours: int = 24,
        is_champion_challenger: bool = False,
    ) -> ABTest:
        """Create new A/B test"""
        
        if is_champion_challenger:
            test = ChampionChallengerTest(
                test_id=test_id,
                name=name,
                strategy_id=strategy_id,
                control_version=control_version,
                treatment_version=treatment_version,
                traffic_split=traffic_split,
                min_sample_size=min_sample_size,
                min_duration_hours=min_duration_hours,
            )
        else:
            test = ABTest(
                test_id=test_id,
                name=name,
                strategy_id=strategy_id,
                control_version=control_version,
                treatment_version=treatment_version,
                traffic_split=traffic_split,
                min_sample_size=min_sample_size,
                min_duration_hours=min_duration_hours,
            )
        
        self.tests[test_id] = test
        logger.info(f"Created A/B test: {test_id} ({control_version} vs {treatment_version})")
        return test
    
    def start_test(self, test_id: str) -> bool:
        """Start A/B test"""
        if test_id not in self.tests:
            logger.warning(f"Test {test_id} not found")
            return False
        
        test = self.tests[test_id]
        test.status = TestStatus.RUNNING
        test.started_at = datetime.utcnow()
        
        logger.info(f"Started A/B test: {test_id}")
        return True
    
    def assign_variant(self, test_id: str) -> Optional[Tuple[TestVariant, str]]:
        """
        Assign a variant for a new trade.
        
        Returns: (variant, version) or None if test not running
        """
        if test_id not in self.tests:
            return None
        
        test = self.tests[test_id]
        
        if test.status != TestStatus.RUNNING:
            return None
        
        # Random assignment based on traffic split
        if random.random() < test.traffic_split:
            return (TestVariant.CONTROL, test.control_version)
        else:
            return (TestVariant.TREATMENT, test.treatment_version)
    
    def record_trade_result(
        self,
        test_id: str,
        variant: TestVariant,
        pnl: float,
        is_win: bool,
    ):
        """Record trade result for a variant"""
        if test_id not in self.tests:
            return
        
        test = self.tests[test_id]
        
        if variant == TestVariant.CONTROL:
            test.control_trades += 1
            test.control_pnl += pnl
            if is_win:
                test.control_wins += 1
        else:
            test.treatment_trades += 1
            test.treatment_pnl += pnl
            if is_win:
                test.treatment_wins += 1
        
        logger.debug(f"Recorded trade for {test_id} {variant.value}: pnl={pnl}")
    
    def evaluate_test(self, test_id: str) -> Optional[Dict]:
        """
        Evaluate test results and determine winner.
        
        Uses statistical significance testing.
        """
        if test_id not in self.tests:
            return None
        
        test = self.tests[test_id]
        
        if not test.is_ready_for_evaluation():
            return {
                "status": "insufficient_data",
                "control_trades": test.control_trades,
                "treatment_trades": test.treatment_trades,
                "min_required": test.min_sample_size,
            }
        
        # Import statistical tester (will create in next file)
        from .statistical_tests import StatisticalTester
        
        tester = StatisticalTester()
        
        # Compare average PnL
        control_pnls = [test.control_pnl / test.control_trades] * test.control_trades
        treatment_pnls = [test.treatment_pnl / test.treatment_trades] * test.treatment_trades
        
        result = tester.t_test(
            control_pnls,
            treatment_pnls,
            confidence_level=test.confidence_level,
        )
        
        test.is_significant = result["is_significant"]
        test.p_value = result["p_value"]
        
        # Determine winner
        control_avg = test.get_control_avg_pnl()
        treatment_avg = test.get_treatment_avg_pnl()
        
        if test.is_significant:
            if treatment_avg > control_avg:
                test.winner = TestVariant.TREATMENT
            else:
                test.winner = TestVariant.CONTROL
        
        evaluation = {
            "test_id": test_id,
            "status": "complete",
            "is_significant": test.is_significant,
            "p_value": test.p_value,
            "winner": test.winner.value if test.winner else None,
            "control": {
                "trades": test.control_trades,
                "total_pnl": test.control_pnl,
                "avg_pnl": control_avg,
                "win_rate": test.get_control_win_rate(),
            },
            "treatment": {
                "trades": test.treatment_trades,
                "total_pnl": test.treatment_pnl,
                "avg_pnl": treatment_avg,
                "win_rate": test.get_treatment_win_rate(),
            },
        }
        
        # Check for automatic promotion
        if isinstance(test, ChampionChallengerTest):
            if test.should_promote_challenger():
                evaluation["recommendation"] = "promote_challenger"
                logger.info(f"Challenger {test.treatment_version} should be promoted")
            else:
                evaluation["recommendation"] = "keep_champion"
        
        return evaluation
    
    def stop_test(self, test_id: str) -> bool:
        """Stop A/B test"""
        if test_id not in self.tests:
            return False
        
        test = self.tests[test_id]
        test.status = TestStatus.COMPLETED
        test.ended_at = datetime.utcnow()
        
        logger.info(f"Stopped A/B test: {test_id}")
        return True
    
    def get_test(self, test_id: str) -> Optional[ABTest]:
        """Get test by ID"""
        return self.tests.get(test_id)
    
    def list_tests(
        self,
        strategy_id: Optional[str] = None,
        status: Optional[TestStatus] = None,
    ) -> List[ABTest]:
        """List all tests"""
        tests = list(self.tests.values())
        
        if strategy_id:
            tests = [t for t in tests if t.strategy_id == strategy_id]
        
        if status:
            tests = [t for t in tests if t.status == status]
        
        return tests
    
    def get_active_test_for_strategy(self, strategy_id: str) -> Optional[ABTest]:
        """Get active test for a strategy"""
        for test in self.tests.values():
            if test.strategy_id == strategy_id and test.status == TestStatus.RUNNING:
                return test
        return None
