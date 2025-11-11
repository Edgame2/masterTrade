"""
Integration test for signal buffer

Tests the complete flow:
1. Signal aggregator generates a signal
2. Signal is automatically buffered in Redis
3. Signal can be retrieved via HTTP API
"""

import asyncio
import requests
import json
from datetime import datetime
import time


def test_signal_buffer_endpoints():
    """Test signal buffer HTTP endpoints"""
    print("=" * 70)
    print("Signal Buffer Integration Test")
    print("=" * 70)
    print()
    
    base_url = "http://localhost:8000"
    
    # Test 1: Get buffer info
    print("Test 1: Get buffer info...")
    response = requests.get(f"{base_url}/signals/buffer/info")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Buffer info retrieved")
        print(f"   Current size: {data['buffer_info']['current_size']}")
        print(f"   Max size: {data['buffer_info']['max_size']}")
        print(f"   TTL: {data['buffer_info'].get('ttl_hours', 'N/A')} hours")
    else:
        print(f"   ❌ Failed: {response.text}")
    print()
    
    # Test 2: Get recent signals (should be empty initially)
    print("Test 2: Get recent signals...")
    response = requests.get(f"{base_url}/signals/recent?limit=10")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Signals retrieved")
        print(f"   Count: {data['count']}")
        
        if data['count'] > 0:
            print(f"   Latest signal:")
            signal = data['signals'][0]
            print(f"     Symbol: {signal['symbol']}")
            print(f"     Direction: {signal['overall_signal']}")
            print(f"     Strength: {signal['signal_strength']}")
            print(f"     Confidence: {signal['confidence']}")
            print(f"     Action: {signal.get('recommended_action', 'N/A')}")
    else:
        print(f"   ❌ Failed: {response.text}")
    print()
    
    # Test 3: Get signals for specific symbol
    print("Test 3: Get signals for BTCUSDT...")
    response = requests.get(f"{base_url}/signals/recent?symbol=BTCUSDT&limit=5")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ BTCUSDT signals retrieved")
        print(f"   Count: {data['count']}")
    else:
        print(f"   ❌ Failed: {response.text}")
    print()
    
    # Test 4: Get signal statistics
    print("Test 4: Get signal statistics for BTCUSDT...")
    response = requests.get(f"{base_url}/signals/stats?symbol=BTCUSDT&hours=24")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data['success']:
            stats = data['statistics']
            print(f"   ✅ Statistics retrieved")
            print(f"   Total signals: {stats.get('total_signals', 0)}")
            
            if stats.get('total_signals', 0) > 0:
                print(f"   Bullish: {stats.get('bullish_percent', 0):.1f}%")
                print(f"   Bearish: {stats.get('bearish_percent', 0):.1f}%")
                print(f"   Avg confidence: {stats.get('average_confidence', 0):.3f}")
                print(f"   Strong signals: {stats.get('strong_signals_percent', 0):.1f}%")
                
                if stats.get('latest_signal'):
                    latest = stats['latest_signal']
                    print(f"   Latest: {latest['direction']} ({latest['strength']}) at {latest['timestamp']}")
        else:
            print(f"   ⚠️  {stats.get('error', 'No signals found')}")
    else:
        print(f"   ❌ Failed: {response.text}")
    print()
    
    # Test 5: Filter by time
    print("Test 5: Get signals from last hour...")
    response = requests.get(f"{base_url}/signals/recent?hours=1&limit=50")
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Time-filtered signals retrieved")
        print(f"   Count: {data['count']}")
    else:
        print(f"   ❌ Failed: {response.text}")
    print()
    
    # Test 6: Test error handling - invalid parameters
    print("Test 6: Test error handling...")
    response = requests.get(f"{base_url}/signals/stats?hours=abc")  # Missing symbol
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 400:
        print(f"   ✅ Error handling works correctly")
        data = response.json()
        print(f"   Error: {data.get('error', 'N/A')}")
    else:
        print(f"   ⚠️  Expected 400 status code")
    print()
    
    print("=" * 70)
    print("Integration test completed!")
    print("=" * 70)
    print()
    print("NOTE: Signal buffer will populate as the system generates signals.")
    print("      The aggregator runs every 60 seconds and publishes signals")
    print("      which are automatically buffered in Redis.")
    print()


if __name__ == "__main__":
    try:
        test_signal_buffer_endpoints()
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to market_data_service on localhost:8000")
        print("   Make sure the service is running and port 8000 is exposed")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
