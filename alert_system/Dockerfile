FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY alert_system/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY alert_system/ .

# Expose port
EXPOSE 8007

# Run the application
CMD ["python", "main.py"]
