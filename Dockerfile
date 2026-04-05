# ─────────────────────────────────────────────────────────────
# IQ Platform — Dockerfile for Railway
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

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Create folders the app needs at runtime
RUN mkdir -p uploads audio_files recordings /data

# Pre-download Whisper model during build so first request is instant
# Uses /tmp/whisper_models — cached in the Docker layer
RUN python3 -c "
from faster_whisper import WhisperModel
print('Pre-downloading Whisper base model...')
m = WhisperModel('base', device='cpu', compute_type='int8', download_root='/tmp/whisper_models')
print('Whisper model ready.')
" || echo "Whisper pre-download failed — will download on first use"

EXPOSE 8000

# Start with 2 workers for performance — Railway gives enough RAM
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
