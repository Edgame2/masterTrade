# WebSocket Whale Alerts API Documentation

## Overview

The WebSocket Whale Alerts API provides real-time push notifications for large cryptocurrency transactions (whale movements). This enables applications to monitor significant market-moving events as they happen.

**WebSocket URL**: `ws://localhost:8000/ws/whale-alerts`

**Protocol**: WebSocket (RFC 6455)

**Authentication**: API key via query parameter

**Update Frequency**: Real-time (broadcasts within 10 seconds of detection)

## Connection

### Endpoint

```
ws://localhost:8000/ws/whale-alerts?api_key=YOUR_API_KEY&min_amount=1000000&symbol=BTC
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| api_key | string | Yes | - | Authentication API key |
| min_amount | float | No | 1000000 | Minimum transaction amount in USD |
| symbol | string | No | all | Filter by specific cryptocurrency (e.g., BTC, ETH) |

### Authentication

API keys can be obtained from the service administrator. For testing/development, the following keys are accepted:
- `test_key`
- `admin_key`
- `whale_watcher`

**Production**: API keys should be validated against a secure database.

### Connection Lifecycle

1. **Client Connects**: Client initiates WebSocket connection with API key
2. **Server Validates**: Server validates API key and filters
3. **Confirmation Sent**: Server sends `connection_established` message
4. **Real-Time Updates**: Server pushes `whale_alert` messages as transactions occur
5. **Keepalive**: Client can send `ping` messages; server responds with `pong`
6. **Filter Updates**: Client can update filters without reconnecting
7. **Disconnect**: Either side can close the connection

## Message Types

### 1. Connection Established (Server → Client)

Sent immediately after successful connection.

```json
{
  "type": "connection_established",
  "message": "Connected to whale alerts stream",
  "filters": {
    "min_amount": 1000000,
    "symbol": "all"
  },
  "timestamp": "2025-11-11T14:00:00Z"
}
```

### 2. Whale Alert (Server → Client)

Broadcast when a whale transaction is detected.

```json
{
  "type": "whale_alert",
  "data": {
    "transaction_hash": "0x1234567890abcdef...",
    "symbol": "BTC",
    "amount": 150.5,
    "amount_usd": 1500000.50,
    "from_address": "0xabcd...",
    "to_address": "0xef12...",
    "from_entity": "Binance",
    "to_entity": "Unknown Wallet",
    "transaction_type": "exchange_outflow",
    "blockchain": "Bitcoin",
    "timestamp": "2025-11-11T14:00:00Z",
    "block_number": 750123,
    "confirmations": 6
  },
  "timestamp": "2025-11-11T14:00:01Z"
}
```

**Transaction Types**:
- `exchange_inflow`: Tokens moving into an exchange
- `exchange_outflow`: Tokens moving out of an exchange
- `large_transfer`: Large transfer between wallets
- `unknown`: Transaction type not determined

### 3. Ping/Pong (Client ↔ Server)

Client sends ping to keep connection alive; server responds with pong.

**Client Request**:
```json
{
  "type": "ping"
}
```

**Server Response**:
```json
{
  "type": "pong",
  "timestamp": "2025-11-11T14:00:00Z"
}
```

### 4. Update Filters (Client → Server)

Client can update filters without reconnecting.

**Client Request**:
```json
{
  "type": "update_filters",
  "min_amount": 2000000,
  "symbol": "ETH"
}
```

**Server Response**:
```json
{
  "type": "filters_updated",
  "filters": {
    "min_amount": 2000000,
    "symbol": "ETH"
  },
  "timestamp": "2025-11-11T14:00:00Z"
}
```

### 5. Error (Server → Client)

Sent when an error occurs.

```json
{
  "type": "error",
  "error": "Invalid message type: unknown_type",
  "timestamp": "2025-11-11T14:00:00Z"
}
```

## Integration Examples

### Python (using websockets)

```python
import asyncio
import websockets
import json

