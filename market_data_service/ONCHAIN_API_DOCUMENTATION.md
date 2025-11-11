# On-Chain Data Query API Documentation

## Overview

The On-Chain Data Query API provides REST endpoints for querying blockchain data including whale transactions, on-chain metrics, and wallet information.

**Base URL**: `http://localhost:8000/api/v1/onchain`

## Endpoints

### 1. Query Whale Transactions

Query large cryptocurrency transactions (whale movements).

**Endpoint**: `GET /api/v1/onchain/whale-transactions`

**Query Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | string | No | None | Filter by cryptocurrency symbol (e.g., 'BTC', 'ETH') |
| `hours` | integer | No | 24 | Hours of history to retrieve |
| `min_amount` | float | No | None | Minimum transaction amount in USD |
| `limit` | integer | No | 100 | Maximum number of results to return |

**Response**:
```json
{
  "success": true,
  "data": [
    {
      "tx_hash": "0xabc123...",
      "symbol": "BTC",
      "amount": 1500.5,
      "amount_usd": 1500.5,
      "from_address": "0x123...",
      "to_address": "0x456...",
      "from_entity": "Binance",
      "to_entity": "Unknown",
      "transaction_type": "exchange_outflow",
      "timestamp": "2025-11-11T10:30:00Z",
      "block_number": 12345678,
      "blockchain": "ethereum"
    }
  ],
  "count": 3,
  "summary": {
    "total_volume_usd": 4235.0,
    "average_amount_usd": 1411.67,
    "largest_transaction": {
      "amount": 1500.5,
      "symbol": "BTC",
      "tx_hash": "0xabc123..."
    },
    "by_type": {
      "exchange_inflows": 5,
      "exchange_outflows": 3,
      "large_transfers": 2
    }
  },
  "filters": {
    "symbol": "BTC",
    "hours": 24,
    "min_amount": null,
    "limit": 100
  },
  "timestamp": "2025-11-11T12:00:00Z"
}
```

**Examples**:
```bash
# Get all whale transactions from last 24 hours
curl "http://localhost:8000/api/v1/onchain/whale-transactions"

# Get BTC whale transactions from last week
curl "http://localhost:8000/api/v1/onchain/whale-transactions?symbol=BTC&hours=168"

# Get transactions larger than $1M
curl "http://localhost:8000/api/v1/onchain/whale-transactions?min_amount=1000000&limit=10"
```

**Transaction Types**:
- `exchange_inflow`: Transfer into an exchange wallet
- `exchange_outflow`: Transfer out of an exchange wallet
- `large_transfer`: Large transfer between wallets

---

### 2. Get On-Chain Metrics by Symbol

Retrieve on-chain metrics for a specific cryptocurrency.

**Endpoint**: `GET /api/v1/onchain/metrics/{symbol}`

**Path Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Cryptocurrency symbol (e.g., 'BTC', 'ETH') |

**Query Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `metric_name` | string | No | None | Specific metric to retrieve (nvt, mvrv, exchange_flow, etc.) |
| `hours` | integer | No | 24 | Hours of history to retrieve |
| `limit` | integer | No | 100 | Maximum number of data points |

**Response**:
```json
{
  "success": true,
  "symbol": "BTC",
  "data": [
    {
      "metric_name": "nvt",
      "symbol": "BTC",
      "value": 95.5,
      "unit": "ratio",
      "timestamp": "2025-11-11T08:35:40Z",
      "source": "glassnode",
      "metadata": {
        "description": "Network Value to Transactions Ratio"
      }
    },
    {
      "metric_name": "mvrv",
      "symbol": "BTC",
      "value": 2.15,
      "unit": "ratio",
      "timestamp": "2025-11-11T08:35:40Z",
      "source": "glassnode",
      "metadata": {
        "description": "Market Value to Realized Value"
      }
    }
  ],
  "count": 2,
  "latest_metrics": {
    "nvt": {
      "value": 95.5,
      "timestamp": "2025-11-11T08:35:40Z",
      "unit": "ratio",
      "data_points": 1
    },
    "mvrv": {
      "value": 2.15,
      "timestamp": "2025-11-11T08:35:40Z",
      "unit": "ratio",
      "data_points": 1
    }
  },
  "available_metrics": ["nvt", "mvrv", "exchange_flow", "active_addresses"],
  "filters": {
    "metric_name": null,
    "hours": 24,
    "limit": 100
  },
  "timestamp": "2025-11-11T12:00:00Z"
}
```

