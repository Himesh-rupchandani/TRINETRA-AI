#!/usr/bin/env bash
echo "======================================================="
echo "  TRINETRA AI - Standalone Detection Backend Server"
echo "======================================================="
echo "Starting FastAPI detection server on http://localhost:8010 ..."
echo "API Documentation: http://localhost:8010/docs"
echo ""

python -m uvicorn server:app --host 0.0.0.0 --port 8010
