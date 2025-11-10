# Risk Management Service

## Overview

The Risk Management Service is a comprehensive risk control system for the MasterTrade trading platform. It provides intelligent position sizing, dynamic stop-loss management, portfolio risk monitoring, and real-time risk alerts to ensure safe and profitable trading operations.

## 🎯 Key Features

### Position Sizing Engine
- **Multi-Algorithm Approach**: Combines volatility-based sizing, Kelly criterion, and risk parity
- **Signal Strength Integration**: Adjusts position size based on signal confidence
- **Dynamic Risk Assessment**: Real-time risk factor analysis and confidence scoring
- **Asset Class Awareness**: Different limits and multipliers for crypto, stablecoins, and DeFi tokens
- **Portfolio Constraints**: Enforces correlation limits and concentration constraints

### Stop-Loss Management
- **Multiple Stop Types**: Fixed, trailing, volatility-based, ATR-based, and support/resistance stops
- **Adaptive Algorithms**: Automatically adjusts stops based on market conditions
- **Breakeven Protection**: Moves stops to protect profits when positions become favorable
- **Time Decay**: Tightens stops over time for underperforming positions
- **Real-Time Updates**: Continuous stop price adjustments with market movements

### Portfolio Risk Controls
- **Value at Risk (VaR)**: 1-day and 5-day VaR calculations with Expected Shortfall
- **Drawdown Monitoring**: Real-time tracking with historical high-water marks
- **Correlation Analysis**: Portfolio-wide correlation risk assessment and limits
- **Concentration Metrics**: HHI-based concentration analysis and warnings
- **Liquidity Assessment**: Position liquidity scoring and illiquid exposure tracking
- **Real-Time Alerts**: Automated notifications for limit breaches and risk escalations

### API & Integration
- **RESTful API**: Comprehensive FastAPI endpoints for all risk functions
- **RabbitMQ Integration**: Real-time message processing for risk checks and alerts
- **Database Operations**: Full Azure Cosmos DB integration with optimized queries
- **Dashboard Support**: Complete data API for risk management dashboards

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Strategy      │────│  Risk Manager   │────│  Order Executor │
│   Services      │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                    ┌─────────┼─────────┐
                    │         │         │
              ┌─────────┐ ┌─────────┐ ┌─────────┐
              │Position │ │Stop-Loss│ │Portfolio│
              │ Sizing  │ │ Manager │ │ Risk    │
              │ Engine  │ │         │ │ Control │
              └─────────┘ └─────────┘ └─────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
              ┌─────────┐         ┌─────────┐
              │ Azure   │         │RabbitMQ │
              │Cosmos DB│         │Messages │
              └─────────┘         └─────────┘
```

## 📁 Project Structure

```
risk_manager/
├── config.py                    # Configuration and settings
├── database.py                  # Azure Cosmos DB operations
├── position_sizing.py           # Position sizing algorithms
├── stop_loss_manager.py         # Stop-loss management system
├── portfolio_risk_controller.py # Portfolio risk monitoring
├── main.py                     # FastAPI endpoints
├── message_handler.py          # RabbitMQ integration
├── service.py                  # Service integration and lifecycle
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container configuration
└── README.md                   # This file
```

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Azure Cosmos DB account
- RabbitMQ server
- Docker (optional)

### Installation

1. **Clone and Navigate**
   ```bash
   cd MasterTrade/risk_manager
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment**
   
   Create `.env` file:
   ```env
   # Azure Cosmos DB
   COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
   COSMOS_KEY=your-primary-key
   COSMOS_DATABASE_NAME=mastertrade
   
   # RabbitMQ
   RABBITMQ_HOST=localhost
   RABBITMQ_PORT=5672
   RABBITMQ_USER=guest
   RABBITMQ_PASSWORD=guest
   RABBITMQ_VHOST=/
   
   # Service Configuration
   RISK_SERVICE_HOST=0.0.0.0
   RISK_SERVICE_PORT=8005
   LOG_LEVEL=INFO
   ```

4. **Run the Service**
   ```bash
   python service.py
   ```

### Docker Deployment

