"""
Comprehensive test runner with support for unit, integration, and performance tests.

Provides flexible test execution with parallel processing, detailed reporting,
and comprehensive test management capabilities.
"""

import asyncio
import time
import logging
import traceback
import json
import multiprocessing
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union, Set
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import concurrent.futures
import importlib
import inspect
import sys

try:
    import pytest
    import coverage
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False
    logging.warning("pytest and coverage not available")

logger = logging.getLogger(__name__)

class TestStatus(Enum):
    """Test execution status"""
    PENDING = "pending"
    RUNNING = "running" 
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"

class TestCategory(Enum):
    """Test category types"""
    UNIT = "unit"
    INTEGRATION = "integration"
    PERFORMANCE = "performance"
    SECURITY = "security"
    API = "api"
    E2E = "e2e"

@dataclass
class TestResult:
    """Test execution result"""
    test_id: str
    name: str
    category: TestCategory
    status: TestStatus
    duration_seconds: float
    error_message: Optional[str] = None
    traceback: Optional[str] = None
    assertions: int = 0
    output: str = ""
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            **asdict(self),
            "category": self.category.value,
            "status": self.status.value,
            "success": self.status == TestStatus.PASSED
        }

@dataclass
class TestCase:
    """Test case definition"""
    test_id: str
    name: str
    category: TestCategory
    description: str
    test_function: Callable
    setup_function: Optional[Callable] = None
    teardown_function: Optional[Callable] = None
    timeout_seconds: int = 60
    retry_attempts: int = 1
    tags: Set[str] = None
    dependencies: List[str] = None
    enabled: bool = True
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = set()
        if self.dependencies is None:
            self.dependencies = []

class TestSuite:
    """
    Test suite containing multiple test cases
    
    Manages test organization, execution order, and dependencies.
    """
    
    def __init__(self, name: str, category: TestCategory, config: dict):
        self.name = name
        self.category = category
        self.config = config
        self.test_cases: Dict[str, TestCase] = {}
        self.setup_function: Optional[Callable] = None
        self.teardown_function: Optional[Callable] = None
        
        # Execution tracking
        self.results: Dict[str, TestResult] = {}
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
    
    def add_test_case(self, test_case: TestCase):
        """Add test case to suite"""
        self.test_cases[test_case.test_id] = test_case
        logger.debug(f"Added test case {test_case.test_id} to suite {self.name}")
    
    def remove_test_case(self, test_id: str) -> bool:
        """Remove test case from suite"""
        if test_id in self.test_cases:
            del self.test_cases[test_id]
            return True
        return False
    
    def get_execution_order(self) -> List[str]:
        """Get test execution order considering dependencies"""
        
        # Simple topological sort for dependency resolution
        visited = set()
        temp_visited = set()
        execution_order = []
        
        def visit(test_id: str):
            if test_id in temp_visited:
                raise ValueError(f"Circular dependency detected involving {test_id}")
            
            if test_id not in visited:
                temp_visited.add(test_id)
                
                test_case = self.test_cases.get(test_id)
                if test_case:
                    # Visit dependencies first
                    for dep_id in test_case.dependencies:
                        if dep_id in self.test_cases:
                            visit(dep_id)
                
                temp_visited.remove(test_id)
                visited.add(test_id)
                execution_order.append(test_id)
        
        # Process all test cases
        for test_id in self.test_cases.keys():
            if test_id not in visited:
                visit(test_id)
        
        return execution_order
    
    def get_statistics(self) -> dict:
        """Get test suite statistics"""
        
        total_tests = len(self.test_cases)
        executed_tests = len(self.results)
        
        status_counts = {}
        for status in TestStatus:
            status_counts[status.value] = sum(
                1 for result in self.results.values() 
                if result.status == status
            )
        
        duration = 0
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
        
        return {
            "suite_name": self.name,
            "category": self.category.value,
            "total_tests": total_tests,
            "executed_tests": executed_tests,
            "status_counts": status_counts,
            "duration_seconds": duration,
            "success_rate": (
                status_counts.get("passed", 0) / executed_tests * 100 
                if executed_tests > 0 else 0
            )
        }

