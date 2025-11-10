#!/usr/bin/env python3
"""
Macro-Economic Data Collection - Quick Test Script

Tests the macro-economic data collector by fetching a sample of data from each source.
"""

import asyncio
import sys
sys.path.append('/home/neodyme/Documents/Projects/masterTrade/market_data_service')

from database import Database
from macro_economic_collector import MacroEconomicCollector


async def test_macro_collector():
    """Test the macro-economic data collector"""
    print("=" * 60)
    print("Testing Macro-Economic Data Collector")
    print("=" * 60)
    print()
    
    database = Database()
    
    async with database, MacroEconomicCollector(database) as collector:
        print("✓ Database and collector initialized\n")
        
        # Test commodities
        print("Testing Commodities Collection...")
        commodities = await collector.fetch_commodities_data()
        print(f"  ✓ Collected {len(commodities)} commodity prices")
        if commodities:
            print(f"    Example: {commodities[0]['name']} = ${commodities[0]['current_value']:.2f}")
        print()
        
        # Test currencies
        print("Testing Currencies Collection...")
        currencies = await collector.fetch_currencies_data()
        print(f"  ✓ Collected {len(currencies)} currency pairs")
        if currencies:
            print(f"    Example: {currencies[0]['name']} = {currencies[0]['current_value']:.4f}")
        print()
        
        # Test treasury yields
        print("Testing Treasury Yields Collection...")
        treasuries = await collector.fetch_treasury_yields()
        print(f"  ✓ Collected {len(treasuries)} treasury yields")
        if treasuries:
            print(f"    Example: {treasuries[0]['name']} = {treasuries[0]['current_yield']:.3f}%")
        print()
        
        # Test FRED (if API key is set)
        print("Testing FRED Indicators Collection...")
        fred_data = await collector.fetch_fred_indicators()
        if fred_data:
            print(f"  ✓ Collected {len(fred_data)} FRED indicators")
            print(f"    Example: {fred_data[0]['name']} = {fred_data[0]['current_value']}")
        else:
            print("  ℹ FRED API key not configured (optional)")
        print()
        
        # Test Fear & Greed Index
        print("Testing Fear & Greed Index Collection...")
        fear_greed = await collector.fetch_crypto_fear_greed_index()
        if fear_greed:
            print(f"  ✓ Fear & Greed Index: {fear_greed['value']} ({fear_greed['classification']})")
        else:
            print("  ✗ Failed to fetch Fear & Greed Index")
        print()
        
        # Get macro summary
        print("Generating Macro-Economic Summary...")
        summary = await collector.get_macro_summary()
        if summary and "error" not in summary:
            print(f"  ✓ Risk Environment: {summary.get('risk_environment')}")
            print(f"  ✓ Market Sentiment: {summary.get('market_sentiment')}")
            if summary.get('key_indicators'):
                print("  ✓ Key Indicators:")
                for key, value in summary['key_indicators'].items():
                    if isinstance(value, dict):
                        print(f"    - {key}: {value.get('value', 'N/A')} ({value.get('trend', 'N/A')})")
                    else:
                        print(f"    - {key}: {value}")
        print()
        
        print("=" * 60)
        print("Test completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(test_macro_collector())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