async def whale_alerts_listener():
    url = "ws://localhost:8000/ws/whale-alerts"
    api_key = "test_key"
    min_amount = 1000000  # $1M
    
    uri = f"{url}?api_key={api_key}&min_amount={min_amount}"
    
    async with websockets.connect(uri) as websocket:
        print("Connected to whale alerts stream")
        
        # Listen for messages
        async for message in websocket:
            data = json.loads(message)
            
            if data["type"] == "whale_alert":
                whale = data["data"]
                print(f"🐋 Whale Alert: {whale['symbol']} "
                      f"${whale['amount_usd']:,.2f} "
                      f"({whale['transaction_type']})")
                print(f"   From: {whale['from_entity']}")
                print(f"   To: {whale['to_entity']}")
                print(f"   Hash: {whale['transaction_hash'][:16]}...")
            
            elif data["type"] == "connection_established":
                print(f"✅ {data['message']}")
                print(f"   Filters: {data['filters']}")
                
                # Send ping to test connection
                await websocket.send(json.dumps({"type": "ping"}))
            
            elif data["type"] == "pong":
                print("📥 Pong received")

# Run the listener
asyncio.run(whale_alerts_listener())
```

### Python (using aiohttp)

```python
import asyncio
import aiohttp
import json

async def whale_alerts_listener():
    url = "ws://localhost:8000/ws/whale-alerts"
    api_key = "test_key"
    
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            f"{url}?api_key={api_key}&min_amount=1000000"
        ) as ws:
            print("Connected to whale alerts")
            
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    if data["type"] == "whale_alert":
                        whale = data["data"]
                        print(f"🐋 {whale['symbol']}: ${whale['amount_usd']:,.2f}")
                    
                    elif data["type"] == "connection_established":
                        print("✅ Connected successfully")
                        
                        # Update filters dynamically
                        await ws.send_json({
                            "type": "update_filters",
                            "min_amount": 2000000,
                            "symbol": "BTC"
                        })
                
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"WebSocket error: {ws.exception()}")
                    break

asyncio.run(whale_alerts_listener())
```

### JavaScript/Node.js (using ws)

```javascript
const WebSocket = require('ws');

const url = 'ws://localhost:8000/ws/whale-alerts';
const apiKey = 'test_key';
const minAmount = 1000000;

const ws = new WebSocket(`${url}?api_key=${apiKey}&min_amount=${minAmount}`);

ws.on('open', () => {
  console.log('✅ Connected to whale alerts stream');
  
  // Send ping to test connection
  ws.send(JSON.stringify({ type: 'ping' }));
});

ws.on('message', (data) => {
  const message = JSON.parse(data);
  
  switch (message.type) {
    case 'connection_established':
      console.log(`📡 ${message.message}`);
      console.log('Filters:', message.filters);
      break;
    
    case 'whale_alert':
      const whale = message.data;
      console.log(`🐋 Whale Alert: ${whale.symbol} $${whale.amount_usd.toLocaleString()}`);
      console.log(`   Type: ${whale.transaction_type}`);
      console.log(`   From: ${whale.from_entity} → To: ${whale.to_entity}`);
      break;
    
    case 'pong':
      console.log('📥 Pong received');
      break;
    
    case 'error':
      console.error(`❌ Error: ${message.error}`);
      break;
  }
});

ws.on('error', (error) => {
  console.error('WebSocket error:', error);
});

ws.on('close', () => {
  console.log('❌ Disconnected from whale alerts stream');
});

// Update filters after 10 seconds
setTimeout(() => {
  ws.send(JSON.stringify({
    type: 'update_filters',
    min_amount: 2000000,
    symbol: 'ETH'
  }));
}, 10000);
```

### JavaScript/Browser

```html
<!DOCTYPE html>
<html>
<head>
  <title>Whale Alerts Monitor</title>
  <style>
    #alerts { font-family: monospace; }
    .whale-alert { color: #00ff00; margin: 10px 0; }
  </style>
</head>
<body>
  <h1>🐋 Whale Alerts Monitor</h1>
  <div id="status">Connecting...</div>
  <div id="alerts"></div>

  <script>
    const url = 'ws://localhost:8000/ws/whale-alerts';
    const apiKey = 'test_key';
    const minAmount = 1000000;
    
    const ws = new WebSocket(`${url}?api_key=${apiKey}&min_amount=${minAmount}`);
    const statusEl = document.getElementById('status');
    const alertsEl = document.getElementById('alerts');
    
    ws.onopen = () => {
      statusEl.textContent = '✅ Connected';
      statusEl.style.color = 'green';
    };
    
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      if (message.type === 'whale_alert') {
        const whale = message.data;
        const alertDiv = document.createElement('div');
        alertDiv.className = 'whale-alert';
        alertDiv.innerHTML = `
          <strong>🐋 ${whale.symbol}</strong>: 
          $${whale.amount_usd.toLocaleString()} 
          (${whale.transaction_type})<br>
          From: ${whale.from_entity} → To: ${whale.to_entity}<br>
          <small>${new Date(whale.timestamp).toLocaleString()}</small>
        `;
        alertsEl.prepend(alertDiv);
      }
    };
    
    ws.onerror = (error) => {
      statusEl.textContent = '❌ Error';
      statusEl.style.color = 'red';
      console.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
      statusEl.textContent = '❌ Disconnected';
      statusEl.style.color = 'red';
    };
  </script>
