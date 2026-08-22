# ── Stage 1: Build React frontend ─────────────────────────
FROM node:18-slim AS frontend-builder

WORKDIR /frontend

# Copy frontend package files
COPY frontend/package.json frontend/package-lock.json* ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Copy frontend source
COPY frontend/ .

# Build production bundle
RUN npm run build

# ── Stage 2: Python backend ────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 + sentence-transformers
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY agents/         ./agents/
COPY db/             ./db/
COPY gh_integration/ ./gh_integration/
COPY orchestration/  ./orchestration/

# Copy built React app from stage 1
COPY --from=frontend-builder /frontend/build ./static

# Download embedding model at build time (faster cold start)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

EXPOSE 8000

# FastAPI serves both API + React static files
CMD ["uvicorn", "gh_integration.webhook:app", "--host", "0.0.0.0", "--port", "8000"]