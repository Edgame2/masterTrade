#!/usr/bin/env python3
"""
Manual Crypto Selection Runner

Triggers the cryptocurrency selection process to find the best cryptos to trade.
This will also trigger automatic historical data download for selected cryptos.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import structlog
from datetime import datetime

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger()

async def run_crypto_selection():
    """Run the cryptocurrency selection process"""
    
    print("\n" + "="*70)
    print("🚀 STARTING CRYPTOCURRENCY SELECTION PROCESS")
    print("="*70 + "\n")
    
    try:
        # Import after path is set
    from postgres_database import Database
        from crypto_selection_engine import CryptoSelectionEngine
        
        # Initialize database
        print("📦 Initializing database connection...")
        database = Database()
        await database.connect()
        print("✓ Database connected\n")
        
        # Initialize crypto selection engine
        print("🔧 Initializing crypto selection engine...")
        engine = CryptoSelectionEngine(database)
        print("✓ Engine initialized\n")
        
        # Run selection
        print("🔍 Analyzing cryptocurrencies to find best trading opportunities...")
        print("   This may take a few minutes...\n")
        
        selected_cryptos = await engine.run_daily_selection()
        
        # Display results
        print("\n" + "="*70)
        print("✅ CRYPTOCURRENCY SELECTION COMPLETE")
        print("="*70 + "\n")
        
        if selected_cryptos:
            print(f"📊 Selected {len(selected_cryptos)} cryptocurrencies for trading:\n")
            
            for i, crypto in enumerate(selected_cryptos, 1):
                print(f"{i}. {crypto.symbol}")
                print(f"   Score: {crypto.score:.2f}/100")
                print(f"   Volatility: {crypto.volatility_score:.1f}")
                print(f"   Volume: {crypto.volume_score:.1f}")
                print(f"   Momentum: {crypto.momentum_score:.1f}")
                print(f"   Technical: {crypto.technical_score:.1f}")
                print(f"   Reason: {crypto.selection_reason}")
                print()
            
            print("="*70)
            print("📈 NEXT STEPS:")
            print("="*70)
            print("✓ Historical data download triggered automatically")
            print("✓ Data will be stored in PostgreSQL")
            print("✓ Strategies can now use this data for backtesting")
            print("✓ Trading can begin once data is available")
            print()
            
        else:
            print("⚠️  No cryptocurrencies selected.")
            print("   This could mean:")
            print("   - Market conditions don't meet criteria")
            print("   - Insufficient data available")
            print("   - All cryptos failed risk assessment")
            print()
        
        # Cleanup
        await database.disconnect()
        print("✓ Database disconnected\n")
        
    except ImportError as e:
        print(f"\n❌ Import Error: {e}")
        print("\nMake sure you're running from the strategy_service directory:")
        print("  cd strategy_service")
        print("  ./venv/bin/python run_crypto_selection.py")
        print()
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Error during crypto selection: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def check_current_selections():
    """Check what cryptos are currently selected"""
    
    print("\n" + "="*70)
    print("📋 CHECKING CURRENT CRYPTOCURRENCY SELECTIONS")
    print("="*70 + "\n")
    
    try:
    from postgres_database import Database
        from crypto_selection_engine import CryptoSelectionEngine
        
        database = Database()
        await database.connect()
        
        engine = CryptoSelectionEngine(database)
        selections = await engine.get_current_selections()
        
        if selections:
            print(f"Current selections from: {selections.get('selection_date', 'Unknown')}")
            print(f"Total selected: {selections.get('total_selected', 0)}\n")
            
            for crypto in selections.get('selected_cryptos', []):
                print(f"  • {crypto.get('symbol', 'Unknown')}")
                print(f"    Score: {crypto.get('score', 0):.2f}")
                print(f"    Reason: {crypto.get('selection_reason', 'N/A')}")
                print()
        else:
            print("No current selections found.")
            print("Run: ./venv/bin/python run_crypto_selection.py --run")
            print()
        
        await database.disconnect()
        
    except Exception as e:
        print(f"Error checking selections: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Cryptocurrency Selection Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run crypto selection process
  ./venv/bin/python run_crypto_selection.py --run
  
  # Check current selections
  ./venv/bin/python run_crypto_selection.py --check
  
  # Run with custom settings (future enhancement)
  ./venv/bin/python run_crypto_selection.py --run --max-selections 15
        """
    )
    
    parser.add_argument('--run', action='store_true',
                       help='Run the cryptocurrency selection process')
    parser.add_argument('--check', action='store_true',
                       help='Check current selections')
    
    args = parser.parse_args()
    
    if args.check:
        asyncio.run(check_current_selections())
    elif args.run:
        asyncio.run(run_crypto_selection())
    else:
        # Default: run selection
        print("No action specified. Running crypto selection...")
        print("Use --help for options\n")
        asyncio.run(run_crypto_selection())
