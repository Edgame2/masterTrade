"""
End-to-End Integration Tests for MasterTrade System

This package contains comprehensive end-to-end tests that verify
the complete data flow through the system:
- Collector ingestion → RabbitMQ → Consumer → PostgreSQL → API

Test categories:
- Data pipeline: Full collector-to-API flow
- Signal aggregation: Multi-source signal generation
- API endpoints: REST API query functionality
- Collector integration: Real collector behavior with mocked APIs
"""
