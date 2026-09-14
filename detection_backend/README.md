# TRINETRA AI — Standalone Detection Backend

A pure, self-contained computer vision & ANPR detection service. **Contains zero frontend or UI dependencies**, and is designed to be shared and integrated with **any external web, mobile, desktop, or cloud UI**.

---

## 📁 Folder Structure

```
detection_backend/
├── README.md                      # Complete documentation & UI integration guide
├── requirements.txt               # Minimal Python dependencies
├── run_server.bat                 # One-click Windows runner (starts server on port 8010)
├── run_server.sh                  # Linux / macOS runner
├── server.py                      # Standalone FastAPI REST API server for external UIs
├── cli.py                         # Standalone CLI tool to process any video from terminal
├── engine/                        # Core Computer Vision Engine
│   ├── detection/                 # YOLO11 vehicle & license plate detection
│   ├── tracking/                  # ByteTrack vehicle tracking with IoU matching
│   ├── anpr/                      # RapidOCR (ONNX), Indian plate normalizer & crop enhancer
│   └── pipeline/                  # Adaptive frame stride (5 FPS), sighting segmenter
├── models/                        # Trained Model Weights
│   ├── best.pt                    # Trained vehicle + plate YOLO11 weights (5.2 MB)
│   ├── yolo11s.pt                 # YOLO11s base weights (18.4 MB)
│   └── license-plate-finetune-v1n.pt # Fine-tuned plate model (5.2 MB)
├── footages_and_videos/           # 8 Sample CCTV Videos & Raw Footages
│   ├── detection1video.mp4
│   ├── Recording_2026-09-11_221936.mp4
│   ├── Recording_cctv_footage_yt.mp4
│   ├── VID_20260907_113743_faculty_parking.mp4
│   ├── VID_20260907_113907_bedi_chowkdi.mp4
│   ├── VID_20260907_114013_main_road.mp4
│   ├── VID_20260907_114142_madhapar_chowkdi.mp4
│   └── test_custom_yolo_video.mp4
├── evidence_frames/               # Extracted Evidence Crops & Plates (5 Scenes)
│   ├── test_detect1/
│   ├── faculty_parking/
│   ├── bedi_chowkdi/
│   ├── main_road/
│   └── cctv_footage_yt/
└── sample_client/                 # Sample integration code for other UIs
    ├── test_client.py             # Python script showing upload, polling & results
    └── test_client.html           # Simple interactive HTML page to test from any browser
```

---

## ⚡ Quick Start

### 1. Install Dependencies
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Start the API Server
On Windows:
```bash
run_server.bat
```
Or directly with Python:
```bash
python server.py
# Or: uvicorn server:app --host 0.0.0.0 --port 8010
```
Open **`http://localhost:8010/docs`** in your browser to access the interactive Swagger UI API explorer.

---

## 🖥️ Command Line (CLI) Usage

You can run detection directly on any video without starting the API server:

```bash
# Fast Turbo Mode (first 15 seconds)
python cli.py --video footages_and_videos/detection1video.mp4 --sample 15 --output results/my_run

# Full Video Analysis with 5.0 FPS surveillance stride
python cli.py --video footages_and_videos/Recording_2026-09-11_221936.mp4 --output results/recording_run
```

Output files generated in the output directory:
- `vehicle_sightings.csv`: Formatted table with tracks, plates, confidence scores, and timestamps.
- `vehicle_sightings.json`: Structured JSON for programmatic consumption.
- `annotated_video.mp4`: Universal H.264 video with bounding box overlays and plate text.
- `evidence/`: High-resolution padded vehicle crops and enhanced plate crops (`.jpg`).

---

## 🌐 REST API Reference for External UIs

The server enables full CORS (`allow_origins=["*"]`), allowing any frontend (React, Angular, Vue, Flutter, Next.js, Android, iOS) to call it without cross-origin blocks.

### 1. Start Video Detection
`POST /api/v1/detect/video`

Accepts `multipart/form-data`:
- `file` (optional): Video file to upload (`.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`).
- `video_path` (optional): Relative/absolute path to video already on the server (e.g. `footages_and_videos/detection1video.mp4`).
- `sample_seconds` (optional): Number of seconds to process (`15.0` for Turbo Mode, `0.0` for Full Video). Default: `0.0`.
- `target_fps` (optional): Analysis frame rate (Default: `5.0`).