**Available Metrics**:
- `nvt`: Network Value to Transactions ratio
- `mvrv`: Market Value to Realized Value ratio
- `exchange_flow`: Net flow into/out of exchanges (positive = inflow)
- `exchange_balance`: Total balance held on exchanges
- `active_addresses`: Number of unique active addresses
- `transaction_count`: Daily transaction count
- `hash_rate`: Network hash rate (Bitcoin)
- `difficulty`: Mining difficulty
- `supply`: Circulating supply

**Examples**:
```bash
# Get all metrics for BTC from last 24 hours
curl "http://localhost:8000/api/v1/onchain/metrics/BTC"

# Get only NVT ratio for BTC from last week
curl "http://localhost:8000/api/v1/onchain/metrics/BTC?metric_name=nvt&hours=168"

# Get Ethereum metrics
curl "http://localhost:8000/api/v1/onchain/metrics/ETH?hours=72"
```

---

### 3. Get Wallet Information

Retrieve information about a specific blockchain wallet address.

**Endpoint**: `GET /api/v1/onchain/wallet/{address}`

**Path Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `address` | string | Yes | Wallet address (Ethereum format: 0x...) |

**Query Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `include_transactions` | boolean | No | false | Include recent transactions |
| `tx_limit` | integer | No | 10 | Number of recent transactions to include |

**Response** (without transactions):
```json
{
  "success": true,
  "address": "0x1234567890123456789012345678901234567890",
  "label": "Binance Hot Wallet",
  "category": "exchange",
  "is_labeled": true,
  "metadata": {
    "exchange": "Binance",
    "wallet_type": "hot",
    "verified": true,
    "added_date": "2024-01-15"
  },
  "timestamp": "2025-11-11T12:00:00Z"
}
```

**Response** (with transactions):
```json
{
  "success": true,
  "address": "0x1234567890123456789012345678901234567890",
  "label": "Binance Hot Wallet",
  "category": "exchange",
  "is_labeled": true,
  "metadata": {
    "exchange": "Binance",
    "wallet_type": "hot"
  },
  "transactions": {
    "recent": [
      {
        "tx_hash": "0xabc123...",
        "symbol": "ETH",
        "amount": 50.5,
        "from_address": "0x1234...",
        "to_address": "0x5678...",
        "timestamp": "2025-11-11T10:30:00Z"
      }
    ],
    "count": 5,
    "summary": {
      "total_sent_usd": 125000.50,
      "total_received_usd": 230000.75,
      "net_flow_usd": 105000.25
    }
  },
  "timestamp": "2025-11-11T12:00:00Z"
}
```

**Wallet Categories**:
- `exchange`: Exchange wallet (Binance, Coinbase, etc.)
- `whale`: Known whale wallet
- `dex`: Decentralized exchange
- `defi`: DeFi protocol
- `bridge`: Cross-chain bridge
- `mining_pool`: Mining pool wallet
- `custodian`: Institutional custodian
- `unknown`: Unlabeled wallet

**Examples**:
```bash
# Get basic wallet information
curl "http://localhost:8000/api/v1/onchain/wallet/0x1234567890123456789012345678901234567890"

# Get wallet info with recent transactions
curl "http://localhost:8000/api/v1/onchain/wallet/0x1234567890123456789012345678901234567890?include_transactions=true"

# Get wallet info with last 20 transactions
curl "http://localhost:8000/api/v1/onchain/wallet/0x1234567890123456789012345678901234567890?include_transactions=true&tx_limit=20"
```

---

## Error Responses

All endpoints return errors in a consistent format:

```json
{
  "success": false,
  "error": "Error message description"
}
```

