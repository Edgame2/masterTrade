#!/usr/bin/env python3
"""
Test script for database-driven symbol management functionality
"""

import asyncio
import sys
import json
from datetime import datetime

# Add the current directory to Python path
sys.path.append('.')

from database import Database
from models import SymbolTracking
from config import settings

async def test_symbol_management():
    """Test all symbol management functionality"""
    
    print("🚀 Testing Database-Driven Symbol Management")
    print("=" * 50)
    
    # Initialize database
    db = Database()
    try:
        await db.connect()
        print("✅ Database connection established")
        
        # Test 1: Initialize default symbols
        print("\n📊 Test 1: Initialize default symbols")
        success = await db.initialize_default_symbols()
        print(f"Default symbols initialized: {success}")
        
        # Test 2: Get all symbols
        print("\n📊 Test 2: Get all symbols")
        all_symbols = await db.get_all_symbols(include_inactive=True)
        print(f"Total symbols in database: {len(all_symbols)}")
        for symbol in all_symbols[:5]:  # Show first 5
            print(f"  - {symbol['symbol']} (tracking: {symbol['tracking']})")
        
        # Test 3: Get only tracked symbols
        print("\n📊 Test 3: Get tracked symbols")
        tracked_symbols = await db.get_tracked_symbols(asset_type="crypto", exchange="binance")
        print(f"Tracked crypto symbols: {len(tracked_symbols)}")
        tracked_list = [s['symbol'] for s in tracked_symbols]
        print(f"Symbols: {', '.join(tracked_list)}")
        
        # Test 4: Add a new symbol
        print("\n📊 Test 4: Add new symbol")
        new_symbol = SymbolTracking(
            id="DOGEUSDC",
            symbol="DOGEUSDC", 
            base_asset="DOGE",
            quote_asset="USDC",
            tracking=True,
            asset_type="crypto",
            exchange="binance",
            priority=2,
            notes="Added via test script"
        )
        
        added = await db.add_symbol_tracking(new_symbol)
        print(f"New symbol DOGEUSDC added: {added}")
        
        # Test 5: Update symbol tracking
        print("\n📊 Test 5: Update symbol tracking") 
        if added:
            updated = await db.update_symbol_tracking("DOGEUSDC", {
                "priority": 1,
                "notes": "Updated priority via test"
            })
            print(f"Symbol DOGEUSDC updated: {updated}")
        
        # Test 6: Disable tracking for a symbol
        print("\n📊 Test 6: Disable tracking")
        disabled = await db.set_symbol_tracking("DOGEUSDC", False)
        print(f"Tracking disabled for DOGEUSDC: {disabled}")
        
        # Test 7: Check tracked symbols after disabling
        print("\n📊 Test 7: Check tracked symbols after disable")
        tracked_symbols_after = await db.get_tracked_symbols(asset_type="crypto")
        tracked_list_after = [s['symbol'] for s in tracked_symbols_after]
        print(f"Tracked symbols now: {len(tracked_symbols_after)}")
        print(f"DOGEUSDC in tracked list: {'DOGEUSDC' in tracked_list_after}")
        
        # Test 8: Re-enable tracking
        print("\n📊 Test 8: Re-enable tracking")
        enabled = await db.set_symbol_tracking("DOGEUSDC", True)
        print(f"Tracking re-enabled for DOGEUSDC: {enabled}")
        
        # Test 9: Get symbol info
        print("\n📊 Test 9: Get symbol info")
        symbol_info = await db.get_symbol_tracking_info("DOGEUSDC")
        if symbol_info:
            print(f"Symbol info: {symbol_info['symbol']}")
            print(f"  - Base: {symbol_info['base_asset']}")
            print(f"  - Quote: {symbol_info['quote_asset']}")
            print(f"  - Tracking: {symbol_info['tracking']}")
            print(f"  - Priority: {symbol_info['priority']}")
            print(f"  - Notes: {symbol_info['notes']}")
        
        # Test 10: Remove symbol (cleanup)
        print("\n📊 Test 10: Remove test symbol")
        removed = await db.remove_symbol_tracking("DOGEUSDC")
        print(f"Test symbol DOGEUSDC removed: {removed}")
        
        print(f"\n✅ All tests completed!")
        
        # Final summary
        final_tracked = await db.get_tracked_symbols(asset_type="crypto")
        print(f"\n📈 Final Summary:")
        print(f"Total tracked symbols: {len(final_tracked)}")
        print(f"Symbols ready for data collection: {', '.join([s['symbol'] for s in final_tracked])}")
        
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
    asyncio.run(test_symbol_management())