class TestRunner:
    """
    Comprehensive test runner with parallel execution and reporting
    
    Provides flexible test execution with support for multiple test categories,
    parallel processing, and detailed result reporting.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.test_suites: Dict[str, TestSuite] = {}
        self.global_setup: Optional[Callable] = None
        self.global_teardown: Optional[Callable] = None
        
        # Execution settings
        self.parallel_execution = config.get("parallel_execution", True)
        self.max_workers = config.get("max_workers", multiprocessing.cpu_count())
        self.timeout_seconds = config.get("timeout_seconds", 300)
        self.retry_attempts = config.get("retry_attempts", 3)
        self.fail_fast = config.get("fail_fast", False)
        
        # Results tracking
        self.execution_start_time: Optional[datetime] = None
        self.execution_end_time: Optional[datetime] = None
        self.all_results: Dict[str, TestResult] = {}
        
        # Coverage tracking
        self.coverage_tracker = None
        if config.get("coverage", {}).get("enabled", True):
            self._setup_coverage()
    
    def _setup_coverage(self):
        """Setup code coverage tracking"""
        try:
            import coverage as cov
            
            coverage_config = self.config.get("coverage", {})
            
            self.coverage_tracker = cov.Coverage(
                source=["."],
                omit=coverage_config.get("exclude_files", [])
            )
            
            logger.info("Code coverage tracking enabled")
            
        except ImportError:
            logger.warning("Coverage package not available")
    
    def add_test_suite(self, test_suite: TestSuite):
        """Add test suite to runner"""
        self.test_suites[test_suite.name] = test_suite
        logger.info(f"Added test suite: {test_suite.name}")
    
    def discover_tests(self, test_directory: str = "tests") -> int:
        """
        Discover and load test cases from directory
        
        Args:
            test_directory: Directory to scan for tests
            
        Returns:
            Number of tests discovered
        """
        
        test_path = Path(test_directory)
        if not test_path.exists():
            logger.warning(f"Test directory {test_directory} not found")
            return 0
        
        discovered_count = 0
        
        # Scan for Python test files
        for test_file in test_path.rglob("test_*.py"):
            try:
                # Import test module
                module_name = test_file.stem
                spec = importlib.util.spec_from_file_location(module_name, test_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Extract test functions
                for name, obj in inspect.getmembers(module):
                    if (inspect.isfunction(obj) and 
                        name.startswith("test_") and 
                        hasattr(obj, "__call__")):
                        
                        # Determine category from file path
                        category = TestCategory.UNIT
                        if "integration" in str(test_file):
                            category = TestCategory.INTEGRATION
                        elif "performance" in str(test_file):
                            category = TestCategory.PERFORMANCE
                        elif "api" in str(test_file):
                            category = TestCategory.API
                        
                        # Create test case
                        test_case = TestCase(
                            test_id=f"{module_name}.{name}",
                            name=name,
                            category=category,
                            description=obj.__doc__ or f"Test function {name}",
                            test_function=obj,
                            timeout_seconds=self.timeout_seconds
                        )
                        
                        # Add to appropriate suite
                        suite_name = f"{category.value}_tests"
                        if suite_name not in self.test_suites:
                            self.test_suites[suite_name] = TestSuite(
                                suite_name, category, self.config
                            )
                        
                        self.test_suites[suite_name].add_test_case(test_case)
                        discovered_count += 1
                
            except Exception as e:
                logger.error(f"Failed to load tests from {test_file}: {e}")
        
        logger.info(f"Discovered {discovered_count} test cases")
        return discovered_count
    
    async def run_test_case(
        self, 
        test_case: TestCase, 
        suite_name: str
    ) -> TestResult:
        """
        Execute a single test case
        
        Args:
            test_case: Test case to execute
            suite_name: Name of containing test suite
            
        Returns:
            Test execution result
        """
        
        start_time = time.time()
        
        result = TestResult(
            test_id=test_case.test_id,
            name=test_case.name,
            category=test_case.category,
            status=TestStatus.RUNNING,
            duration_seconds=0,
            metadata={"suite": suite_name}
        )
        
        if not test_case.enabled:
            result.status = TestStatus.SKIPPED
            result.error_message = "Test case disabled"
            return result
        
        try:
            # Setup
            if test_case.setup_function:
                await self._run_function_with_timeout(
                    test_case.setup_function, 
                    test_case.timeout_seconds
                )
            
            # Execute test with retry logic
            for attempt in range(max(1, test_case.retry_attempts)):
                try:
                    # Run test function
                    await self._run_function_with_timeout(
                        test_case.test_function,
                        test_case.timeout_seconds
                    )
                    
                    result.status = TestStatus.PASSED
                    break
                    
                except AssertionError as e:
                    result.status = TestStatus.FAILED
                    result.error_message = str(e)
                    result.traceback = traceback.format_exc()
                    
                    if attempt < test_case.retry_attempts - 1:
                        logger.warning(f"Test {test_case.test_id} failed, retrying (attempt {attempt + 1})")
                        await asyncio.sleep(1)  # Brief delay before retry
                    else:
                        break
                        
                except Exception as e:
                    result.status = TestStatus.ERROR
                    result.error_message = str(e)
                    result.traceback = traceback.format_exc()
                    break
            
            # Teardown
            if test_case.teardown_function:
                try:
                    await self._run_function_with_timeout(
                        test_case.teardown_function,
                        test_case.timeout_seconds
                    )
                except Exception as e:
                    logger.warning(f"Teardown failed for {test_case.test_id}: {e}")
        
        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = f"Test execution error: {e}"
            result.traceback = traceback.format_exc()
        
        finally:
            result.duration_seconds = time.time() - start_time
        
        return result
    
    async def _run_function_with_timeout(self, func: Callable, timeout: int):
        """Run function with timeout"""
        
        if inspect.iscoroutinefunction(func):
            # Async function
            await asyncio.wait_for(func(), timeout=timeout)
        else:
            # Sync function - run in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, func)
    
    async def run_test_suite(self, suite_name: str) -> Dict[str, TestResult]:
        """
        Execute all tests in a suite
        
        Args:
            suite_name: Name of test suite to run
            
        Returns:
            Dictionary of test results
        """
        
        suite = self.test_suites.get(suite_name)
        if not suite:
            logger.error(f"Test suite {suite_name} not found")
            return {}
        
        logger.info(f"Running test suite: {suite_name}")
        suite.start_time = datetime.now()
        
        try:
            # Suite setup
            if suite.setup_function:
                await suite.setup_function()
            
            # Get execution order
            execution_order = suite.get_execution_order()
            
            if self.parallel_execution and len(execution_order) > 1:
                # Parallel execution
                results = await self._run_tests_parallel(suite, execution_order)
            else:
                # Sequential execution
                results = await self._run_tests_sequential(suite, execution_order)
            
            # Update suite results
            suite.results.update(results)
            
            # Suite teardown
            if suite.teardown_function:
                try:
                    await suite.teardown_function()
                except Exception as e:
                    logger.error(f"Suite teardown failed for {suite_name}: {e}")
        
        except Exception as e:
            logger.error(f"Test suite {suite_name} execution failed: {e}")
            
            # Mark all tests as error
            for test_id in suite.test_cases:
                results[test_id] = TestResult(
                    test_id=test_id,
                    name=suite.test_cases[test_id].name,
                    category=suite.category,
                    status=TestStatus.ERROR,
                    duration_seconds=0,
                    error_message=f"Suite execution error: {e}"
                )
        
        finally:
            suite.end_time = datetime.now()
        
        return suite.results
    
    async def _run_tests_parallel(
        self, 
        suite: TestSuite, 
        execution_order: List[str]
    ) -> Dict[str, TestResult]:
        """Run tests in parallel where possible"""
        
        results = {}
        
        # Group tests by dependency level
        dependency_levels = self._group_by_dependency_level(suite, execution_order)
        
        for level_tests in dependency_levels:
            if len(level_tests) == 1:
                # Single test - run directly
                test_id = level_tests[0]
                test_case = suite.test_cases[test_id]
                result = await self.run_test_case(test_case, suite.name)
                results[test_id] = result
                
                # Check fail fast
                if self.fail_fast and result.status in [TestStatus.FAILED, TestStatus.ERROR]:
                    logger.info("Fail fast enabled, stopping execution")
                    break
            else:
                # Multiple tests - run in parallel
                tasks = []
                for test_id in level_tests:
                    test_case = suite.test_cases[test_id]
                    task = asyncio.create_task(
                        self.run_test_case(test_case, suite.name)
                    )
                    tasks.append((test_id, task))
                
                # Wait for all tasks in this level
                for test_id, task in tasks:
                    try:
                        result = await task
                        results[test_id] = result
                        
                        # Check fail fast
                        if self.fail_fast and result.status in [TestStatus.FAILED, TestStatus.ERROR]:
                            logger.info("Fail fast enabled, cancelling remaining tasks")
                            
                            # Cancel remaining tasks
                            for remaining_id, remaining_task in tasks:
                                if not remaining_task.done():
                                    remaining_task.cancel()
                            
                            return results
                            
                    except asyncio.CancelledError:
                        results[test_id] = TestResult(
                            test_id=test_id,
                            name=suite.test_cases[test_id].name,
                            category=suite.category,
                            status=TestStatus.SKIPPED,
                            duration_seconds=0,
                            error_message="Test cancelled due to fail fast"
                        )
        
        return results
    
    async def _run_tests_sequential(
        self, 
        suite: TestSuite, 
        execution_order: List[str]
    ) -> Dict[str, TestResult]:
        """Run tests sequentially"""
        
        results = {}
        
        for test_id in execution_order:
            test_case = suite.test_cases[test_id]
            result = await self.run_test_case(test_case, suite.name)
            results[test_id] = result
            
            # Check fail fast
            if self.fail_fast and result.status in [TestStatus.FAILED, TestStatus.ERROR]:
                logger.info("Fail fast enabled, stopping execution")
                break
        
        return results
    
    def _group_by_dependency_level(
        self, 
        suite: TestSuite, 
        execution_order: List[str]
    ) -> List[List[str]]:
        """Group tests by dependency level for parallel execution"""
        
        dependency_levels = []
        processed = set()
        
        for test_id in execution_order:
            test_case = suite.test_cases[test_id]
            
            # Find appropriate level
            level_index = 0
            for dep_id in test_case.dependencies:
                if dep_id in processed:
                    # Find level of dependency
                    for i, level in enumerate(dependency_levels):
                        if dep_id in level:
                            level_index = max(level_index, i + 1)
                            break
            
            # Ensure we have enough levels
            while len(dependency_levels) <= level_index:
                dependency_levels.append([])
            
            # Add to appropriate level
            dependency_levels[level_index].append(test_id)
            processed.add(test_id)
        
        return dependency_levels
    
    async def run_all_tests(
        self, 
        categories: List[str] = None,
        suites: List[str] = None,
        tags: Set[str] = None
    ) -> Dict[str, Dict[str, TestResult]]:
        """
        Run all or filtered tests
        
        Args:
            categories: Test categories to run
            suites: Specific test suites to run
            tags: Test tags to filter by
            
        Returns:
            Dictionary of suite results
        """
        
        self.execution_start_time = datetime.now()
        
        # Start coverage tracking
        if self.coverage_tracker:
            self.coverage_tracker.start()
        
        try:
            # Global setup
            if self.global_setup:
                await self.global_setup()
            
            # Filter test suites
            suites_to_run = []
            
            for suite_name, suite in self.test_suites.items():
                # Filter by category
                if categories and suite.category.value not in categories:
                    continue
                
                # Filter by suite name
                if suites and suite_name not in suites:
                    continue
                
                # Filter by tags
                if tags:
                    suite_has_tags = False
                    for test_case in suite.test_cases.values():
                        if tags.intersection(test_case.tags):
                            suite_has_tags = True
                            break
                    
                    if not suite_has_tags:
                        continue
                
                suites_to_run.append(suite_name)
            
            logger.info(f"Running {len(suites_to_run)} test suites")
            
            # Run test suites
            all_suite_results = {}
            
            for suite_name in suites_to_run:
                try:
                    suite_results = await self.run_test_suite(suite_name)
                    all_suite_results[suite_name] = suite_results
                    self.all_results.update(suite_results)
                    
                    logger.info(f"Completed test suite: {suite_name}")
                    
                except Exception as e:
                    logger.error(f"Failed to run test suite {suite_name}: {e}")
            
            # Global teardown
            if self.global_teardown:
                try:
                    await self.global_teardown()
                except Exception as e:
                    logger.error(f"Global teardown failed: {e}")
            
            return all_suite_results
        
        finally:
            # Stop coverage tracking
            if self.coverage_tracker:
                self.coverage_tracker.stop()
                self.coverage_tracker.save()
            
            self.execution_end_time = datetime.now()
    
    def get_test_statistics(self) -> dict:
        """Get comprehensive test execution statistics"""
        
        total_tests = len(self.all_results)
        
        status_counts = {}
        for status in TestStatus:
            status_counts[status.value] = sum(
                1 for result in self.all_results.values() 
                if result.status == status
            )
        
        duration = 0
        if self.execution_start_time and self.execution_end_time:
            duration = (self.execution_end_time - self.execution_start_time).total_seconds()
        
        # Suite statistics
        suite_stats = {}
        for suite_name, suite in self.test_suites.items():
            suite_stats[suite_name] = suite.get_statistics()
        
        # Coverage statistics
        coverage_stats = {}
        if self.coverage_tracker:
            try:
                coverage_stats = {
                    "total_coverage": self.coverage_tracker.report(),
                    "missing_lines": len(self.coverage_tracker.get_data().missing_arcs())
                }
            except Exception as e:
                logger.warning(f"Failed to get coverage statistics: {e}")
        
        return {
            "execution_summary": {
                "total_tests": total_tests,
                "status_counts": status_counts,
                "duration_seconds": duration,
                "success_rate": (
                    status_counts.get("passed", 0) / total_tests * 100 
                    if total_tests > 0 else 0
                ),
                "started_at": self.execution_start_time.isoformat() if self.execution_start_time else None,
                "completed_at": self.execution_end_time.isoformat() if self.execution_end_time else None
            },
            "suite_statistics": suite_stats,
            "coverage_statistics": coverage_stats,
            "configuration": {
                "parallel_execution": self.parallel_execution,
                "max_workers": self.max_workers,
                "timeout_seconds": self.timeout_seconds,
                "fail_fast": self.fail_fast
            }
        }
    
    def export_results(self, output_path: str, format: str = "json"):
        """Export test results to file"""
        
        results_data = {
            "statistics": self.get_test_statistics(),
            "results": [result.to_dict() for result in self.all_results.values()]
        }
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        if format.lower() == "json":
            with open(output_file, 'w') as f:
                json.dump(results_data, f, indent=2, default=str)
        
        elif format.lower() == "junit":
            # Generate JUnit XML format
            self._export_junit_xml(results_data, output_file)
        
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        logger.info(f"Test results exported to {output_file}")
    
    def _export_junit_xml(self, results_data: dict, output_file: Path):
        """Export results in JUnit XML format"""
        
        try:
            import xml.etree.ElementTree as ET
            
            # Create root element
            testsuites = ET.Element("testsuites")
            
            # Group results by suite
            suite_results = {}
            for result in results_data["results"]:
                suite_name = result.get("metadata", {}).get("suite", "unknown")
                if suite_name not in suite_results:
                    suite_results[suite_name] = []
                suite_results[suite_name].append(result)
            
            # Create testsuite elements
            for suite_name, results in suite_results.items():
                testsuite = ET.SubElement(testsuites, "testsuite")
                testsuite.set("name", suite_name)
                testsuite.set("tests", str(len(results)))
                
                failures = sum(1 for r in results if r["status"] == "failed")
                errors = sum(1 for r in results if r["status"] == "error")
                skipped = sum(1 for r in results if r["status"] == "skipped")
                
                testsuite.set("failures", str(failures))
                testsuite.set("errors", str(errors))
                testsuite.set("skipped", str(skipped))
                
                total_time = sum(r["duration_seconds"] for r in results)
                testsuite.set("time", str(total_time))
                
                # Create testcase elements
                for result in results:
                    testcase = ET.SubElement(testsuite, "testcase")
                    testcase.set("name", result["name"])
                    testcase.set("classname", result["test_id"])
                    testcase.set("time", str(result["duration_seconds"]))
                    
                    if result["status"] == "failed":
                        failure = ET.SubElement(testcase, "failure")
                        failure.set("message", result.get("error_message", ""))
                        failure.text = result.get("traceback", "")
                    
                    elif result["status"] == "error":
                        error = ET.SubElement(testcase, "error")
                        error.set("message", result.get("error_message", ""))
                        error.text = result.get("traceback", "")
                    
                    elif result["status"] == "skipped":
                        skipped_elem = ET.SubElement(testcase, "skipped")
                        skipped_elem.set("message", result.get("error_message", ""))
            
            # Write XML file
            tree = ET.ElementTree(testsuites)
            tree.write(output_file, encoding="utf-8", xml_declaration=True)
            
        except Exception as e:
            logger.error(f"Failed to export JUnit XML: {e}")
            raise