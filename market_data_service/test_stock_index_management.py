#!/usr/bin/env python3
"""
Test script for database-driven stock index management functionality
"""

import asyncio
import sys
import json
from datetime import datetime

# Add the current directory to Python path
sys.path.append('.')

from database import Database
from models import SymbolTracking
from stock_index_collector import StockIndexDataCollector
from config import settings

async def test_stock_index_management():
    """Test all stock index management functionality"""
    
    print("📈 Testing Database-Driven Stock Index Management")
    print("=" * 55)
    
    # Initialize database
    db = Database()
    try:
        await db.connect()
        print("✅ Database connection established")
        
        # Test 1: Initialize default stock indices
        print("\n📊 Test 1: Initialize default stock indices")
        success = await db.initialize_default_stock_indices()
        print(f"Default stock indices initialized: {success}")
        
        # Test 2: Get all stock indices
        print("\n📊 Test 2: Get tracked stock indices")
        tracked_indices = await db.get_tracked_stock_indices()
        print(f"Tracked stock indices: {len(tracked_indices)}")
        for idx in tracked_indices[:5]:  # Show first 5
            print(f"  - {idx['symbol']} ({idx['base_asset']}) - {idx['quote_asset']} - Priority: {idx['priority']}")
        
        # Test 3: Get indices by category
        print("\n📊 Test 3: Get stock indices by category")
        categories = await db.get_stock_indices_by_category()
        print("Categories and indices:")
        for category, indices in categories.items():
            print(f"  {category}: {len(indices)} indices")
            if indices:
                print(f"    {', '.join(indices[:3])}{'...' if len(indices) > 3 else ''}")
        
        # Test 4: Add a new stock index
        print("\n📊 Test 4: Add new stock index")
        new_index = SymbolTracking(
            id="^KOSPI",
            symbol="^KOSPI",
            base_asset="KOSPI",
            quote_asset="KR",
            tracking=True,
            asset_type="stock_index",
            exchange="global_markets",
            priority=2,
            intervals=["1d"],
            notes="major korea index - Added via test script"
        )
        
        added = await db.add_symbol_tracking(new_index)
        print(f"New stock index ^KOSPI added: {added}")
        
        # Test 5: Update stock index metadata
        print("\n📊 Test 5: Update stock index metadata")
        if added:
            updated = await db.update_stock_index_metadata("^KOSPI", {
                "category": "international",
                "region": "south_korea",
                "full_name": "Korea Composite Stock Price Index",
                "priority": 1
            })
            print(f"Stock index ^KOSPI metadata updated: {updated}")
        
        # Test 6: Get regional indices
        print("\n📊 Test 6: Get US indices")
        us_indices = await db.get_tracked_stock_indices(region="us")
        print(f"US indices: {len(us_indices)}")
        us_symbols = [idx['symbol'] for idx in us_indices]
        print(f"US symbols: {', '.join(us_symbols)}")
        
        # Test 7: Test stock index collector with database
        print("\n📊 Test 7: Test stock index collector")
        collector = StockIndexDataCollector(db)
        await collector.connect()
        
        print(f"Collector loaded {len(collector.tracked_indices)} indices from database:")
        print(f"Tracked indices: {', '.join(collector.tracked_indices[:5])}{'...' if len(collector.tracked_indices) > 5 else ''}")
        
        print("Categories loaded:")
        for category, indices in collector.index_categories.items():
            print(f"  {category}: {len(indices)} indices")
        
        await collector.disconnect()
        
        # Test 8: Disable tracking for test index
        print("\n📊 Test 8: Disable tracking for test index")
        disabled = await db.set_symbol_tracking("^KOSPI", False)
        print(f"Tracking disabled for ^KOSPI: {disabled}")
        
        # Test 9: Check tracked indices after disabling
        print("\n📊 Test 9: Check tracked indices after disable")
        tracked_after = await db.get_tracked_stock_indices()
        kospi_tracked = any(idx['symbol'] == '^KOSPI' for idx in tracked_after)
        print(f"^KOSPI in tracked list after disable: {kospi_tracked}")
        print(f"Total tracked indices: {len(tracked_after)}")
        
        # Test 10: Remove test index (cleanup)
        print("\n📊 Test 10: Remove test index")
        removed = await db.remove_symbol_tracking("^KOSPI")
        print(f"Test index ^KOSPI removed: {removed}")
        
        print(f"\n✅ All stock index tests completed!")
        
        # Final summary
        final_tracked = await db.get_tracked_stock_indices()
        final_categories = await db.get_stock_indices_by_category()
        
        print(f"\n📈 Final Summary:")
        print(f"Total tracked stock indices: {len(final_tracked)}")
        print(f"Categories available: {', '.join(final_categories.keys())}")
        print("Stock indices ready for data collection:")
        for category, indices in final_categories.items():
            if indices:
                print(f"  {category}: {', '.join(indices)}")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Clean up database connection
        if hasattr(db, 'client') and db.client:
            await db.client.close()
        print("\n🔌 Database connection closed")

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_stock_index_management())