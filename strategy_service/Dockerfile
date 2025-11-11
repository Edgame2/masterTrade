FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
# Copy shared modules first
COPY shared/ /app/shared/

# Copy service-specific files
COPY strategy_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY strategy_service/ .

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

# Expose port for API and metrics
EXPOSE 8006 9091

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health')" || exit 1

CMD ["python", "main.py"]