1. **Build Image**
   ```bash
   docker build -t mastertrade/risk-manager .
   ```

2. **Run Container**
   ```bash
   docker run -p 8005:8005 \
     -e COSMOS_ENDPOINT=your-endpoint \
     -e COSMOS_KEY=your-key \
     -e RABBITMQ_HOST=rabbitmq \
     mastertrade/risk-manager
   ```

## 🔧 Configuration

### Risk Parameters

The service uses comprehensive risk parameters defined in `config.py`:

```python
# Position Sizing Limits
MIN_POSITION_SIZE_USD = 10.0
MAX_POSITION_SIZE_USD = 100000.0
MAX_SINGLE_POSITION_PERCENT = 10.0
DEFAULT_RISK_PER_TRADE = 2.0

# Portfolio Risk Limits
MAX_PORTFOLIO_RISK_PERCENT = 15.0
MAX_LEVERAGE_RATIO = 3.0
MAX_DRAWDOWN_PERCENT = 20.0
MAX_VAR_PERCENT = 5.0

# Stop-Loss Settings
MIN_STOP_LOSS_PERCENT = 0.5
MAX_STOP_LOSS_PERCENT = 15.0
DEFAULT_STOP_LOSS_PERCENT = 3.0

# Asset Class Limits
CRYPTO_MAX_POSITION_PERCENT = 8.0
STABLECOIN_MAX_POSITION_PERCENT = 15.0
DEFI_MAX_POSITION_PERCENT = 5.0
```

### Asset Classification

Assets are automatically classified with appropriate risk multipliers:

```python
ASSET_CLASSES = {
    "BTC": "CRYPTO", "ETH": "CRYPTO", "SOL": "CRYPTO",
    "USDT": "STABLECOIN", "USDC": "STABLECOIN", "BUSD": "STABLECOIN",
    "UNI": "DEFI", "AAVE": "DEFI", "COMP": "DEFI"
}

RISK_MULTIPLIERS = {
    "CRYPTO": 1.0,      # Base risk
    "STABLECOIN": 0.3,  # Lower risk
    "DEFI": 1.5,        # Higher risk
    "ALTCOIN": 2.0      # Highest risk
}
```

## 📡 API Reference

### Position Sizing

**POST** `/position-sizing/calculate`
```json
{
  "symbol": "BTC",
  "strategy_id": "momentum_v1",
  "signal_strength": 0.85,
  "current_price": 45000.0,
  "volatility": 0.03,
  "risk_per_trade_percent": 2.0
}
```

**Response:**
```json
{
  "success": true,
  "recommended_size_usd": 2500.0,
  "recommended_quantity": 0.055556,
  "position_risk_percent": 1.8,
  "stop_loss_price": 43650.0,
  "max_loss_usd": 450.0,
  "confidence_score": 0.82,
  "approved": true
}
```

### Stop-Loss Management

**POST** `/stop-loss/create`
```json
{
  "position_id": "pos_123",
  "symbol": "ETH",
  "entry_price": 3000.0,
  "quantity": 0.8,
  "config": {
    "stop_type": "trailing",
    "initial_stop_percent": 3.0,
    "trailing_distance_percent": 2.0,
    "breakeven_protection": true
  }
}
```

### Portfolio Risk

**GET** `/portfolio/risk-metrics`
```json
{
  "portfolio_value": 125000.0,
  "leverage_ratio": 1.8,
  "risk_measures": {
    "var_1d": 2500.0,
    "max_drawdown": 8.5,
    "current_drawdown": 2.1
  },
  "overall_risk": {
    "risk_level": "medium",
    "risk_score": 45.2
  }
}
```

## 🔄 Message Queue Integration

### Risk Check Flow

1. **Strategy Service** → Risk Check Request
2. **Risk Manager** → Position Sizing & Risk Analysis
3. **Risk Manager** → Approval/Rejection Response
4. **Strategy Service** → Order Execution (if approved)

### Real-Time Monitoring

- **Price Updates** → Stop-Loss Adjustments
- **Position Updates** → Portfolio Risk Recalculation
- **Risk Alerts** → Immediate Notifications
- **Stop-Loss Triggers** → Order Execution Commands

