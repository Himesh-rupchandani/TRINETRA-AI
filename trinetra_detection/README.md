# 🚗 TRINETRA AI - Standalone Detection Module

Yeh ek **completely independent, self-contained** detection package hai jisme **Vehicle & Number Plate Detection** ka pura A to Z setup shamil hai. Isme database, frontend ya backend ki koi jarurat nahi hai. Aapka teammate is folder ko direct run kar sakta hai.

---

## 📁 Folder Structure (Kya-Kya Shamil Hai)

```text
trinetra_detection/
├── models/
│   ├── best.pt                # Trained YOLO11 model (Vehicle + Number Plate detector)
│   ├── best.onnx              # Portable ONNX model for high-speed inference
│   ├── yolo11n.pt             # Base YOLO11 model (backup)
│   └── dataset_classes.yaml   # Class mapping (0: vehicle, 1: number_plate)
├── core/
│   ├── __init__.py            # Python package init
│   ├── detector.py            # Reusable VehiclePlateDetector Python class
│   └── visualizer.py          # Bounding boxes, labels, and overlay banner renderer
├── sample_data/               # Ready-to-test sample car & license plate images
│   ├── sample_1.jpg
│   ├── sample_2.jpg
│   └── sample_3.jpg
├── outputs/
│   ├── annotated_images/      # Detection bounding box wali output photos
│   ├── detected_plates/       # Automatically cropped number plate photos
│   └── annotated_frames/      # Key annotated snapshot frames from video/webcam
├── detect_image.py            # Image ya folder of images par detection chalane ki script
├── detect_video.py            # Kisi bhi video (.mp4, .avi) par detection chalane ki script
├── detect_webcam.py           # Live webcam ya RTSP CCTV camera stream detection script
├── requirements.txt           # Python dependencies list
├── run_demo.bat               # Windows 1-Click double-click demo runner
├── run_demo.ps1               # PowerShell demo script
└── README.md                  # Complete documentation
```

---

## 🚀 Quick Setup (2 Minutes)

### 1. Requirements Install Karein
Apne terminal ya command prompt me `trinetra_detection` folder ke andar navigate karein aur run karein:
```bash
pip install -r requirements.txt
```

---

## 💻 How to Run (Kaise Chalayein)

### Option A: 1-Click Demo (Sabse Aasan)
Windows par simply **`run_demo.bat`** par double click karein ya PowerShell me run karein:
```powershell
.\run_demo.ps1
```
Yeh automatically sample images par detection run karega aur results `outputs/` folder me save kar dega!

---

### Option B: Image Detection (`detect_image.py`)
1. **Sample images folder par detection chalana:**
   ```bash
   python detect_image.py --input sample_data
   ```

2. **Kisi specific image par detection chalana:**
   ```bash
   python detect_image.py --input path/to/your/car.jpg
   ```

3. **Confidence threshold change karna (default 0.25):**
   ```bash
   python detect_image.py --input sample_data --conf 0.35
   ```

**Output:**
- Annotated images: `outputs/annotated_images/`
- Cropped Number Plates: `outputs/detected_plates/`

---

### Option C: Video Detection (`detect_video.py`)
Kisi bhi video file par vehicle aur number plate detect karne ke liye:
```bash
python detect_video.py --video "path/to/your_video.mp4"
```

**Custom Options (Optional):**
```bash
python detect_video.py --video my_video.mp4 --conf 0.30 --stride 2 --output-video outputs/my_result.mp4
```
- `--video` : Input video path (Required)
- `--conf` : Confidence threshold (default `0.25`)
- `--stride` : Frame stride (default `2`, e.g. 60fps video ko 30fps par process karega)
- `--max-frames` : Sirf pehle N frames test karne ke liye (e.g. `--max-frames 300`)
- `--output-video` : Annotated output video save karne ka path

---

### Option D: Live Webcam / CCTV Stream (`detect_webcam.py`)
1. **Laptop webcam (Camera 0) par live detection:**
   ```bash
   python detect_webcam.py
   ```

2. **External USB webcam (Camera 1):**
   ```bash
   python detect_webcam.py --source 1
   ```

3. **RTSP CCTV Camera Stream:**
   ```bash
   python detect_webcam.py --source "rtsp://admin:password@192.168.1.100:554/stream"
   ```
*Controls: Press **`q`** to quit | Press **`s`** to save current snapshot frame.*

---

## 🐍 Python Code Me Kaise Use Karein (API Reference)

Aap is detection module ko kisi bhi dusre Python script ya project me as a library import kar sakte hain:

```python
import cv2
from core.detector import VehiclePlateDetector
from core.visualizer import Visualizer

# 1. Initialize Detector
detector = VehiclePlateDetector(model_path="models/best.pt", conf_threshold=0.25)

# 2. Load any image
image = cv2.imread("sample_data/sample_1.jpg")

# 3. Detect objects
detections = detector.detect(image)

for det in detections:
    print(f"Found {det.class_name} with confidence {det.confidence:.2f} at {det.bbox}")

    # Number plate crop karna
    if det.class_name == "number_plate":
        plate_crop = det.crop(image)
        cv2.imwrite("my_plate.jpg", plate_crop)

# 4. Draw boxes and banner
annotated = Visualizer.draw_detections(image, detections)
annotated = Visualizer.draw_banner(annotated, title="TRINETRA AI", info_text="Live Inference")
cv2.imwrite("annotated.jpg", annotated)
```

---

## 🎯 Model Details
- **Trained Architecture**: Ultralytics YOLO11 Fine-tuned
- **Classes**:
  - `0`: `vehicle` (Cars, SUVs, Bikes, Buses, Trucks)
  - `1`: `number_plate` (High-precision license plate bounding box)
- **Formats Included**:
  - PyTorch weights: `models/best.pt` (PyTorch / GPU / CPU inference)
  - ONNX weights: `models/best.onnx` (Cross-platform inference)
