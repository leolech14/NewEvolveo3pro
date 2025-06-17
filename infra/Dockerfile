# Multi-stage build for production deployment
FROM python:3.12-slim as builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libfontconfig1 \
    libxrender1 \
    libgomp1 \
    libgdal-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /build

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY pyproject.toml .
COPY README.md .

# Install the package
RUN pip install -e .

# Production stage
FROM python:3.12-slim as production

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libfontconfig1 \
    libxrender1 \
    libgomp1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd -r etl && useradd -r -g etl -s /bin/bash etl

# Set work directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code
COPY --from=builder /build/src ./src
COPY --from=builder /build/pyproject.toml .

# Create necessary directories
RUN mkdir -p data/{incoming,raw_json,draft_csv,golden,artefacts} \
    && mkdir -p logs \
    && chown -R etl:etl /app

# Switch to non-root user
USER etl

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from src.merger.ensemble_merger import EnsembleMerger; m = EnsembleMerger(); exit(0 if any(m.health_check().values()) else 1)"

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Expose ports
EXPOSE 8080 8000

# Default command
CMD ["evolve", "--help"]

# Labels for metadata
LABEL maintainer="Leo Lech <leo@example.com>"
LABEL version="0.1.0"
LABEL description="NewEvolveo3pro: Failure-proof bank statement extraction pipeline"
