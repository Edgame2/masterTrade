# Dynamic Technical Indicator System

## Overview

The Dynamic Technical Indicator System enables the `strategy_service` to configure and request specific technical indicators from the `market_data_service` in real-time. This system provides efficient, cached calculations with flexible configuration options and **persistent database storage** for configuration management.

## Architecture

### Components

1. **Database Models** (`models.py`)
   - `IndicatorConfigurationDB` - Persistent indicator configurations
   - `IndicatorCalculationResult` - Historical calculation results
   - Azure Cosmos DB containers with optimized indexing

2. **Indicator Models** (`indicator_models.py`)
   - Defines configuration structures for all supported indicators
   - Validates parameters for each indicator type
   - Handles request/response data models

3. **Technical Indicator Calculator** (`technical_indicator_calculator.py`)
   - High-performance calculation engine with caching
   - Supports batch processing and parallel execution
   - Implements all major technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, etc.)

4. **Configuration Manager** (`indicator_configuration_manager.py`)
   - **Database-driven configuration management**
   - Manages dynamic configuration via RabbitMQ
   - Handles subscriptions and continuous updates
   - Processes configuration requests from strategy service
   - Automatic refresh from database

5. **Market Data Indicator Client** (`shared/market_data_indicator_client.py`)
   - Client library for strategy service integration
   - Provides builder pattern for easy indicator configuration
   - Supports both RabbitMQ messaging and REST API access

## Supported Indicators

| Indicator | Type | Parameters | Output Fields |
|-----------|------|------------|---------------|
| SMA | `sma` | period | `sma_{period}` |
| EMA | `ema` | period | `ema_{period}` |
| RSI | `rsi` | period | `rsi_{period}` |
| MACD | `macd` | fast_period, slow_period, signal_period | `macd_line`, `macd_signal`, `macd_histogram` |
| Bollinger Bands | `bollinger_bands` | period, std_dev | `bb_upper`, `bb_middle`, `bb_lower` |
| Stochastic | `stochastic` | k_period, d_period | `stoch_k_{period}`, `stoch_d_{period}` |

## Usage Examples

### 1. Basic Indicator Request (Strategy Service)

```python
from shared.market_data_indicator_client import MarketDataIndicatorClient, create_indicator_builder

# Initialize client
client = MarketDataIndicatorClient(
    rabbitmq_url="amqp://user:pass@localhost:5672/",
    api_base_url="http://localhost:8001"
)
await client.connect()

# Create indicator configuration using builder
builder = (create_indicator_builder("BTCUSDC", "5m")
          .set_strategy_id("momentum_strategy_v1")
          .add_rsi(14)
          .add_macd(12, 26, 9)
          .add_sma(20)
          .add_sma(50))

indicators = builder.build()

# Request calculations
results = await client.request_bulk_indicators(
    strategy_id="momentum_strategy_v1",
    indicators=indicators,
    wait_for_results=True
)

# Process results
for result in results:
    print(f"Indicator: {result['configuration_id']}")
    print(f"Values: {result['values']}")
    print(f"Calculation time: {result['calculation_time_ms']}ms")
```

### 2. Convenience Functions

```python
from shared.market_data_indicator_client import create_standard_indicators

# Create standard indicator set
indicators = create_standard_indicators(
    symbol="ETHUSDC",
    interval="15m",
    strategy_id="trend_following_v2"
)

# Or create momentum-focused indicators
momentum_indicators = create_momentum_indicators(
    symbol="ADAUSDC", 
    interval="1h",
    strategy_id="momentum_v1"
)
```

### 3. Real-time Subscription

```python
# Register result handler
async def handle_rsi_update(result):
    rsi_value = result['values'].get('rsi_14')
    if rsi_value:
        if rsi_value > 70:
            print("RSI Overbought:", rsi_value)
        elif rsi_value < 30:
            print("RSI Oversold:", rsi_value)

# Register handler
client.register_result_handler("rsi_config_id", handle_rsi_update)

# Results will be automatically delivered via RabbitMQ
```

### 4. REST API Access (Alternative)

