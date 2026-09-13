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

3. **Confidence / NMS / resolution tune karna:**
   ```bash
   python detect_image.py --input sample_data --conf 0.35 --iou 0.45 --imgsz 960
   ```
   - `--conf` (default **0.35**) — neeche ka value background/pedestrian par
     false `vehicle` boxes banata hai.
   - `--iou` (default **0.45**) — ek hi vehicle par duplicate boxes hatata hai.
   - `--imgsz` (default **960**) — door/parked vehicles alag-alag box paate hain.
   - `--vehicle-model none` — vehicle boxes bhi `--model` se hi (purana behaviour).

**Output:**
- Annotated images: `outputs/annotated_images/`
- Cropped Number Plates: `outputs/detected_plates/`

---

### 🔬 Multi-scale: doosra pass, native resolution pe (default ON)

`detect_image.py` aur `detect_video.py` ab har frame ko **do baar** dekhte hain:
ek baar poora frame (imgsz 960), aur ek baar frame ko **vertical strips** me kaat
kar har strip ko uski **apni native resolution** par. Kyun? 1280-wide frame ko
960 me squeeze karne par har vehicle 75% ho jaata hai — do parked vehicles ka box
merge ho kar ek bada rectangle ban jaata hai, aur 20 px ki door wali car model ki
pahunch se bahar ho jaati hai. Strip native resolution par hai to dono theek.

- Boxes me **koi padding/jaadu nahi**: crop ka offset wapas jodna aur frame ke
  bahar ka hissa kaatna — bas. Jo box crop ki *kaati* edge se chipakta hai (frame
  ki edge se nahi) use drop kar diya jaata hai, kyun ki wahi vehicle padosi strip
  pura dekhta hai.
- Do passes se aaya hua duplicate "ek hi vehicle, do box" nahi banta: IoU +
  containment (size guard ke saath) se one vehicle → one box.
- Isse boxes **tighter** bhi hote hain, bade nahi. Is repo ke 33 hand-checked
  frames par (CPU): **7.1 → 9.1 vehicle/frame, aur mean box area 2.87% → 2.24%**.
- Cost: ~3x inference (yeh offline tools hain, isliye value quality par lagta hai).
  Tez banana ho: `--no-multiscale`, ya poore process ke liye `TRINETRA_MULTISCALE=0`.
- `detect_webcam.py` me ise **off** rakha gaya hai — live view 2x inference ka
  intezaar nahi kar sakta; wahan frame-rate hi quality hai.

### Option C: Video Detection (`detect_video.py`)
Kisi bhi video file par vehicle aur number plate detect karne ke liye:
```bash
python detect_video.py --video "path/to/your_video.mp4"
```

**Custom Options (Optional):**
```bash
python detect_video.py --video my_video.mp4 --conf 0.35 --iou 0.45 --imgsz 960     --stride 2 --output-video outputs/my_result.mp4
```
- `--video` : Input video path (Required)
- `--conf` : Confidence threshold (default `0.35`)
- `--iou` : NMS IoU threshold (default `0.45`) — duplicate boxes per vehicle
- `--imgsz` : Inference resolution (default `960`) — tight boxes for small/distant vehicles
- `--vehicle-model` : Vehicle boxes ka weight (`none` = sirf `--model`)
- `--stride` : Frame stride (default `2`, e.g. 60fps video ko 30fps par process karega)
- `--max-frames` : Sirf pehle N frames test karne ke liye (e.g. `--max-frames 300`)
- `--output-video` : Annotated output video save karne ka path

> **Vehicle boxes ka model (zaroori note):** har box ka rectangle model ke
> apne `xyxy` se aata hai — koi padding, fixed size ya manual shrink nahi.
> Isliye *tight* boxes ke liye vehicle boxes ek **per-class** weight se nikalte
> hain (`car / motorcycle / bus / truck`: repo ka `TRINETRAAI/backend/yolo11s.pt`,
> warna `models/yolo11n.pt`), aur `best.pt` ka `vehicle` class sirf tab use hota
> hai jab koi per-class weight na mile. Wajah: `best.pt` ek single coarse
> `vehicle` class par train hua hai, jisme paas-paas khade 3-4 bikes ek hi
> label ban jaate hain — measured: ek box ne 1280x720 frame ka **74.9%** cover
> kiya tha. Number-plate class (aur plate crops) unchanged `best.pt` se hi aate
> hain, `conf 0.25 @ imgsz 640` par — ANPR behaviour badalta hi nahi hai.

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

4. **Live view ke settings (default tuned hain - wahi jo offline video pass use karta hai):**
   ```bash
   python detect_webcam.py --source 0 --conf 0.35 --iou 0.45 --imgsz 960
   ```
   `--imgsz 960` live view ko offline analysis ke barabar rakhta hai (door ki cars
   bhi milti hain). Kamzor CPU par `--imgsz 640` karein - box tight hi rahenge,
   bas door ke vehicles kam dikhenge. `--vehicle-model` se vehicle boxes ka weight
   badla ja sakta hai (default: `models/best.pt` coarse `vehicle` class hone par
   apne aap per-class weight par switch ho jata hai).

5. **Bina monitor (headless server / NVR) par live stream:**
   ```bash
   python detect_webcam.py --source "rtsp://.../stream" --no-display --save /tmp/live_annotated.mp4
   ```
   `--no-display` (ya koi bhi GUI na hone par apne aap) window kholne ki koshish
   nahi karta, warna OpenCV bina GTK wale server par crash ho jata hai.
   `--max-frames 100` se ek bounded test run bhi ho sakta hai.

*Controls: Press **`q`** to quit | Press **`s`** to save current snapshot frame.*

---

## 🐍 Python Code Me Kaise Use Karein (API Reference)

Aap is detection module ko kisi bhi dusre Python script ya project me as a library import kar sakte hain:

```python
import cv2
from core.detector import VehiclePlateDetector
from core.visualizer import Visualizer

# 1. Initialize Detector (vehicle boxes: per-class weight; plate boxes: best.pt)
detector = VehiclePlateDetector(model_path="models/best.pt", conf_threshold=0.35,
                                iou_threshold=0.45, imgsz=960)

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
- **Vehicle boxes at runtime**: ek per-class COCO YOLO11 weight (`yolo11s` /
  `yolo11n`) — class ids `2 car, 3 motorcycle, 5 bus, 7 truck` — jab tak ki
  `--vehicle-model none` na ho. Plates hamesha `best.pt` se.
- **Formats Included**:
  - PyTorch weights: `models/best.pt` (PyTorch / GPU / CPU inference)
  - ONNX weights: `models/best.onnx` (Cross-platform inference)
