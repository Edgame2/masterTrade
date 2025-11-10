"""
Strategy Versioning & A/B Testing API

FastAPI endpoints for strategy version management and A/B testing.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from .version_manager import VersionManager, StrategyVersion, VersionStatus
from .ab_testing import ABTestManager, ABTest, TestStatus, TestVariant
from .performance_comparator import PerformanceComparator
from .statistical_tests import StatisticalTester


# Global instances
version_manager = VersionManager()
ab_test_manager = ABTestManager()
performance_comparator = PerformanceComparator()
statistical_tester = StatisticalTester()

versioning_router = APIRouter(prefix="/api/versioning", tags=["versioning"])


# ============= Request/Response Models =============

class CreateVersionRequest(BaseModel):
    strategy_id: str
    parameters: Dict[str, Any]
    code: str
    created_by: str
    description: str = ""
    changes: List[str] = []
    version_increment: str = "patch"


class PromoteVersionRequest(BaseModel):
    new_status: str  # "draft", "testing", "active", "deprecated", "retired"


class CreateABTestRequest(BaseModel):
    test_id: str
    name: str
    strategy_id: str
    control_version: str
    treatment_version: str
    traffic_split: float = 0.5
    min_sample_size: int = 100
    min_duration_hours: int = 24
    is_champion_challenger: bool = False


class RecordTradeRequest(BaseModel):
    test_id: str
    variant: str  # "control" or "treatment"
    pnl: float
    is_win: bool


class CompareVersionsRequest(BaseModel):
    strategy_id: str
    version1: str
    version2: str


class ComparePerformanceRequest(BaseModel):
    version1: str
    version1_returns: List[float]
    version2: str
    version2_returns: List[float]


class StatisticalTestRequest(BaseModel):
    control_samples: List[float]
    treatment_samples: List[float]
    confidence_level: float = 0.95


# ============= Version Management Endpoints =============

@versioning_router.post("/versions/create")
async def create_version(request: CreateVersionRequest):
    """Create a new strategy version"""
    
    try:
        version = version_manager.create_version(
            strategy_id=request.strategy_id,
            parameters=request.parameters,
            code=request.code,
            created_by=request.created_by,
            description=request.description,
            changes=request.changes,
            version_increment=request.version_increment,
        )
        
        return {
            "status": "success",
            "version": version.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.get("/versions/{strategy_id}/list")
async def list_versions(strategy_id: str, status: Optional[str] = None):
    """List all versions of a strategy"""
    
    try:
        version_status = VersionStatus(status) if status else None
        versions = version_manager.list_versions(strategy_id, version_status)
        
        return {
            "strategy_id": strategy_id,
            "count": len(versions),
            "versions": [v.to_dict() for v in versions],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.get("/versions/{strategy_id}/{version}")
async def get_version(strategy_id: str, version: str):
    """Get specific version details"""
    
    v = version_manager.get_version(strategy_id, version)
    if not v:
        raise HTTPException(status_code=404, detail="Version not found")
    
    return v.to_dict()


@versioning_router.get("/versions/{strategy_id}/latest")
async def get_latest_version(strategy_id: str):
    """Get latest version"""
    
    v = version_manager.get_latest_version(strategy_id)
    if not v:
        raise HTTPException(status_code=404, detail="No versions found")
    
    return v.to_dict()


@versioning_router.get("/versions/{strategy_id}/active")
async def get_active_version(strategy_id: str):
    """Get currently active version"""
    
    v = version_manager.get_active_version(strategy_id)
    if not v:
        raise HTTPException(status_code=404, detail="No active version")
    
    return v.to_dict()


@versioning_router.post("/versions/{strategy_id}/{version}/promote")
async def promote_version(strategy_id: str, version: str, request: PromoteVersionRequest):
    """Promote version to new status"""
    
    try:
        new_status = VersionStatus(request.new_status)
        success = version_manager.promote_version(strategy_id, version, new_status)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to promote version")
        
        return {
            "status": "success",
            "strategy_id": strategy_id,
            "version": version,
            "new_status": request.new_status,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid status: {request.new_status}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.post("/versions/{strategy_id}/rollback/{target_version}")
async def rollback_version(strategy_id: str, target_version: str):
    """Rollback to a previous version"""
    
    try:
        success = version_manager.rollback_to_version(strategy_id, target_version)
        
        if not success:
            raise HTTPException(status_code=400, detail="Rollback failed")
        
        return {
            "status": "success",
            "strategy_id": strategy_id,
            "rolled_back_to": target_version,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.post("/versions/compare")
async def compare_versions(request: CompareVersionsRequest):
    """Compare two versions"""
    
    try:
        comparison = version_manager.compare_versions(
            strategy_id=request.strategy_id,
            version1=request.version1,
            version2=request.version2,
        )
        
        return comparison
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.get("/versions/{strategy_id}/{version}/lineage")
async def get_version_lineage(strategy_id: str, version: str):
    """Get version lineage (ancestry)"""
    
    try:
        lineage = version_manager.get_version_lineage(strategy_id, version)
        
        return {
            "strategy_id": strategy_id,
            "version": version,
            "lineage": [v.to_dict() for v in lineage],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= A/B Testing Endpoints =============

@versioning_router.post("/ab-tests/create")
async def create_ab_test(request: CreateABTestRequest):
    """Create new A/B test"""
    
    try:
        test = ab_test_manager.create_test(
            test_id=request.test_id,
            name=request.name,
            strategy_id=request.strategy_id,
            control_version=request.control_version,
            treatment_version=request.treatment_version,
            traffic_split=request.traffic_split,
            min_sample_size=request.min_sample_size,
            min_duration_hours=request.min_duration_hours,
            is_champion_challenger=request.is_champion_challenger,
        )
        
        return {
            "status": "success",
            "test_id": test.test_id,
            "control_version": test.control_version,
            "treatment_version": test.treatment_version,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.post("/ab-tests/{test_id}/start")
async def start_ab_test(test_id: str):
    """Start A/B test"""
    
    success = ab_test_manager.start_test(test_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to start test")
    
    return {"status": "success", "test_id": test_id}


@versioning_router.get("/ab-tests/{test_id}/assign")
async def assign_variant(test_id: str):
    """Assign variant for a new trade"""
    
    result = ab_test_manager.assign_variant(test_id)
    if not result:
        raise HTTPException(status_code=404, detail="Test not found or not running")
    
    variant, version = result
    
    return {
        "test_id": test_id,
        "variant": variant.value,
        "version": version,
    }


@versioning_router.post("/ab-tests/record-trade")
async def record_trade(request: RecordTradeRequest):
    """Record trade result for A/B test"""
    
    try:
        variant = TestVariant(request.variant)
        ab_test_manager.record_trade_result(
            test_id=request.test_id,
            variant=variant,
            pnl=request.pnl,
            is_win=request.is_win,
        )
        
        return {"status": "success"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid variant")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.get("/ab-tests/{test_id}")
async def get_ab_test(test_id: str):
    """Get A/B test details"""
    
    test = ab_test_manager.get_test(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    
    return {
        "test_id": test.test_id,
        "name": test.name,
        "status": test.status.value,
        "control_version": test.control_version,
        "treatment_version": test.treatment_version,
        "control_trades": test.control_trades,
        "treatment_trades": test.treatment_trades,
        "control_pnl": test.control_pnl,
        "treatment_pnl": test.treatment_pnl,
        "control_win_rate": test.get_control_win_rate(),
        "treatment_win_rate": test.get_treatment_win_rate(),
        "winner": test.winner.value if test.winner else None,
        "is_significant": test.is_significant,
        "p_value": test.p_value,
    }


@versioning_router.post("/ab-tests/{test_id}/evaluate")
async def evaluate_ab_test(test_id: str):
    """Evaluate A/B test results"""
    
    result = ab_test_manager.evaluate_test(test_id)
    if not result:
        raise HTTPException(status_code=404, detail="Test not found")
    
    return result


@versioning_router.post("/ab-tests/{test_id}/stop")
async def stop_ab_test(test_id: str):
    """Stop A/B test"""
    
    success = ab_test_manager.stop_test(test_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to stop test")
    
    return {"status": "success", "test_id": test_id}


@versioning_router.get("/ab-tests/list")
async def list_ab_tests(strategy_id: Optional[str] = None, status: Optional[str] = None):
    """List A/B tests"""
    
    try:
        test_status = TestStatus(status) if status else None
        tests = ab_test_manager.list_tests(strategy_id, test_status)
        
        return {
            "count": len(tests),
            "tests": [
                {
                    "test_id": t.test_id,
                    "name": t.name,
                    "strategy_id": t.strategy_id,
                    "status": t.status.value,
                    "control_version": t.control_version,
                    "treatment_version": t.treatment_version,
                }
                for t in tests
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= Performance Comparison Endpoints =============

@versioning_router.post("/performance/compare")
async def compare_performance(request: ComparePerformanceRequest):
    """Compare performance between versions"""
    
    try:
        result = performance_comparator.compare(
            version1=request.version1,
            version1_returns=request.version1_returns,
            version2=request.version2,
            version2_returns=request.version2_returns,
        )
        
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.post("/performance/rank")
async def rank_versions(versions_data: Dict[str, List[float]]):
    """Rank multiple versions by performance"""
    
    try:
        rankings = performance_comparator.rank_versions(versions_data)
        return {"rankings": rankings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= Statistical Testing Endpoints =============

@versioning_router.post("/statistics/t-test")
async def t_test(request: StatisticalTestRequest):
    """Perform t-test"""
    
    try:
        result = statistical_tester.t_test(
            control_samples=request.control_samples,
            treatment_samples=request.treatment_samples,
            confidence_level=request.confidence_level,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.post("/statistics/mann-whitney")
async def mann_whitney_test(request: StatisticalTestRequest):
    """Perform Mann-Whitney U test"""
    
    try:
        result = statistical_tester.mann_whitney_test(
            control_samples=request.control_samples,
            treatment_samples=request.treatment_samples,
            confidence_level=request.confidence_level,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.post("/statistics/bayesian")
async def bayesian_comparison(request: StatisticalTestRequest):
    """Perform Bayesian comparison"""
    
    try:
        result = statistical_tester.bayesian_comparison(
            control_samples=request.control_samples,
            treatment_samples=request.treatment_samples,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@versioning_router.get("/health")
async def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "active_tests": len([t for t in ab_test_manager.tests.values() if t.status == TestStatus.RUNNING]),
        "total_versions": sum(len(versions) for versions in version_manager.versions.values()),
    }
