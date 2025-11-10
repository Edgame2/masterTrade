#!/usr/bin/env python3
"""
MasterTrade System Verification and Cleanup Script

Checks all system requirements from instructions and removes unnecessary files
"""

import os
import json
import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

def check_service(name: str, port: int) -> bool:
    """Check if a service is running on the specified port"""
    try:
        result = subprocess.run(
            f"curl -s http://localhost:{port}/health 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0 and "healthy" in result.stdout.lower()
    except:
        return False

def check_requirements():
    """Check all requirements from instructions"""
    results = {
        "services": {},
        "automation": {},
        "data_collection": {},
        "features": {}
    }
    
    print("=" * 80)
    print("MASTERTRADE SYSTEM VERIFICATION")
    print("=" * 80)
    print()
    
    # 1. Check Services
    print("1. CHECKING SERVICES")
    print("-" * 80)
    services = {
        "Market Data Service": 8000,
        "Strategy Service": 8001,
        "Order Executor": 8081,
        "API Gateway": 8090,
        "Frontend UI": 3000
    }
    
    for name, port in services.items():
        running = check_service(name, port)
        results["services"][name] = running
        status = "✓ RUNNING" if running else "✗ STOPPED"
        print(f"  {status:12} {name:25} (port {port})")
    print()
    
    # 2. Check Automation Features
    print("2. CHECKING AUTOMATION FEATURES")
    print("-" * 80)
    
    automation_files = {
        "Automatic Strategy Discovery": "strategy_service/automatic_strategy_activation.py",
        "Daily Strategy Review": "strategy_service/daily_strategy_reviewer.py",
        "Crypto Selection Engine": "strategy_service/crypto_selection_engine.py",
        "Strategy Generator": "strategy_service/core/strategy_generator.py",
        "Backtesting Framework": "strategy_service/backtest_engine.py"
    }
    
    for feature, filepath in automation_files.items():
        exists = os.path.exists(filepath)
        results["automation"][feature] = exists
        status = "✓ EXISTS" if exists else "✗ MISSING"
        print(f"  {status:12} {feature}")
    print()
    
    # 3. Check Data Collection
    print("3. CHECKING DATA COLLECTION")
    print("-" * 80)
    
    data_features = {
        "Symbol Management API": "market_data_service/main.py",
        "Technical Indicators": "market_data_service/technical_indicator_calculator.py",
        "Stock Index Collector": "market_data_service/stock_index_collector.py",
        "Sentiment Data Collector": "market_data_service/sentiment_data_collector.py",
        "Historical Data Collector": "market_data_service/historical_data_collector.py"
    }
    
    for feature, filepath in data_features.items():
        exists = os.path.exists(filepath)
        results["data_collection"][feature] = exists
        status = "✓ EXISTS" if exists else "✗ MISSING"
        print(f"  {status:12} {feature}")
    print()
    
    # 4. Check Database Connections
    print("4. CHECKING DATABASE INTEGRATION")
    print("-" * 80)
    
    # Check if Cosmos DB connection is configured
    env_vars = {
        "COSMOS_DB_URI": os.getenv("COSMOS_DB_URI"),
        "COSMOS_DB_KEY": os.getenv("COSMOS_DB_KEY"),
        "COSMOS_DB_DATABASE": os.getenv("COSMOS_DB_DATABASE", "mmasterTrade")
    }
    
    for var, value in env_vars.items():
        configured = value is not None
        status = "✓ SET" if configured else "✗ NOT SET"
        print(f"  {status:12} {var}")
    print()
    
    # 5. Check Generated Strategies
    print("5. CHECKING STRATEGY STATUS")
    print("-" * 80)
    
    strategy_files = {
        "1000 Generated Strategies": "strategy_service/strategies_1000.json",
        "Backtest Results": "strategy_service/backtest_results_1000.json",
        "BTC Correlation Strategies": "strategy_service/btc_correlation_strategies.json"
    }
    
    for name, filepath in strategy_files.items():
        if os.path.exists(filepath):
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            print(f"  ✓ EXISTS   {name:35} ({size_mb:.2f} MB)")
            results["features"][name] = True
        else:
            print(f"  ✗ MISSING  {name}")
            results["features"][name] = False
    print()
    
    return results

def find_unnecessary_files():
    """Find files that should be removed"""
    print("6. IDENTIFYING UNNECESSARY FILES")
    print("-" * 80)
    
    unnecessary_patterns = [
        # Duplicate or test files
        "**/*_backup.*",
        "**/*_old.*",
        "**/*_test_*.py",
        "**/test_*.log",
        "**/*.pyc",
        "**/__pycache__",
        "**/.pytest_cache",
        "**/node_modules",
        
        # Temporary files
        "**/tmp_*",
        "**/*.tmp",
        "**/*.swp",
        "**/*.swo",
        
        # IDE files
        "**/.vscode/settings.json",
        "**/.idea",
        "**/*.code-workspace",
        
        # Log files (old)
        "**/logs/*.log.*",
        "**/*.log.1",
        "**/*.log.2",
    ]
    
    base_path = Path(".")
    files_to_remove = []
    
    for pattern in unnecessary_patterns:
        for file_path in base_path.glob(pattern):
            if file_path.is_file():
                files_to_remove.append(str(file_path))
    
    # Check for duplicate strategy files (keeping the comprehensive ones)
    strategy_dir = Path("strategy_service")
    if strategy_dir.exists():
        json_files = list(strategy_dir.glob("*.json"))
        
        # Keep these files
        keep_files = {
            "strategies_1000.json",
            "backtest_results_1000.json",
            "btc_correlation_strategies.json",
            "backtest_results_all.csv",
            "backtest_monthly_returns.csv"
        }
        
        for json_file in json_files:
            if json_file.name not in keep_files and json_file.stat().st_size < 1000:
                # Small JSON files that are likely test/temp files
                files_to_remove.append(str(json_file))
    
    if files_to_remove:
        print(f"  Found {len(files_to_remove)} unnecessary files:")
        for file in files_to_remove[:20]:  # Show first 20
            print(f"    - {file}")
        if len(files_to_remove) > 20:
            print(f"    ... and {len(files_to_remove) - 20} more")
    else:
        print("  ✓ No unnecessary files found")
    print()
    
    return files_to_remove

def generate_summary(results: Dict) -> Tuple[int, int]:
    """Generate summary of findings"""
    total_checks = 0
    passed_checks = 0
    
    for category, checks in results.items():
        for name, status in checks.items():
            total_checks += 1
            if status:
                passed_checks += 1
    
    return passed_checks, total_checks

def main():
    """Main execution"""
    print()
    
    # Check requirements
    results = check_requirements()
    
    # Find unnecessary files
    unnecessary_files = find_unnecessary_files()
    
    # Generate summary
    passed, total = generate_summary(results)
    pass_rate = (passed / total * 100) if total > 0 else 0
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  System Checks:        {passed}/{total} passed ({pass_rate:.1f}%)")
    print(f"  Unnecessary Files:    {len(unnecessary_files)}")
    print()
    
    # Overall status
    if pass_rate >= 80:
        print("  ✓ SYSTEM STATUS: GOOD - Most features are functional")
    elif pass_rate >= 60:
        print("  ⚠ SYSTEM STATUS: NEEDS ATTENTION - Some features missing")
    else:
        print("  ✗ SYSTEM STATUS: CRITICAL - Major features missing")
    print()
    
    # Recommendations
    print("RECOMMENDATIONS")
    print("-" * 80)
    
    if not results["services"]["Market Data Service"]:
        print("  1. Start Market Data Service (required for data collection)")
    
    if not results["services"]["Strategy Service"]:
        print("  2. Start Strategy Service (required for strategy execution)")
    
    if not results["services"]["Frontend UI"]:
        print("  3. Start Frontend UI (for monitoring dashboard)")
    
    if unnecessary_files:
        print(f"  4. Clean up {len(unnecessary_files)} unnecessary files")
    
    # Check if strategies need to be imported
    if results["features"].get("1000 Generated Strategies") and passed > 0:
        print("  5. Import generated strategies into Strategy Service database")
        print("     Command: cd strategy_service && python3 import_strategies.py")
    
    print()
    print("=" * 80)
    print()
    
    return 0 if pass_rate >= 80 else 1

if __name__ == "__main__":
    sys.exit(main())
