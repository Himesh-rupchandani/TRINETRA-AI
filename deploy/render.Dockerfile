# Alternative for an EXISTING Render Docker service.
# Root Directory: blank; Dockerfile Path: deploy/render.Dockerfile; Context: .
FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY TRINETRAAI/backend/requirements.txt TRINETRAAI/backend/requirements-ml.txt /app/TRINETRAAI/backend/
COPY scripts/ensure_headless_opencv.py scripts/render_preflight.py /app/scripts/
RUN python -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r TRINETRAAI/backend/requirements-ml.txt \
    && python scripts/ensure_headless_opencv.py \
    && python scripts/render_preflight.py --imports-only
COPY TRINETRAAI/backend /app/TRINETRAAI/backend/
COPY trinetra_detection/models/yolo11n.pt trinetra_detection/models/best.pt /app/trinetra_detection/models/
COPY scripts/render_start.sh /app/scripts/render_start.sh
ENV APP_ENV=production DEBUG=false DEMO_MODE=false DEMO_ALERTS_ENABLED=false \
    AUTO_SEED_DEMO=false AUTO_START_CAMERAS=false TRINETRA_API_ONLY=0
WORKDIR /app/TRINETRAAI/backend
EXPOSE 10000
CMD ["bash", "/app/scripts/render_start.sh"]
