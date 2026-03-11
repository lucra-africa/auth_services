FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050

# Use gunicorn with uvicorn worker in production for better process management.
# Single worker required: WebSocket connections are stored in-memory per process.
# Render sets PORT env var automatically; fall back to 8050.
CMD ["sh", "-c", "gunicorn src.main:app --bind 0.0.0.0:${PORT:-8050} --worker-class uvicorn.workers.UvicornWorker --workers 1 --timeout 120"]
