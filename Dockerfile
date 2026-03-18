# Stage 1: Build React frontend
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


# Stage 2: Python + FastAPI
FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy Python project files
COPY pyproject.toml ./
COPY backend/ ./backend/

# Install Python dependencies
RUN uv pip install --system --no-cache .

# Copy built frontend into backend/static
COPY --from=frontend-build /app/backend/static ./backend/static

# Create data directory (will be mounted as a volume in production)
RUN mkdir -p /data

EXPOSE 8080

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
