#!/bin/bash

echo "🚀 MASTERTRADE SYSTEM TEST - COMPLETE CHECK"
echo "=============================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

services=(
    "API Gateway:8090"
    "Market Data Service:8000"
    "Strategy Service:8001" 
    "Order Executor:8081"
    "Monitoring UI:3001"
)

echo -e "\n📊 Testing all MasterTrade services..."

for service in "${services[@]}"; do
    name=$(echo $service | cut -d: -f1)
    port=$(echo $service | cut -d: -f2)
    
    echo -e "\n🔍 Testing $name on port $port..."
    
    # Test basic connectivity
    if curl -s --connect-timeout 5 "http://localhost:$port" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ $name is RUNNING${NC}"
        
        # Test health endpoint if available
        if curl -s --connect-timeout 3 "http://localhost:$port/health" > /dev/null 2>&1; then
            echo -e "   💚 Health endpoint: OK"
        fi
        
        # Test specific endpoints
        case $name in
            "API Gateway")
                if curl -s "http://localhost:$port/api/market-data/health" > /dev/null 2>&1; then
                    echo -e "   🔄 Market data routing: OK"
                fi
                if curl -s "http://localhost:$port/api/strategy/health" > /dev/null 2>&1; then
                    echo -e "   🧠 Strategy routing: OK"
                fi
                ;;
            "Market Data Service")
                response=$(curl -s "http://localhost:$port/symbols/active")
                if [ $? -eq 0 ]; then
                    echo -e "   📈 Symbols endpoint: OK"
                fi
                ;;
            "Strategy Service")
                response=$(curl -s "http://localhost:$port/strategies")
                if [ $? -eq 0 ]; then
                    echo -e "   🎯 Strategies endpoint: OK"
                fi
                ;;
            "Order Executor")
                response=$(curl -s "http://localhost:$port/orders")
                if [ $? -eq 0 ]; then
                    echo -e "   📋 Orders endpoint: OK"
                fi
                ;;
        esac
        
    else
        echo -e "${RED}❌ $name is NOT RESPONDING${NC}"
    fi
done

echo -e "\n🔗 Testing Inter-Service Communication..."

# Test Strategy -> Market Data
echo -e "\n🧠➡️📊 Strategy Service → Market Data Service"
if curl -s "http://localhost:8001/market-data/symbols" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Strategy can access Market Data${NC}"
else
    echo -e "${YELLOW}⚠️  Direct communication may need API Gateway${NC}"
fi

# Test via API Gateway
echo -e "\n🌐 API Gateway Integration Test"
if curl -s "http://localhost:8090/api/strategy/health" > /dev/null 2>&1 && \
   curl -s "http://localhost:8090/api/market-data/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ API Gateway routing works${NC}"
else
    echo -e "${YELLOW}⚠️  API Gateway routing needs attention${NC}"
fi

echo -e "\n📈 System Status Summary"
echo "========================"

total_services=5
running_services=0

for service in "${services[@]}"; do
    name=$(echo $service | cut -d: -f1)
    port=$(echo $service | cut -d: -f2)
    
    if curl -s --connect-timeout 3 "http://localhost:$port" > /dev/null 2>&1; then
        running_services=$((running_services + 1))
    fi
done

echo "Services Running: $running_services/$total_services"

if [ $running_services -eq $total_services ]; then
    echo -e "${GREEN}🎉 ALL SERVICES ARE OPERATIONAL!${NC}"
    echo -e "${GREEN}MasterTrade system is ready for trading!${NC}"
elif [ $running_services -gt 3 ]; then
    echo -e "${YELLOW}⚡ SYSTEM MOSTLY OPERATIONAL ($running_services/$total_services)${NC}"
    echo -e "${YELLOW}Core trading functionality available${NC}"
else
    echo -e "${RED}🚨 SYSTEM NEEDS ATTENTION ($running_services/$total_services services running)${NC}"
fi

echo -e "\n🌐 Access URLs:"
echo "• API Gateway:        http://localhost:8090"
echo "• Market Data:        http://localhost:8000" 
echo "• Strategy Service:   http://localhost:8001"
echo "• Order Executor:     http://localhost:8081"
echo "• Monitoring UI:      http://localhost:3001"

echo -e "\n📚 API Documentation:"
echo "• Market Data API:    http://localhost:8000/docs"
echo "• Strategy API:       http://localhost:8001/docs"
echo "• Order Executor API: http://localhost:8081/docs"

echo -e "\nTest completed at: $(date)"