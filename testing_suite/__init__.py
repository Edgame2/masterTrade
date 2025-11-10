"""
Comprehensive Testing Suite

End-to-end testing framework for masterTrade platform with unit tests,
integration tests, performance tests, and automated test execution.
"""

from .test_runner import (
    TestRunner,
    TestSuite,
    TestCase,
    TestResult,
    TestStatus,
    TestCategory
)

from .unit_tests import (
    UnitTestManager,
    DatabaseTestCase,
    APITestCase,
    ServiceTestCase,
    UtilityTestCase
)

from .integration_tests import (
    IntegrationTestManager,
    ServiceIntegrationTest,
    DatabaseIntegrationTest,
    APIIntegrationTest,
    WorkflowIntegrationTest
)

from .performance_tests import (
    PerformanceTestManager,
    LoadTestCase,
    StressTestCase,
    EnduranceTestCase,
    ScalabilityTestCase
)

from .test_data_manager import (
    TestDataManager,
    TestDataGenerator,
    MockDataProvider,
    TestDatabase
)

from .test_utilities import (
    TestUtilities,
    MockService,
    TestHelpers,
    AssertionHelpers,
    TestFixtures
)

from .report_generator import (
    TestReportGenerator,
    TestMetrics,
    CoverageAnalyzer,
    TestDashboard
)

__version__ = "1.0.0"

# Default testing configuration
DEFAULT_CONFIG = {
    "testing": {
        "enabled": True,
        "parallel_execution": True,
        "max_workers": 4,
        "timeout_seconds": 300,
        "retry_attempts": 3,
        "fail_fast": False,
        "verbose": True,
        "generate_reports": True,
        "coverage_threshold": 80.0,
        
        # Test categories to run
        "categories": [
            "unit",
            "integration", 
            "performance",
            "security",
            "api"
        ],
        
        # Test environments
        "environments": {
            "unit": {
                "database_url": "sqlite:///:memory:",
                "redis_url": "redis://localhost:6379/15",
                "mock_external_services": True,
                "log_level": "WARNING"
            },
            "integration": {
                "database_type": "cosmos_db",
                "cosmos_database": "mmasterTrade_test",
                "redis_url": "redis://localhost:6379/14", 
                "mock_external_services": False,
                "log_level": "INFO"
            },
            "performance": {
                "database_type": "cosmos_db", 
                "cosmos_database": "mmasterTrade_perf_test",
                "redis_url": "redis://localhost:6379/13",
                "mock_external_services": False,
                "log_level": "ERROR"
            }
        },
        
        # Test data configuration
        "test_data": {
            "generate_mock_data": True,
            "mock_data_size": 1000,
            "preserve_test_data": False,
            "cleanup_after_tests": True,
            "seed": 42
        },
        
        # Performance test thresholds
        "performance_thresholds": {
            "api_response_time_ms": 200,
            "database_query_time_ms": 50,
            "memory_usage_mb": 512,
            "cpu_usage_percent": 80,
            "throughput_requests_per_second": 1000
        },
        
        # Coverage configuration
        "coverage": {
            "enabled": True,
            "min_coverage_percent": 80,
            "exclude_files": [
                "*/tests/*",
                "*/migrations/*",
                "*/__pycache__/*",
                "*/venv/*"
            ],
            "report_formats": ["html", "xml", "json"]
        },
        
        # Reporting configuration
        "reporting": {
            "enabled": True,
            "output_directory": "test_results",
            "formats": ["html", "json", "junit"],
            "include_screenshots": True,
            "include_logs": True,
            "dashboard_enabled": True
        }
    }
}

def create_test_runner(config: dict = None) -> TestRunner:
    """
    Create a configured test runner instance
    
    Args:
        config: Test runner configuration
        
    Returns:
        Configured TestRunner instance
    """
    if config is None:
        config = DEFAULT_CONFIG["testing"]
    
    return TestRunner(config)

def create_test_suite(
    name: str,
    category: str = "unit",
    config: dict = None
) -> TestSuite:
    """
    Create a test suite instance
    
    Args:
        name: Test suite name
        category: Test category
        config: Test suite configuration
        
    Returns:
        Configured TestSuite instance
    """
    if config is None:
        config = DEFAULT_CONFIG["testing"]
    
    return TestSuite(name, category, config)

def create_test_data_manager(config: dict = None) -> TestDataManager:
    """
    Create a test data manager instance
    
    Args:
        config: Test data manager configuration
        
    Returns:
        Configured TestDataManager instance
    """
    if config is None:
        config = DEFAULT_CONFIG["testing"]["test_data"]
    
    return TestDataManager(config)

# Export all components for easy access
__all__ = [
    # Core Test Framework
    "TestRunner",
    "TestSuite",
    "TestCase", 
    "TestResult",
    "TestStatus",
    "TestCategory",
    
    # Test Managers
    "UnitTestManager",
    "IntegrationTestManager", 
    "PerformanceTestManager",
    
    # Test Cases
    "DatabaseTestCase",
    "APITestCase",
    "ServiceTestCase",
    "UtilityTestCase",
    "ServiceIntegrationTest",
    "DatabaseIntegrationTest",
    "APIIntegrationTest",
    "WorkflowIntegrationTest",
    "LoadTestCase",
    "StressTestCase",
    "EnduranceTestCase",
    "ScalabilityTestCase",
    
    # Test Data & Utilities
    "TestDataManager",
    "TestDataGenerator",
    "MockDataProvider",
    "TestDatabase",
    "TestUtilities",
    "MockService",
    "TestHelpers",
    "AssertionHelpers",
    "TestFixtures",
    
    # Reporting
    "TestReportGenerator",
    "TestMetrics",
    "CoverageAnalyzer", 
    "TestDashboard",
    
    # Factory functions
    "create_test_runner",
    "create_test_suite",
    "create_test_data_manager",
    
    # Configuration
    "DEFAULT_CONFIG"
]