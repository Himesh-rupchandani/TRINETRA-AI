# Trinetra AI Detection Demo (PowerShell)
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "      TRINETRA AI - Vehicle & Plate Detection Demo     " -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan

Write-Host "`nRunning Vehicle & Plate Detection on Sample Images..." -ForegroundColor Green
python detect_image.py --input sample_data --model models/best.pt

Write-Host "`n[DONE] Check your outputs folder:" -ForegroundColor Cyan
Write-Host "  - outputs/annotated_images/" -ForegroundColor Green
Write-Host "  - outputs/detected_plates/" -ForegroundColor Green