```python
# Direct REST API access for immediate results
config = {
    "id": "rsi_btc_test",
    "indicator_type": "rsi", 
    "parameters": [{"name": "period", "value": 14, "data_type": "int"}],
    "symbol": "BTCUSDC",
    "interval": "5m",
    "periods_required": 30,
    "output_fields": ["rsi_14"],
    "strategy_id": "test_strategy",
    "priority": 1
}

result = await client.calculate_indicator_rest(config)
print(f"RSI Value: {result['values']['rsi_14']}")
```

## Configuration Flow

### 1. Strategy Service → Market Data Service

```mermaid
sequenceDiagram
    participant S as Strategy Service
    participant R as RabbitMQ
    participant M as Market Data Service
    participant C as Calculator
    participant DB as Database

    S->>R: Publish indicator config (config.request.add)
    R->>M: Route to config manager
    M->>C: Create indicator calculation
    C->>DB: Fetch market data
    C->>C: Calculate indicator
    C->>R: Publish result (indicator_results)
    R->>S: Deliver result to strategy
```

### 2. RabbitMQ Routing Keys

- **Configuration Requests**: `config.request.{action}`
  - `config.request.add` - Add new indicator
  - `config.request.update` - Update existing indicator
  - `config.request.remove` - Remove indicator
  - `config.request.bulk` - Bulk operations
  - `config.request.subscribe` - Create subscription

- **Results**: `result.{symbol}.{interval}`
  - Example: `result.BTCUSDC.5m`

### 3. Message Formats

#### Configuration Request
```json
{
  "strategy_id": "momentum_v1",
  "configuration": {
    "id": "rsi_14_btc_12345",
    "indicator_type": "rsi",
    "parameters": [
      {"name": "period", "value": 14, "data_type": "int"}
    ],
    "symbol": "BTCUSDC",
    "interval": "5m",
    "periods_required": 30,
    "output_fields": ["rsi_14"],
    "strategy_id": "momentum_v1",
    "priority": 1,
    "cache_duration_minutes": 5
  },
  "calculate_immediately": true
}
```

#### Result Message
```json
{
  "configuration_id": "rsi_14_btc_12345",
  "symbol": "BTCUSDC",
  "interval": "5m", 
  "timestamp": "2023-12-01T10:30:00Z",
  "values": {
    "rsi_14": 65.42
  },
  "metadata": {
    "parameters": {"period": 14},
    "data_range": {
      "start": "2023-12-01T09:00:00Z",
      "end": "2023-12-01T10:30:00Z"
    }
  },
  "data_points_used": 50,
  "calculation_time_ms": 12.5,
  "cache_hit": false
}
```

## Database-Driven Features

### 1. Persistent Configuration Storage
- **Azure Cosmos DB containers**: `indicator_configurations` and `indicator_results`
- **Partition strategy**: Configurations partitioned by `strategy_id`
- **Optimized indexing**: Fast queries by symbol, interval, indicator type
- **Automatic TTL**: Results auto-expire after 7 days

### 2. Configuration Management
- **CRUD operations**: Full create, read, update, delete via REST API
- **Strategy-based organization**: Configurations grouped by strategy
- **Priority-based execution**: High-priority indicators calculated first
- **Performance tracking**: Statistics on calculation times and error rates

### 3. Background Processing
- **Continuous calculation**: Automatic recalculation based on frequency settings
- **Database-driven scheduling**: Configurations loaded from database
- **Error handling**: Failed calculations tracked and retried
- **Resource optimization**: Batch processing for efficiency

## Performance Features

### 1. Intelligent Caching
- **Multi-level caching**: Memory cache with TTL + database storage
- **Cache keys**: Hash of indicator type + symbol + interval + parameters
- **Cache statistics**: Hit ratios and performance metrics
- **Database persistence**: Results stored for historical analysis

### 2. Batch Processing
- **Parallel execution**: Multiple indicators calculated simultaneously
- **Batch optimization**: Efficient data loading for multiple symbols
- **Resource management**: Configurable batch sizes
- **Database batching**: Efficient bulk operations

### 3. Performance Monitoring
- **Prometheus metrics**: Calculation times, cache performance, error rates
- **Resource tracking**: Memory usage, CPU utilization
- **Throughput monitoring**: Calculations per minute
- **Database metrics**: Query performance and storage utilization

## API Endpoints

