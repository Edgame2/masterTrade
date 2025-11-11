#!/usr/bin/env python3
"""
WebSocket Whale Alerts Test Client

Tests the WebSocket endpoint for real-time whale transaction alerts.
"""

import asyncio
import aiohttp
import json
from datetime import datetime

async def test_whale_alerts_websocket():
    """Test WebSocket whale alerts endpoint"""
    
    url = "ws://localhost:8000/ws/whale-alerts"
    api_key = "test_key"
    min_amount = 500000  # $500k minimum
    
    print("=" * 70)
    print("WebSocket Whale Alerts Test Client")
    print("=" * 70)
    print(f"URL: {url}")
    print(f"API Key: {api_key}")
    print(f"Min Amount: ${min_amount:,}")
    print("=" * 70)
    print()
    
    async with aiohttp.ClientSession() as session:
        try:
            # Connect to WebSocket
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecting to WebSocket...")
            async with session.ws_connect(
                f"{url}?api_key={api_key}&min_amount={min_amount}"
            ) as ws:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Connected successfully!")
                print()
                
                # Track message count
                msg_count = 0
                
                # Listen for messages
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        msg_count += 1
                        data = json.loads(msg.data)
                        msg_type = data.get('type')
                        timestamp = data.get('timestamp', 'N/A')
                        
                        if msg_type == 'connection_established':
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔗 Connection Established")
                            print(f"  Message: {data.get('message')}")
                            print(f"  Filters: {json.dumps(data.get('filters', {}), indent=2)}")
                            print()
                            
                            # Send a ping after connection
                            await ws.send_json({
                                "type": "ping"
                            })
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📤 Sent ping")
                            print()
                        
                        elif msg_type == 'pong':
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📥 Received pong")
                            print()
                            
                            # Test filter update after first pong
                            if msg_count == 2:
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔧 Updating filters...")
                                await ws.send_json({
                                    "type": "update_filters",
                                    "min_amount": 1000000,  # Increase to $1M
                                    "symbol": "BTC"  # Filter to BTC only
                                })
                                print()
                        
                        elif msg_type == 'filters_updated':
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Filters Updated")
                            print(f"  New Filters: {json.dumps(data.get('filters', {}), indent=2)}")
                            print()
                        
                        elif msg_type == 'whale_alert':
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🐋 WHALE ALERT!")
                            whale_data = data.get('data', {})
                            print(f"  Symbol: {whale_data.get('symbol')}")
                            print(f"  Amount: ${whale_data.get('amount_usd', 0):,.2f}")
                            print(f"  Type: {whale_data.get('transaction_type')}")
                            print(f"  From: {whale_data.get('from_entity', 'Unknown')}")
                            print(f"  To: {whale_data.get('to_entity', 'Unknown')}")
                            print(f"  Hash: {whale_data.get('transaction_hash', 'N/A')[:16]}...")
                            print(f"  TX Time: {whale_data.get('timestamp')}")
                            print()
                        
                        elif msg_type == 'error':
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error")
                            print(f"  Error: {data.get('error')}")
                            print()
                        
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📨 Unknown message type: {msg_type}")
                            print(f"  Data: {json.dumps(data, indent=2)}")
                            print()
                        
                        # After testing basic functionality, close connection
                        if msg_count >= 5:  # After 5 messages, disconnect
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Test complete. Disconnecting...")
                            await ws.close()
                            break
                    
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ WebSocket error")
                        break
                    
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connection closed")
                        break
                
                print()
                print("=" * 70)
                print(f"Test Summary: Received {msg_count} messages")
                print("=" * 70)
        
        except aiohttp.ClientConnectorError as e:
            print(f"❌ Connection Error: {e}")
            print("   Make sure market_data_service is running on port 8000")
        except Exception as e:
            print(f"❌ Error: {e}")


async def test_invalid_api_key():
    """Test with invalid API key"""
    url = "ws://localhost:8000/ws/whale-alerts"
    
    print("\n" + "=" * 70)
    print("Testing Invalid API Key")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        try:
            # Try to connect without API key
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempting connection without API key...")
            async with session.get(f"http://localhost:8000/ws/whale-alerts") as response:
                result = await response.json()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Correctly rejected")
                print(f"  Status: {response.status}")
                print(f"  Response: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("=" * 70)


async def test_long_running_connection():
    """Test long-running connection (listens for 30 seconds)"""
    url = "ws://localhost:8000/ws/whale-alerts"
    api_key = "test_key"
    
    print("\n" + "=" * 70)
    print("Testing Long-Running Connection (30 seconds)")
    print("=" * 70)
    print("Listening for whale alerts...")
    print("(Press Ctrl+C to stop early)")
    print("=" * 70)
    print()
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(
                f"{url}?api_key={api_key}&min_amount=500000"
            ) as ws:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Connected")
                
                # Set timeout
                start_time = asyncio.get_event_loop().time()
                timeout = 30  # 30 seconds
                
                alert_count = 0
                
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        msg_type = data.get('type')
                        
                        if msg_type == 'whale_alert':
                            alert_count += 1
                            whale_data = data.get('data', {})
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🐋 Alert #{alert_count}: "
                                  f"{whale_data.get('symbol')} "
                                  f"${whale_data.get('amount_usd', 0):,.2f} "
                                  f"({whale_data.get('transaction_type')})")
                    
                    # Check timeout
                    if asyncio.get_event_loop().time() - start_time > timeout:
                        print()
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏱️ Timeout reached")
                        await ws.close()
                        break
                
                print()
                print(f"Total whale alerts received: {alert_count}")
        
        except KeyboardInterrupt:
            print("\n\n⚠️ Interrupted by user")
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    print("=" * 70)


async def main():
    """Run all tests"""
    print("\n")
    print("🐋" * 35)
    print("WEBSOCKET WHALE ALERTS TEST SUITE")
    print("🐋" * 35)
    print()
    
    # Test 1: Basic functionality
    await test_whale_alerts_websocket()
    await asyncio.sleep(2)
    
    # Test 2: Invalid API key
    await test_invalid_api_key()
    await asyncio.sleep(2)
    
    # Test 3: Long-running connection (optional, comment out if not needed)
    # await test_long_running_connection()
    
    print("\n✅ All tests completed!")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Tests interrupted by user")
