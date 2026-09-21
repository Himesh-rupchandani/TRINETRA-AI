# ==============================================================================
# TRINETRA AI - Enterprise Computer Vision & CCTV Backend Dockerfile
# ==============================================================================

FROM python:3.11-slim

# System dependencies for OpenCV, FFmpeg, and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies first for efficient layer caching.
# The image is the FULL deployment: it must decode frames and run ANPR, so it
# takes requirements-ml.txt (which also installs the core API set). For an
# API-only image, swap the file and drop ffmpeg/libgl from the apt line.
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements-ml.txt

# Copy application source
COPY . .

# Set runtime environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    APP_ENV=production \
    DEMO_MODE=false

EXPOSE 8000

# Container healthcheck against /api/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Launch uvicorn ASGI production server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