### Market Data Service Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/indicators/calculate` | POST | Calculate single indicator |
| `/api/indicators/bulk-calculate` | POST | Calculate multiple indicators |
| `/api/indicators/cached/{symbol}` | GET | Get cached indicator values |
| `/api/indicators/performance` | GET | Get performance metrics |

### Example Usage

```bash
# Create indicator configuration in database
curl -X POST "http://localhost:8001/api/indicators/configurations" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "momentum_v1",
    "indicator_type": "rsi",
    "symbol": "BTCUSDC",
    "interval": "5m",
    "parameters": {"period": 14},
    "output_fields": ["rsi_14"],
    "periods_required": 30,
    "active": true,
    "priority": 1,
    "continuous_calculation": true
  }'

# Get all configurations for a strategy
curl "http://localhost:8001/api/indicators/configurations?strategy_id=momentum_v1"

# Get indicator results from database
curl "http://localhost:8001/api/indicators/results/BTCUSDC?hours_back=24&limit=100"

# Get strategies overview
curl "http://localhost:8001/api/indicators/strategies"

# Calculate single RSI (immediate)
curl -X POST "http://localhost:8001/api/indicators/calculate" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "rsi_test",
    "indicator_type": "rsi",
    "parameters": [{"name": "period", "value": 14, "data_type": "int"}],
    "symbol": "BTCUSDC",
    "interval": "5m",
    "periods_required": 30,
    "output_fields": ["rsi_14"],
    "strategy_id": "test",
    "priority": 1
  }'
```

## Integration with Strategy Service

### 1. Update Strategy Service Dependencies

Add to `strategy_service/requirements.txt`:
```
aiohttp==3.9.1
aio-pika==9.3.1
```

### 2. Initialize Client in Strategy Service

```python
# strategy_service/main.py
from shared.market_data_indicator_client import MarketDataIndicatorClient

class StrategyService:
    def __init__(self):
        self.indicator_client = MarketDataIndicatorClient(
            rabbitmq_url=settings.RABBITMQ_URL,
            api_base_url="http://market_data_service:8001"
        )
    
    async def initialize(self):
        await self.indicator_client.connect()
    
    async def shutdown(self):
        await self.indicator_client.disconnect()
```

### 3. Use in Strategy Execution

```python
# In strategy execution
async def execute_strategy(self, symbol: str, strategy_config: Dict):
    # Request required indicators
    indicators = create_standard_indicators(symbol, "5m", self.strategy_id)
    results = await self.indicator_client.request_bulk_indicators(
        self.strategy_id, indicators
    )
    
    # Extract values for strategy logic
    indicator_values = {}
    for result in results:
        indicator_values.update(result['values'])
    
    # Execute strategy with indicators
    if indicator_values.get('rsi_14', 0) < 30:
        return self.generate_buy_signal(symbol, indicator_values)
    elif indicator_values.get('rsi_14', 0) > 70:
        return self.generate_sell_signal(symbol, indicator_values)
```

## Best Practices

### 1. Configuration Management
- **Use meaningful IDs**: Include indicator type, parameters, and symbol
- **Set appropriate priorities**: High-frequency strategies get priority 1
- **Configure cache TTL**: Balance freshness with performance

### 2. Error Handling
- **Timeout management**: Set appropriate timeouts for calculations
- **Fallback strategies**: Handle calculation failures gracefully
- **Resource limits**: Monitor memory and CPU usage

### 3. Performance Optimization
- **Batch requests**: Use bulk calculations for multiple indicators
- **Cache utilization**: Leverage cached results when possible
- **Subscription management**: Clean up unused subscriptions

## Monitoring and Debugging

### 1. Logs
- **Structured logging**: JSON format with correlation IDs
- **Performance logs**: Calculation times and cache statistics
- **Error tracking**: Detailed error information with context

### 2. Metrics
- **Prometheus integration**: Comprehensive performance metrics
- **Custom dashboards**: Grafana dashboards for monitoring
- **Alerting**: Alerts for calculation failures and performance issues

### 3. Health Checks
- **Service health**: Monitor service availability
- **Database connectivity**: Check database connections
- **RabbitMQ health**: Monitor message queue performance

This system provides a robust, efficient foundation for dynamic technical indicator calculations while maintaining high performance and flexibility for various trading strategies.