## 📊 Risk Metrics

### Value at Risk (VaR)
- **1-Day VaR**: Maximum expected loss over 1 day (95% confidence)
- **5-Day VaR**: Maximum expected loss over 5 days (95% confidence)
- **Expected Shortfall**: Average loss exceeding VaR threshold

### Concentration Metrics
- **HHI Index**: Herfindahl-Hirschman Index for portfolio concentration
- **Largest Position**: Percentage of portfolio in single largest position
- **Sector Exposure**: Concentration by asset class/sector

### Correlation Analysis
- **Correlation Matrix**: Cross-asset correlation coefficients
- **Correlation Risk**: Weighted correlation exposure score
- **Diversification**: Portfolio diversification effectiveness

## 🚨 Risk Alerts

### Alert Types
- **Exposure Limit**: Single position or sector exposure exceeded
- **VaR Exceeded**: Portfolio VaR above acceptable threshold
- **Drawdown Warning**: Portfolio drawdown approaching limits
- **Correlation Breach**: High correlation between positions
- **Liquidity Risk**: Excessive exposure to illiquid assets
- **Volatility Spike**: Extreme market volatility detected

### Severity Levels
- **LOW**: Information and minor warnings
- **MEDIUM**: Attention required, monitor closely
- **HIGH**: Action recommended, consider position adjustments
- **CRITICAL**: Immediate action required, stop trading

## 🔍 Monitoring & Debugging

### Health Endpoints
- **GET** `/health` - Service health check
- **GET** `/portfolio/dashboard` - Complete risk dashboard data
- **GET** `/portfolio/risk-alerts` - Active risk alerts

### Logging
The service uses structured logging with JSON format:
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "message": "Position size calculated for BTC",
  "symbol": "BTC",
  "size_usd": 2500.0,
  "approved": true
}
```

### Metrics Collection
- Portfolio risk scores and trends
- Position sizing decisions and outcomes
- Stop-loss trigger rates and effectiveness
- Alert frequency and resolution times

## 🧪 Testing

```bash
# Unit tests
pytest tests/unit/

# Integration tests  
pytest tests/integration/

# API tests
pytest tests/api/

# Load testing
pytest tests/load/
```

## 🔒 Security Considerations

- **API Authentication**: Implement JWT or API key authentication
- **Rate Limiting**: Protect endpoints from abuse
- **Input Validation**: Strict validation of all risk parameters
- **Audit Logging**: Complete audit trail of risk decisions
- **Data Encryption**: Encrypt sensitive configuration data

## 📈 Performance Optimization

- **Database Indexing**: Optimized queries with proper indexing
- **Caching**: Redis caching for frequently accessed data
- **Async Processing**: Non-blocking operations throughout
- **Connection Pooling**: Efficient database connection management
- **Message Batching**: Batch processing for high-volume updates

## 🤝 Integration Points

### Strategy Services
- Real-time risk check requests
- Position sizing recommendations
- Risk approval/rejection responses

### Order Executor
- Stop-loss trigger notifications
- Risk-based order modifications
- Position limit enforcement

### Portfolio Service
- Position updates and tracking
- P&L calculations and reporting
- Account balance monitoring

### Market Data Service
- Price feeds for risk calculations
- Volatility and volume data
- Technical indicator inputs

### Monitoring Service
- Risk alert notifications
- Dashboard data feeds
- Performance metrics collection

## 📚 Further Reading

- [Position Sizing Algorithms](docs/position-sizing.md)
- [Stop-Loss Strategies](docs/stop-loss.md) 
- [Portfolio Risk Theory](docs/portfolio-risk.md)
- [Message Queue Patterns](docs/messaging.md)
- [Database Schema](docs/database.md)

## 🆘 Support

For issues and questions:
- Check logs in `/var/log/mastertrade/risk-manager.log`
- Review configuration in `config.py`
- Monitor service health at `/health` endpoint
- Examine risk alerts at `/portfolio/risk-alerts`

## 📄 License

This Risk Management Service is part of the MasterTrade platform and is proprietary software.