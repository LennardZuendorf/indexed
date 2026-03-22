# =============================================================================
# Indexed MCP Server - Docker Image
# =============================================================================
# Multi-stage build for the indexed CLI and MCP server.
#
# Usage:
#   docker build -t indexed .
#   docker run -v ~/.indexed:/root/.indexed indexed              # MCP server (stdio)
#   docker run -v ~/.indexed:/root/.indexed indexed index inspect  # CLI commands
#
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies with uv
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy workspace files needed for dependency resolution
COPY pyproject.toml uv.lock ./
COPY indexed/pyproject.toml indexed/
COPY packages/indexed-core/pyproject.toml packages/indexed-core/
COPY packages/indexed-config/pyproject.toml packages/indexed-config/
COPY packages/indexed-connectors/pyproject.toml packages/indexed-connectors/
COPY packages/utils/pyproject.toml packages/utils/

# Copy source code
COPY indexed/src indexed/src
COPY packages/indexed-core/src packages/indexed-core/src
COPY packages/indexed-config/src packages/indexed-config/src
COPY packages/indexed-connectors/src packages/indexed-connectors/src
COPY packages/utils/src packages/utils/src

# Install dependencies (production only, no dev dependencies)
RUN uv sync --frozen --no-dev

# Pre-download embedding model into HuggingFace cache
ENV HF_HUB_CACHE=/app/.cache/huggingface/hub
RUN uv run indexed init || true

# -----------------------------------------------------------------------------
# Stage 2: Runtime - Minimal image with installed packages
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Install runtime dependencies for document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    # For PDF processing (unstructured)
    libmagic1 \
    poppler-utils \
    # For office documents
    libreoffice-common \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security (optional, commented out for simpler volume mounts)
# RUN useradd -m -u 1000 indexed
# USER indexed

# Set working directory
WORKDIR /app

# Copy uv from builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy installed environment from builder
COPY --from=builder /app /app

# Create data directory for volume mount
RUN mkdir -p /root/.indexed/data/collections /root/.indexed/data/caches

# Environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HF_HUB_CACHE=/app/.cache/huggingface/hub

# Default MCP server port (for HTTP/SSE transports)
EXPOSE 8000

# Health check for HTTP mode
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Entrypoint: indexed CLI (allows all commands)
# Default command: mcp (starts MCP server in stdio mode)
ENTRYPOINT ["indexed"]
CMD ["mcp"]
