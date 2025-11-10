# MasterTrade - Crypto Trading Bot

A comprehensive cryptocurrency trading bot built with microservices architecture using Python and FastAPI.

## Architecture

- **Market Data Service**: Real-time market data streaming, sentiment analysis, and stock index correlation
- **Strategy Service**: AI-powered trading strategy execution with daily crypto selection and automatic strategy activation
- **Order Executor**: Advanced order management with multi-exchange integration
- **Arbitrage Service**: Cross-exchange and DEX arbitrage opportunity detection
- **API Gateway**: Unified REST API with authentication and data aggregation
- **Database**: PostgreSQL for reliable, performant local data storage
- **Message Queue**: RabbitMQ for inter-service communication
- **Monitoring**: Prometheus + Grafana for metrics and visualization
- **Security**: Environment-based credential management

## Quick Start

**Prerequisites:**
- Docker and Docker Compose installed
- PostgreSQL installed and running locally on your machine
- PostgreSQL database `mastertrade` created

1. Copy environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your API credentials:
   - PostgreSQL connection details (user, password, database name)
   - Exchange API keys (Binance, etc.)
   - RabbitMQ credentials

3. Ensure PostgreSQL is running and accessible:
   ```bash
   psql -U mastertrade -d mastertrade -c "SELECT 1;"
   ```

4. Build and run all services:
   ```bash
   docker compose up --build
   ```

4. Access the interfaces:
   - Management UI: http://localhost:3000
   - API Gateway: http://localhost:8080
   - Data Access API: http://localhost:8005
   - Grafana: http://localhost:3001
   - RabbitMQ Management: http://localhost:15672
   - Prometheus: http://localhost:9090

## Configuration

Before starting, configure the following in your `.env` file:

- **PostgreSQL**: Set database credentials (user, password, database name)
  - Database must be running on your local machine
  - Docker containers will connect via `host.docker.internal`
- **Exchange API Keys**: Add your Binance and other exchange credentials
- **RabbitMQ Credentials**: Set username/password for message queue
- **JWT Secret**: Generate secure secret for API authentication

## Services Overview

### Market Data Service
- Multi-source data collection (crypto, sentiment, stock indices)
- Real-time and historical data with PostgreSQL storage
- Dynamic technical indicator calculation system
- Enhanced data sharing via RabbitMQ

### Strategy Service
- Advanced AI/ML trading strategies with transformer models and RL agents
- Daily crypto selection system that identifies best cryptocurrencies to trade
- Automatic strategy activation based on performance metrics
- Daily strategy review and improvement system
- Generates buy/sell signals based on comprehensive market analysis
- Publishes trading signals to message queue

### Order Executor
- Executes trades on Binance exchange
- Manages order lifecycle and status tracking
- Handles order validation and error recovery

### Risk Manager
- Calculates position sizes and risk metrics
- Enforces stop-loss and take-profit rules
- Monitors portfolio exposure and limits

### Management UI
- Real-time dashboard with trading metrics
- Strategy configuration and backtesting
- Manual trading controls and overrides

## Development

Each service is containerized and can be developed independently. See individual service README files for development setup.

## Monitoring

- **Grafana Dashboards**: Trading performance, system metrics, alerts
- **Prometheus Metrics**: Custom metrics from each service
- **Application Logs**: Centralized logging with structured output

## Security Notes

- Never commit real API keys or passwords
- Use secure passwords in production
- Configure proper firewall rules
- Enable SSL/TLS for external connections

## License

This project is for educational purposes. Use at your own risk.# masterTrade
