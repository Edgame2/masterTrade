#!/bin/bash
# Rebuild and restart strategy service

echo "Stopping strategy service..."
docker stop mastertrade_strategy

echo "Removing old container..."
docker rm mastertrade_strategy

echo "Rebuilding strategy service image..."
docker compose build strategy_service

echo "Starting strategy service..."
docker compose up -d strategy_service

echo "Waiting for service to start..."
sleep 10

echo "Checking service status..."
docker ps --filter "name=strategy" --format "{{.Names}}\t{{.Status}}"

echo "Done! Check logs with: docker logs mastertrade_strategy"