</body>
</html>
```

## Error Handling

### Common Errors

**Missing API Key**:
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "success": false,
  "error": "API key is required. Use ?api_key=YOUR_KEY"
}
```

**Invalid Message Format**:
```json
{
  "type": "error",
  "error": "Invalid JSON",
  "timestamp": "2025-11-11T14:00:00Z"
}
```

**Unknown Message Type**:
```json
{
  "type": "error",
  "error": "Unknown message type: invalid_type",
  "timestamp": "2025-11-11T14:00:00Z"
}
```

### Reconnection Strategy

Implement exponential backoff for reconnections:

```python
import asyncio
import websockets

async def connect_with_retry(url, max_retries=5):
    retry_delay = 1  # Start with 1 second
    
    for attempt in range(max_retries):
        try:
            async with websockets.connect(url) as ws:
                print(f"Connected (attempt {attempt + 1})")
                # Handle messages
                async for message in ws:
                    process_message(message)
        
        except websockets.ConnectionClosed:
            print(f"Connection closed, retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)  # Max 60 seconds
        
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
    
    print("Max retries reached")
```

## Performance Characteristics

- **Latency**: Alerts broadcast within 10 seconds of detection
- **Throughput**: Supports 100+ concurrent connections
- **Message Size**: Typical message ~500-1000 bytes
- **Keepalive**: Optional ping/pong every 30-60 seconds recommended

## Security Considerations

1. **API Key Validation**: Always validate API keys against secure storage
2. **Rate Limiting**: Implement per-client rate limits (e.g., 1000 connections/hour)
3. **TLS/SSL**: Use `wss://` in production for encrypted connections
4. **Input Validation**: Validate all client messages to prevent injection attacks
5. **Connection Limits**: Limit concurrent connections per API key

## Monitoring & Metrics

The service exposes Prometheus metrics:

- `websocket_connections`: Number of active WebSocket connections
- `whale_alerts_sent_total`: Total number of whale alerts broadcast
- `websocket_errors_total`: Total WebSocket errors

## Use Cases

### Trading Bots
Monitor whale movements to adjust trading strategies:
```python
if whale["transaction_type"] == "exchange_inflow" and whale["amount_usd"] > 5000000:
    # Large deposit to exchange - possible sell pressure
    execute_defensive_strategy()
```

### Alert Systems
Send notifications to users when whales move:
```python
if whale["symbol"] == user_watching and whale["amount_usd"] > user_threshold:
    send_telegram_notification(user, whale)
```

### Analytics Dashboards
Display real-time whale activity:
```javascript
if (message.type === 'whale_alert') {
  updateDashboard(message.data);
  playAlertSound();
}
```

## FAQ

**Q: How are whale transactions detected?**  
A: Transactions are collected from multiple on-chain data providers (Moralis, Etherscan, etc.) and filtered by amount.

**Q: What is the typical delay between transaction and alert?**  
A: Approximately 5-15 seconds, depending on blockchain confirmation times and data provider latency.

**Q: Can I filter by multiple symbols?**  
A: Currently only single symbol filtering is supported. Use `symbol=all` to receive alerts for all cryptocurrencies.

**Q: What happens if I lose connection?**  
A: Implement reconnection logic with exponential backoff. Missed alerts during disconnection are not replayed.

**Q: Is there a message history?**  
A: No, WebSocket provides real-time streaming only. Use REST API endpoints to query historical whale transactions.

## Support

For issues or questions:
- Check service logs: `docker logs mastertrade_market_data`
- Test connection: Use included test client `test_websocket_whale_alerts.py`
- Verify service health: `curl http://localhost:8000/health`

---

**Version**: 1.0  
**Last Updated**: November 11, 2025
