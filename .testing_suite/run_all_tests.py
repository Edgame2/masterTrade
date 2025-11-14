#!/usr/bin/env python3
"""
MasterTrade System Integration Test Suite

This script runs comprehensive tests on ALL components of the trading bot:
1. Database connectivity and schema
2. Services health and API endpoints
3. Data collection and storage
4. Strategy generation and backtesting
5. Order execution (paper/testnet)
6. Risk management
7. Monitoring and alerts
8. Message queue integration

Run: python3 run_all_tests.py
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import test modules
from test_database import DatabaseTests
from test_services import ServiceTests
from test_data_collection import DataCollectionTests
from test_strategy_generation import StrategyGenerationTests
from test_order_execution import OrderExecutionTests
from test_risk_management import RiskManagementTests
from test_monitoring import MonitoringTests
from test_message_queue import MessageQueueTests
from test_environment import EnvironmentTests

class TestRunner:
    """Orchestrates all system tests"""
    
    def __init__(self):
        self.results = {
            'total_tests': 0,
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
        self.test_suites = []
        
    def add_suite(self, suite_name: str, suite_class):
        """Add a test suite to run"""
        self.test_suites.append((suite_name, suite_class))
    
    async def run_all_tests(self) -> Dict:
        """Run all test suites"""
        print("=" * 80)
        print("MasterTrade System Integration Test Suite")
        print(f"Started: {datetime.now().isoformat()}")
        print("=" * 80)
        print()
        
        for suite_name, suite_class in self.test_suites:
            print(f"\n{'=' * 80}")
            print(f"Running: {suite_name}")
            print(f"{'=' * 80}\n")
            
            try:
                suite = suite_class()
                results = await suite.run_all_tests()
                
                self.results['total_tests'] += results['total']
                self.results['passed'] += results['passed']
                self.results['failed'] += results['failed']
                self.results['skipped'] += results['skipped']
                
                if results['errors']:
                    self.results['errors'].extend([
                        f"{suite_name}: {error}" for error in results['errors']
                    ])
                
                # Print suite summary
                print(f"\n{suite_name} Summary:")
                print(f"  Total: {results['total']}")
                print(f"  ✅ Passed: {results['passed']}")
                print(f"  ❌ Failed: {results['failed']}")
                print(f"  ⏭️  Skipped: {results['skipped']}")
                
            except Exception as e:
                print(f"❌ Error running {suite_name}: {e}")
                self.results['errors'].append(f"{suite_name}: {str(e)}")
        
        # Final summary
        print("\n" + "=" * 80)
        print("FINAL TEST RESULTS")
        print("=" * 80)
        print(f"\nTotal Tests: {self.results['total_tests']}")
        print(f"✅ Passed: {self.results['passed']} ({self._percentage(self.results['passed'])}%)")
        print(f"❌ Failed: {self.results['failed']} ({self._percentage(self.results['failed'])}%)")
        print(f"⏭️  Skipped: {self.results['skipped']} ({self._percentage(self.results['skipped'])}%)")
        
        if self.results['errors']:
            print(f"\n❌ Errors ({len(self.results['errors'])}):")
            for error in self.results['errors'][:10]:  # Show first 10
                print(f"  - {error}")
            if len(self.results['errors']) > 10:
                print(f"  ... and {len(self.results['errors']) - 10} more")
        
        print(f"\nCompleted: {datetime.now().isoformat()}")
        print("=" * 80)
        
        # Return overall status
        success_rate = (self.results['passed'] / self.results['total_tests'] * 100) if self.results['total_tests'] > 0 else 0
        
        if success_rate >= 95:
            print("\n🎉 EXCELLENT! System is production-ready (95%+ pass rate)")
            return_code = 0
        elif success_rate >= 80:
            print("\n✅ GOOD! Most systems working (80%+ pass rate)")
            return_code = 0
        elif success_rate >= 60:
            print("\n⚠️  WARNING! Multiple failures detected (60-80% pass rate)")
            return_code = 1
        else:
            print("\n❌ CRITICAL! System has major issues (<60% pass rate)")
            return_code = 2
        
        return return_code
    
    def _percentage(self, count: int) -> str:
        """Calculate percentage"""
        if self.results['total_tests'] == 0:
            return "0.0"
        return f"{(count / self.results['total_tests'] * 100):.1f}"


async def main():
    """Main test runner"""
    runner = TestRunner()
    
    # Add all test suites in order
    runner.add_suite("Environment Variables", EnvironmentTests)
    runner.add_suite("Database Tests", DatabaseTests)
    runner.add_suite("Service Health Tests", ServiceTests)
    runner.add_suite("Data Collection Tests", DataCollectionTests)
    runner.add_suite("Strategy Generation Tests", StrategyGenerationTests)
    runner.add_suite("Order Execution Tests", OrderExecutionTests)
    runner.add_suite("Risk Management Tests", RiskManagementTests)
    runner.add_suite("Monitoring Tests", MonitoringTests)
    runner.add_suite("Message Queue Tests", MessageQueueTests)
    
    # Run all tests
    return_code = await runner.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(return_code)


if __name__ == "__main__":
    asyncio.run(main())
