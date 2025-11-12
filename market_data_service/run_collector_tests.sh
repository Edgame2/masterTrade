#!/bin/bash
# Test Runner Script for Collector Unit Tests
# Usage: ./run_collector_tests.sh [options]

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default options
VERBOSE=false
COVERAGE=true
PARALLEL=false
SPECIFIC_TEST=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --no-coverage)
            COVERAGE=false
            shift
            ;;
        -p|--parallel)
            PARALLEL=true
            shift
            ;;
        -t|--test)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: ./run_collector_tests.sh [options]"
            echo ""
            echo "Options:"
            echo "  -v, --verbose       Verbose output"
            echo "  --no-coverage       Skip coverage reporting"
            echo "  -p, --parallel      Run tests in parallel"
            echo "  -t, --test NAME     Run specific test file"
            echo "  -h, --help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run_collector_tests.sh                      # Run all tests with coverage"
            echo "  ./run_collector_tests.sh -v                   # Verbose output"
            echo "  ./run_collector_tests.sh -p                   # Run in parallel"
            echo "  ./run_collector_tests.sh -t test_moralis      # Run only Moralis tests"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Collector Unit Tests Runner${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if we're in the right directory
if [ ! -d "tests/collectors" ]; then
    echo -e "${RED}Error: tests/collectors directory not found${NC}"
    echo "Please run this script from the market_data_service directory"
    exit 1
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${YELLOW}pytest not found. Installing test dependencies...${NC}"
    pip install -r requirements-test.txt
    echo ""
fi

# Build pytest command
PYTEST_CMD="pytest"

if [ -n "$SPECIFIC_TEST" ]; then
    PYTEST_CMD="$PYTEST_CMD tests/collectors/test_${SPECIFIC_TEST}_collector.py"
else
    PYTEST_CMD="$PYTEST_CMD tests/collectors/"
fi

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=collectors --cov-report=html --cov-report=term-missing"
fi

if [ "$PARALLEL" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -n auto"
fi

# Add standard options
PYTEST_CMD="$PYTEST_CMD --tb=short"

echo -e "${YELLOW}Running command:${NC} $PYTEST_CMD"
echo ""

# Run tests
if $PYTEST_CMD; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✅ All tests passed!${NC}"
    echo -e "${GREEN}========================================${NC}"
    
    if [ "$COVERAGE" = true ]; then
        echo ""
        echo -e "${YELLOW}Coverage report saved to: htmlcov/index.html${NC}"
        echo -e "${YELLOW}View with: xdg-open htmlcov/index.html${NC}"
    fi
    
    exit 0
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}❌ Some tests failed${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
