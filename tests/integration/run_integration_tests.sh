#!/bin/bash
# Run integration tests for goal-oriented trading

set -e

echo "================================================"
echo "Goal-Oriented Trading Integration Tests"
echo "================================================"
echo ""

# Check if PostgreSQL is running
echo "1. Checking PostgreSQL connection..."
if psql -h localhost -p 5432 -U mastertrade -d mastertrade -c "SELECT 1" > /dev/null 2>&1; then
    echo "   ✓ PostgreSQL is running"
else
    echo "   ✗ PostgreSQL is not running or not accessible"
    echo "   Please start PostgreSQL: docker compose up -d postgres"
    exit 1
fi

# Check if schema exists
echo "2. Checking database schema..."
if psql -h localhost -p 5432 -U mastertrade -d mastertrade -c "\dt financial_goals" > /dev/null 2>&1; then
    echo "   ✓ Goal-oriented tables exist"
else
    echo "   ✗ Goal-oriented tables do not exist"
    echo "   Running migration..."
    psql -h localhost -p 5432 -U mastertrade -d mastertrade -f risk_manager/migrations/add_goal_oriented_tables.sql
    echo "   ✓ Migration complete"
fi

# Set environment variable
export TEST_DATABASE_URL="postgresql://mastertrade:mastertrade@localhost:5432/mastertrade"

# Check if pytest is installed
echo "3. Checking test dependencies..."
if ! python3 -m pytest --version > /dev/null 2>&1; then
    echo "   ✗ pytest not installed"
    echo "   Installing pytest..."
    pip install pytest pytest-asyncio asyncpg
    echo "   ✓ Dependencies installed"
else
    echo "   ✓ pytest is installed"
fi

echo ""
echo "================================================"
echo "Running Integration Tests"
echo "================================================"
echo ""

# Run tests
python3 -m pytest tests/integration/test_goal_trading_flow.py -v -s

echo ""
echo "================================================"
echo "Test Execution Complete"
echo "================================================"
