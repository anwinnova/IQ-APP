# ─────────────────────────────────────────────────────────────
# IQ Platform — Dockerfile
# Works on: Render (free), Railway, Fly.io, any Docker host
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System packages needed by faster-whisper + PyMuPDF + gTTS
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

# Create runtime folders
RUN mkdir -p uploads audio_files recordings interview_videos

# Startup script — uses /app/data persistent disk on Render if available
RUN printf '#!/bin/sh\n\
if [ -d "/app/data" ]; then\n\
  mkdir -p /app/data/audio_files /app/data/recordings /app/data/uploads\n\
  [ -d /app/audio_files ] && [ ! -L /app/audio_files ] && rm -rf /app/audio_files && ln -s /app/data/audio_files /app/audio_files\n\
  [ -d /app/recordings ]  && [ ! -L /app/recordings ]  && rm -rf /app/recordings  && ln -s /app/data/recordings  /app/recordings\n\
  [ -d /app/uploads ]     && [ ! -L /app/uploads ]     && rm -rf /app/uploads     && ln -s /app/data/uploads     /app/uploads\n\
  export DB_PATH="${DB_PATH:-prepsense.db}"
fi\n\
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}\n' > /app/start.sh \
  && chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