**Common HTTP Status Codes**:
- `200`: Success
- `400`: Bad Request (invalid parameters)
- `404`: Not Found (endpoint doesn't exist)
- `500`: Internal Server Error

**Example Error Responses**:

Invalid wallet address:
```json
{
  "success": false,
  "error": "Invalid wallet address format. Expected Ethereum address (0x...)"
}
```

Missing required parameter:
```json
{
  "success": false,
  "error": "Symbol is required"
}
```

Invalid parameter value:
```json
{
  "success": false,
  "error": "Invalid parameter value: invalid literal for int() with base 10: 'abc'"
}
```

---

## Rate Limiting

API endpoints are subject to rate limiting:
- **Rate Limit**: 60 requests per minute per IP
- **Burst Limit**: 10 requests per second

Rate limit information is included in response headers:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 55
X-RateLimit-Reset: 1699723200
```

---

## Data Freshness

- **Whale Transactions**: Real-time (updated within 1-5 minutes)
- **On-Chain Metrics**: Updated every 1-4 hours depending on metric
- **Wallet Labels**: Updated periodically

---

## Legacy Endpoints (Backward Compatibility)

The following legacy endpoints are still supported but may be deprecated:

- `GET /onchain/whales` → Use `/api/v1/onchain/whale-transactions`
- `GET /onchain/metrics` → Use `/api/v1/onchain/metrics/{symbol}`
- `GET /onchain/collectors/health` → Use `/health/collectors`

---

## Integration Examples

### Python

```python
import requests

base_url = "http://localhost:8000/api/v1/onchain"

# Get whale transactions for BTC
response = requests.get(
    f"{base_url}/whale-transactions",
    params={
        "symbol": "BTC",
        "hours": 24,
        "limit": 10
    }
)

if response.json()["success"]:
    transactions = response.json()["data"]
    for tx in transactions:
        print(f"Amount: {tx['amount']} {tx['symbol']}")

# Get on-chain metrics for ETH
response = requests.get(f"{base_url}/metrics/ETH")
if response.json()["success"]:
    metrics = response.json()["latest_metrics"]
    print(f"NVT Ratio: {metrics.get('nvt', {}).get('value')}")

# Get wallet information
address = "0x1234567890123456789012345678901234567890"
response = requests.get(
    f"{base_url}/wallet/{address}",
    params={"include_transactions": True}
)
if response.json()["success"]:
    wallet = response.json()
    print(f"Label: {wallet['label']}, Category: {wallet['category']}")
```

### JavaScript/Node.js

```javascript
const axios = require('axios');

const baseURL = 'http://localhost:8000/api/v1/onchain';

// Get whale transactions
async function getWhaleTransactions() {
  const response = await axios.get(`${baseURL}/whale-transactions`, {
    params: {
      symbol: 'BTC',
      hours: 24,
      limit: 10
    }
  });
  
  if (response.data.success) {
    console.log(`Found ${response.data.count} transactions`);
    console.log(`Total volume: $${response.data.summary.total_volume_usd}`);
  }
}

// Get on-chain metrics
async function getMetrics(symbol) {
  const response = await axios.get(`${baseURL}/metrics/${symbol}`);
  
  if (response.data.success) {
    const metrics = response.data.latest_metrics;
    console.log(`NVT Ratio: ${metrics.nvt?.value}`);
    console.log(`MVRV Ratio: ${metrics.mvrv?.value}`);
  }
}

// Get wallet info
async function getWalletInfo(address) {
  const response = await axios.get(`${baseURL}/wallet/${address}`, {
    params: {
      include_transactions: true,
      tx_limit: 5
    }
  });
  
  if (response.data.success) {
    console.log(`Wallet: ${response.data.label} (${response.data.category})`);
    if (response.data.transactions) {
      console.log(`Transaction count: ${response.data.transactions.count}`);
    }
  }
}
```

### cURL

```bash
# Get whale transactions
curl -X GET "http://localhost:8000/api/v1/onchain/whale-transactions?symbol=BTC&hours=24&limit=10" \
  -H "Accept: application/json"

# Get on-chain metrics
curl -X GET "http://localhost:8000/api/v1/onchain/metrics/BTC?hours=168" \
  -H "Accept: application/json"

# Get wallet information
curl -X GET "http://localhost:8000/api/v1/onchain/wallet/0x1234567890123456789012345678901234567890?include_transactions=true" \
  -H "Accept: application/json"
```

---

## Notes

- All timestamps are in ISO 8601 format with UTC timezone
- All monetary amounts are in USD unless otherwise specified
- Wallet addresses are case-insensitive (automatically lowercased)
- Historical data is retained for 90 days for whale transactions and on-chain metrics
- Wallet labels are maintained in a separate database and updated periodically

---

## Support

For issues, questions, or feature requests, please contact the development team or open an issue in the project repository.

**Last Updated**: November 11, 2025  
**API Version**: 1.0
