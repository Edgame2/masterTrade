# MasterTrade System Management Scripts

Quick reference for managing the MasterTrade trading bot system.

## 🚀 Quick Start

### One Command to Rule Them All

```bash
# Restart entire system
./restart.sh
```

## 📜 Available Scripts

### 1. `restart.sh` - Complete System Restart
Stops all services and restarts them in the correct order.

```bash
./restart.sh
```

**What it does:**
- Stops all running services (ports 8000, 8001, 8081, 8090, 3000)
- Starts Market Data Service (port 8000)
- Starts Strategy Service (port 8001)
- Starts Order Executor (port 8081)
- Starts API Gateway (port 8090)
- Starts Frontend UI (port 3000)
- Performs health checks on all services
- Shows access points and log file locations

### 2. `stop.sh` - Stop All Services
Stops all MasterTrade services.

```bash
./stop.sh
```

**What it does:**
- Kills processes on all MasterTrade ports
- Cleans up any remaining Python processes
- Confirms all services are stopped

### 3. `status.sh` - Check System Status
Shows the current status of all services.

```bash
./status.sh
```

**What it shows:**
- Running status of each service (✓ RUNNING / ✗ STOPPED)
- Process details (PID, CPU, Memory usage)
- API endpoints and URLs
- Log file locations
- Quick command reference

## 🔧 Service Details

| Service | Port | Description |
|---------|------|-------------|
| Market Data Service | 8000 | Collects and manages market data from exchanges |
| Strategy Service | 8001 | Manages trading strategies and signals |
| Order Executor | 8081 | Executes trades on exchanges |
| API Gateway | 8090 | Unified REST API for all services |
| Frontend UI | 3000 | Web-based management dashboard |

## 📊 Access Points

After starting the system, access:

- **Management Dashboard**: http://localhost:3000
  - View crypto pairs and historical data
  - Monitor strategies and performance
  - Manage trading configurations

- **API Gateway**: http://localhost:8090
  - REST API for all backend services
  - Health check: http://localhost:8090/health
  - API docs: http://localhost:8090/docs

## 📋 Log Files

All services write logs to `/tmp/`:

```bash
# View logs (real-time)
tail -f /tmp/market_data.log
tail -f /tmp/strategy_service.log
tail -f /tmp/order_executor.log
tail -f /tmp/api_gateway.log
tail -f /tmp/frontend.log

# View last 100 lines
tail -100 /tmp/api_gateway.log
```

## 🔍 Troubleshooting

### Service won't start

1. Check if virtual environment exists:
```bash
ls -la market_data_service/venv
ls -la strategy_service/venv
ls -la order_executor/venv
ls -la api_gateway/venv
```

2. Check the logs:
```bash
tail -50 /tmp/[service_name].log
```

3. Verify port is not in use:
```bash
lsof -i :8000  # or other port number
```

### Port already in use

```bash
# Kill specific port
lsof -ti:8090 | xargs kill -9

# Or use stop.sh to kill all
./stop.sh
```

### Frontend won't start

1. Check if node_modules exists:
```bash
ls monitoring_ui/node_modules
```

2. If missing, install dependencies:
```bash
cd monitoring_ui && npm install
```

## 🔄 Common Workflows

### Daily Development Workflow

```bash
# Start your day
./restart.sh

# Check everything is running
./status.sh

# Work on your changes...

# When done for the day
./stop.sh
```

### After Code Changes

```bash
# Restart just to pick up changes
./restart.sh
```

### Debugging Issues

```bash
# Stop everything
./stop.sh

# Start services one by one manually to see errors
cd market_data_service && ./venv/bin/python main.py
# (Ctrl+C when done)

cd strategy_service && ./venv/bin/python main.py
# etc...
```

## ⚙️ Configuration

### Using Mock Database (Development)

By default, API Gateway uses mock data. To use Azure Cosmos DB:

Edit `restart.sh` and change this line:
```bash
USE_MOCK_DATABASE=true nohup ./venv/bin/python main.py
```
to:
```bash
USE_MOCK_DATABASE=false nohup ./venv/bin/python main.py
```

### Environment Variables

Each service reads from its own `.env` file or uses defaults:
- `market_data_service/.env`
- `strategy_service/.env`
- `order_executor/.env`
- `api_gateway/.env`

## 🎯 Testing After Restart

```bash
# Quick health check all services
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8081/health
curl http://localhost:8090/health

# Test crypto management endpoint
curl http://localhost:8090/api/symbols | jq

# Open UI in browser
xdg-open http://localhost:3000  # Linux
open http://localhost:3000       # macOS
```

## 📚 Additional Commands

```bash
# View all MasterTrade processes
ps aux | grep -E "main\.py|next-server" | grep -v grep

# Check memory usage
ps aux | grep -E "main\.py|next-server" | awk '{sum+=$4} END {print "Total memory: " sum "%"}'

# Monitor logs in real-time (all services)
tail -f /tmp/*.log
```

## 🆘 Emergency Stop

If services are misbehaving:

```bash
# Nuclear option - kill everything
pkill -f "main.py"
pkill -f "next-server"

# Then restart cleanly
./restart.sh
```

## 📝 Notes

- Services start with a 3-second delay between each to ensure proper initialization
- Health checks wait 2 seconds after all services start
- Logs are appended, not overwritten, so you can see historical issues
- Frontend takes longest to start (5 seconds)
- All services run in the background with nohup

---

**Need Help?**
- Check the logs in `/tmp/`
- Run `./status.sh` to see what's running
- Ensure all virtual environments are created
- Verify ports 8000, 8001, 8081, 8090, 3000 are available
