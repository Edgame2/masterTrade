FROM python:3.11-slim

WORKDIR /app

# Copy shared modules first
COPY shared/ /app/shared/

# Copy service-specific files
COPY api_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api_gateway/ .

RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

CMD ["python", "main.py"]