**Response (201 Created)**:
```json
{
  "job_id": "job_20260912_142000_a1b2c3d4",
  "filename": "detection1video.mp4",
  "status": "QUEUED",
  "stage": "QUEUED",
  "sample_seconds": 15.0,
  "target_fps": 5.0,
  "created_at": "2026-09-12T14:20:00.000Z",
  "message": "Video queued for detection. Use GET /api/v1/detect/jobs/{job_id} to monitor progress."
}
```

---

### 2. Check Job Progress
`GET /api/v1/detect/jobs/{job_id}`

**Response (200 OK)**:
```json
{
  "job_id": "job_20260912_142000_a1b2c3d4",
  "status": "PROCESSING",
  "stage": "READING_NUMBER_PLATES",
  "progress_pct": 65.4,
  "frames_total": 900,
  "frames_processed": 588,
  "vehicles_detected": 420,
  "plates_detected": 28,
  "ocr_reads": 35,
  "elapsed_time_sec": 14.2
}
```
*Possible stages*: `QUEUED` -> `PROCESSING` -> `DETECTING_VEHICLES` -> `READING_NUMBER_PLATES` -> `GENERATING_RESULTS` -> `COMPLETED`.

---

### 3. Get Detection Results
`GET /api/v1/detect/jobs/{job_id}/results`

**Response (200 OK)**:
```json
{
  "job_id": "job_20260912_142000_a1b2c3d4",
  "filename": "detection1video.mp4",
  "status": "COMPLETED",
  "total_sightings": 16,
  "unique_plates": 4,
  "sightings": [
    {
      "sighting_id": 1,
      "track_id": 3,
      "vehicle_class": "car",
      "plate_number": "GJ03ER2997",
      "plate_confidence": 0.94,
      "detection_confidence": 0.88,
      "start_time": "00:02.14",
      "duration_sec": 3.4,
      "evidence_urls": {
        "vehicle_image": "/api/v1/detect/evidence/job_20260912_142000_a1b2c3d4/sighting_01_vehicle.jpg",
        "plate_image": "/api/v1/detect/evidence/job_20260912_142000_a1b2c3d4/sighting_01_plate.jpg",
        "full_frame": "/api/v1/detect/evidence/job_20260912_142000_a1b2c3d4/sighting_01.jpg"
      }
    }
  ]
}
```

---

### 4. Fetch Evidence Image (Vehicle Crop or Plate)
`GET /api/v1/detect/evidence/{job_id}/{filename}`

Streams the requested `.jpg` image directly to render in an `<img>` tag.

---

### 5. Stream Annotated Video
`GET /api/v1/detect/jobs/{job_id}/annotated`

Streams the `.mp4` video with bounding box overlays for playback in `<video>` tags.

---

### 6. Single Image Frame Detection
`POST /api/v1/detect/frame`

Accepts an image file (`file: UploadFile`) and runs instant vehicle and plate recognition for live camera snapshots.

---

## 📱 How to Integrate in Another UI

### JavaScript / React / Vue Example
```javascript
// 1. Upload video
const formData = new FormData();
formData.append('file', videoFileInput.files[0]);
formData.append('sample_seconds', '15.0'); // Turbo mode

const startRes = await fetch('http://localhost:8010/api/v1/detect/video', {
  method: 'POST',
  body: formData,
});
const { job_id } = await startRes.json();

// 2. Poll progress
const poll = setInterval(async () => {
  const statusRes = await fetch(`http://localhost:8010/api/v1/detect/jobs/${job_id}`);
  const job = await statusRes.json();
  console.log(`Progress: ${job.progress_pct}% (${job.stage})`);

  if (job.status === 'COMPLETED') {
    clearInterval(poll);

    // 3. Fetch results
    const resultsRes = await fetch(`http://localhost:8010/api/v1/detect/jobs/${job_id}/results`);
    const data = await resultsRes.json();
    console.log('Detected Vehicles & Plates:', data.sightings);
  }
}, 1000);
```

### Try the Sample HTML Client
Double-click `sample_client/test_client.html` in any browser while `server.py` is running to immediately test video upload, real-time progress bars, and rendering of detected vehicle crops and license plates!
