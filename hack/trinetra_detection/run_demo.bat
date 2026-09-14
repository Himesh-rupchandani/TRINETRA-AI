@echo off
title Trinetra AI - Detection Demo
echo ========================================================
echo       TRINETRA AI - Vehicle & Number Plate Detection
echo ========================================================
echo.
echo Checking Python environment...
python --version
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

echo.
echo Running Vehicle & Plate Detection on Sample Images...
python detect_image.py --input sample_data --model models/best.pt

echo.
echo [DONE] Check the outputs folder:
echo   - outputs\annotated_images\
echo   - outputs\detected_plates\
echo.
pause
