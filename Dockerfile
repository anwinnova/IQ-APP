# ─────────────────────────────────────────────────────────────
# IQ Platform — Dockerfile for Railway
# Uses Python 3.11 slim — no Nixpacks, no pip ensurepip error
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System packages needed by faster-whisper + PyMuPDF
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    libgomp1 \
    gcc \
    g++ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first (Docker cache layer)
COPY requirements.txt .

# Install Python packages — plain pip, no --break-system-packages needed
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Create folders the app needs at runtime
RUN mkdir -p uploads audio_files recordings interview_videos

# Expose port (Railway sets $PORT)
EXPOSE 8000

# Start command — reads $PORT from Railway environment
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
