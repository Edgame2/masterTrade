# Enhanced Market Data Sharing System

## Overview

The MasterTrade system now features comprehensive data sharing between the market_data_service and all other services (order_executor, strategy_service, arbitrage_service, etc.). This enhancement provides real-time access to all collected data types for better trading decisions.

## Data Types Available

### 1. Real-time Market Data
- **Kline/Candlestick Data**: OHLCV data with customizable intervals
- **Trade Data**: Individual trade executions with price, quantity, and timestamp
- **Order Book Data**: Bid/ask spreads and market depth
- **Ticker Updates**: Real-time price changes and 24h statistics

### 2. Sentiment Analysis Data
- **Global Crypto Sentiment**: Overall cryptocurrency market sentiment
- **Global Market Sentiment**: Traditional market sentiment indicators
- **Per-Symbol Sentiment**: Individual cryptocurrency sentiment analysis
- **News Sentiment**: Market sentiment derived from news articles
- **Social Media Sentiment**: Twitter and Reddit sentiment analysis

### 3. Stock Market Indices
- **Major Indices**: S&P 500, NASDAQ, Dow Jones, etc.
- **Global Indices**: FTSE, Nikkei, DAX, and others
- **Real-time Values**: Current prices and percentage changes
- **Historical Data**: Historical stock index performance

### 4. Market Correlation Data
- **Crypto-Stock Correlation**: Correlation between crypto and traditional markets
- **Inter-Crypto Correlation**: Correlation between different cryptocurrencies
- **Market Beta**: Risk metrics and volatility correlations
- **Volatility Indicators**: Market volatility and fear/greed indices

## Communication Mechanisms

### 1. RabbitMQ Real-time Messaging

#### Enhanced RabbitMQ Configuration
```yaml
New Queues:
- sentiment_data: TTL 2h, Max 5,000 messages
- stock_index_data: TTL 24h, Max 1,000 messages  
- correlation_data: TTL 24h, Max 1,000 messages
- ticker_updates: TTL 30min, Max 20,000 messages
- orderbook_updates: TTL 5min, Max 50,000 messages
- trade_updates: TTL 30min, Max 30,000 messages
- strategy_market_data: TTL 1h, Max 15,000 messages
- executor_market_data: TTL 1h, Max 15,000 messages
```

#### Routing Keys
```yaml
Market Data:
- market.data.kline: Real-time candlestick data
- market.data.trade: Individual trade executions
- market.data.orderbook: Order book updates

Sentiment Data:
- sentiment.summary: Global sentiment updates
- sentiment.crypto.{symbol}: Per-cryptocurrency sentiment
- sentiment.news: News-based sentiment analysis

Stock Indices:
- stock.summary: Stock market summary
- stock.index.{index_name}: Individual index updates

Correlation:
- correlation.market: Market correlation analysis
- correlation.crypto: Crypto correlation analysis

Price Updates:
- ticker.{symbol}: Real-time price updates
```

### 2. REST API Access

#### Enhanced Data Access API Endpoints

**Market Data Endpoints:**
```
GET /api/market-data/{symbol}        # Historical market data
GET /api/latest-price/{symbol}       # Current price and 24h stats
GET /api/ohlcv/{symbol}             # OHLCV data for charting
GET /api/trades/{symbol}            # Recent trade history
```

**Sentiment Analysis Endpoints:**
```
GET /api/sentiment                   # All sentiment data
GET /api/sentiment/global           # Global market sentiment
GET /api/sentiment?symbol={symbol}   # Symbol-specific sentiment
```

**Stock Market Endpoints:**
```
GET /api/stock-indices              # All tracked stock indices
GET /api/stock-indices/{index}      # Specific index data
GET /api/stock-indices/correlation  # Stock-crypto correlation
```

**Correlation Analysis Endpoints:**
```
GET /api/correlation                # Market correlation data
GET /api/correlation/crypto         # Crypto-specific correlations
GET /api/correlation/traditional    # Traditional market correlations
```

**Comprehensive Summary:**
```
GET /api/market-summary             # Complete market overview
```

## Service Integration

### 1. Order Executor Enhancement

The order_executor now integrates comprehensive market data for intelligent order execution:

**Features Added:**
- **Smart Position Sizing**: Adjusts position sizes based on sentiment and volatility
- **Order Type Selection**: Chooses optimal order types (market/limit) based on market conditions
- **Risk Adjustment**: Reduces position sizes during negative sentiment periods
- **Volatility Awareness**: Adjusts execution strategy based on price volatility
- **Global Context**: Considers global market conditions in execution decisions

**Market Data Usage:**
```python
# Price Updates for Execution
current_prices[symbol] = {
    'price': real_time_price,
    'volume': current_volume,
    'price_change_percent': daily_change,
    'timestamp': update_time
}

# Sentiment-based Position Adjustment
if signal_type == 'BUY' and sentiment_score < -0.3:
    position_size *= 0.7  # Reduce by 30% for negative sentiment

# Volatility-based Order Type Selection
if price_change_percent > 3 or volume < 1000:
    order_type = 'LIMIT'  # Use limit orders for volatile markets
```

