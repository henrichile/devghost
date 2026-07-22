# Backend Dockerfile - Python FastAPI analysis engine
FROM python:3.11-slim

# Install system dependencies:
# - git: required for cloning repositories in POST /analyze
# - build-essential: required for compiling tree-sitter C extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends git build-essential curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install the package and all dependencies (tree-sitter grammars, FastAPI, Uvicorn)
RUN pip install --no-cache-dir .

# Expose the API port
EXPOSE 8000

# Run Uvicorn - exec form ensures signals propagate correctly
# and container exits with non-zero code if Uvicorn fails to start
CMD ["uvicorn", "dev_ghost_parser.server:app", "--host", "0.0.0.0", "--port", "8000"]
