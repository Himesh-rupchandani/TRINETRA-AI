@echo off
echo =======================================================
echo   TRINETRA AI - Standalone Detection Backend Server
echo =======================================================
echo Starting FastAPI detection server on http://localhost:8010 ...
echo API Documentation: http://localhost:8010/docs
echo.

if exist "..\TRINETRAAI\backend\.venv\Scripts\python.exe" (
    "..\TRINETRAAI\backend\.venv\Scripts\python.exe" -m uvicorn server:app --host 0.0.0.0 --port 8010 --reload
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m uvicorn server:app --host 0.0.0.0 --port 8010 --reload
) else (
    python -m uvicorn server:app --host 0.0.0.0 --port 8010 --reload
)
pause