### 2. Strategy Service Enhancement

The strategy_service now uses comprehensive market data for enhanced strategy decisions:

**Features Added:**
- **Multi-factor Analysis**: Combines technical, sentiment, and correlation data
- **Global Context Awareness**: Considers global market conditions
- **Enhanced Signal Generation**: Improved signal quality with additional data sources
- **Market Regime Detection**: Adapts strategies based on market conditions
- **Risk-adjusted Signals**: Adjusts signal strength based on market risk

**Enhanced Strategy Context:**
```python
enhanced_context = {
    'current_data': market_data,
    'historical_data': price_history,
    'sentiment': symbol_sentiment,
    'global_crypto_sentiment': global_crypto,
    'global_market_sentiment': global_market,
    'correlation_data': correlation_analysis,
    'stock_indices': stock_market_data,
    'current_price': real_time_price
}
```

### 3. Enhanced Market Data Consumer

New unified consumer class for all services:

**Key Features:**
- **Unified Interface**: Single consumer for all data types
- **Selective Subscription**: Choose specific data types to consume
- **Automatic Fallback**: REST API backup when real-time fails
- **Message Enrichment**: Adds metadata and context to all messages
- **Service Identification**: Tags messages with source service

**Usage Example:**
```python
# Initialize consumer
consumer = EnhancedMarketDataConsumer(service_name="order_executor")
await consumer.initialize()

# Register handlers
consumer.add_message_handler("ticker_updates", handle_price_update)
consumer.add_message_handler("sentiment_updates", handle_sentiment)
consumer.add_message_handler("all", universal_handler)

# Start consuming specific data types
await consumer.start_consuming_specific_data_types([
    "ticker", "sentiment", "correlation", "stock_index"
])
```

## Message Format

### Enhanced Message Structure
```json
{
    "data_type": "ticker_updates",
    "timestamp": "2025-11-04T10:30:00Z",
    "source": "market_data_service",
    "data": {
        "symbol": "BTCUSDC",
        "price": 67500.00,
        "volume": 1234567.89,
        "price_change": 1250.50,
        "price_change_percent": 1.89,
        "high_24h": 68000.00,
        "low_24h": 65500.00
    }
}
```

### Sentiment Data Format
```json
{
    "data_type": "sentiment_updates",
    "timestamp": "2025-11-04T10:30:00Z",
    "source": "market_data_service",
    "data": {
        "global_crypto_sentiment": {
            "score": 0.65,
            "label": "positive",
            "confidence": 0.82
        },
        "global_market_sentiment": {
            "score": -0.23,
            "label": "slightly_negative",
            "confidence": 0.75
        },
        "BTCUSDC_sentiment": {
            "score": 0.45,
            "label": "positive",
            "sources": ["news", "twitter", "reddit"]
        }
    }
}
```

## Performance Considerations

### 1. Data Flow Optimization
- **Selective Subscriptions**: Services only receive relevant data types
- **Message Filtering**: Routing keys prevent unnecessary message delivery
- **Caching Strategy**: Local caching reduces API calls
- **Batch Processing**: Multiple updates processed together when possible

### 2. Resource Management
- **TTL Settings**: Automatic message expiration prevents queue buildup
- **Max Length Limits**: Prevents memory overflow in queues
- **Connection Pooling**: Efficient connection management
- **Graceful Degradation**: Fallback mechanisms when services are unavailable

### 3. Monitoring and Health Checks
- **Prometheus Metrics**: Track message throughput and latency
- **Health Endpoints**: Monitor service status and data freshness
- **Error Handling**: Comprehensive error logging and recovery
- **Performance Alerts**: Automated alerting for performance issues

## Benefits

### For Order Execution:
1. **Smarter Position Sizing**: Considers market sentiment and volatility
2. **Better Execution Timing**: Uses real-time market conditions
3. **Risk Management**: Automatic position adjustment based on market risk
4. **Cost Optimization**: Optimal order type selection reduces slippage

### For Strategy Development:
1. **Enhanced Signals**: Multi-factor analysis improves signal quality
2. **Market Context**: Global market awareness in strategy decisions
3. **Risk Adjustment**: Sentiment-based signal strength adjustment
4. **Regime Detection**: Adaptive strategies based on market conditions

### For System Performance:
1. **Unified Architecture**: Consistent data access across all services
2. **Real-time Updates**: Immediate availability of all market data
3. **Scalable Design**: Easy addition of new data sources and consumers
4. **Reliable Delivery**: Robust messaging with automatic failover

This enhanced data sharing system transforms MasterTrade from a basic trading bot into a sophisticated, data-driven trading platform that considers multiple market factors for optimal trading decisions.