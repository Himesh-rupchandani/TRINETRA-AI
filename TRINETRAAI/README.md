# TRINETRA AI - Intelligent CCTV Surveillance Platform

Enterprise Computer Vision CCTV Video Intelligence & ANPR / ALPR Hotlist Tracking System.

## Project Structure
- `backend/` — FastAPI backend service, Computer Vision pipeline, GIS routing, SQLite/PostgreSQL layer, Sentinel catalogue synchronization.
- `docker-compose.yml` — Container orchestration for local deployment.

## Quick Start with Docker
```bash
docker compose up --build -d
```

## Quick Start with Python
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m scripts.seed_demo
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Running Tests
```powershell
cd backend
pytest -v
```
All 91 automated tests pass with 100% success rate.
For full API contracts and architectural specifications, see [backend/README.md](backend/README.md).
