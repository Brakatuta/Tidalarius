# Build step for the Vue frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Run step for the Python backend
FROM python:3.13-slim
WORKDIR /app

# Install system dependencies if required (e.g., for some python packages like tidalapi or websockets)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy backend code
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Define environment variables
ENV CONFIG_DIR=/config
ENV DATA_DIR=/data
ENV PYTHONPATH=/app/backend

# Create config and data directories
RUN mkdir -p /config /data /music

# We will run using uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

