FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production image
FROM python:3.11-slim

WORKDIR /app

# Copy only necessary files from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY pyproject.toml .
COPY README.md .
COPY LICENSE .

# Install the package
RUN pip install --no-cache-dir -e .

# Create data directory
RUN mkdir -p /data

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Environment variables
ENV OB_DATA_DIR=/data
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8080

# Volume for persistent data
VOLUME ["/data"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD openbridge status || exit 1

# Run the server
CMD ["openbridge", "start", "--host", "0.0.0.0", "--port", "8080"]
