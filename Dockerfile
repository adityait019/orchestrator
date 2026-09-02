FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy the project
COPY . .

# Install dependencies
RUN uv sync --frozen --no-dev

# Start the Orchestrator
CMD ["sh", "-c", "uv run python database/create_tables.py && uv run uvicorn main:app --host 0.0.0.0 --port 8000"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1