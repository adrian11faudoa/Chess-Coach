# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install --legacy-peer-deps

COPY frontend/ ./
RUN npm run build
# Output lands in /app/backend/static (per vite.config.js outDir)


# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM python:3.11-slim AS final

# Install Stockfish from package manager (smallest option for containers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    stockfish \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./

# Copy built frontend from stage 1
COPY --from=frontend-build /app/backend/static ./static

# Create data directory for SQLite
RUN mkdir -p /data

# Non-root user for security
RUN useradd -m appuser && chown -R appuser /app /data
USER appuser

# Runtime environment
ENV STOCKFISH_PATH=/usr/games/stockfish \
    DB_PATH=/data/chesscoach.db \
    HOST=0.0.0.0 \
    PORT=8000 \
    WORKERS=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["sh", "-c", "uvicorn main:app --host $HOST --port $PORT --workers $WORKERS"]
