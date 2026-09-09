# Number-plate usage: every plate in a video, and how long it was there

Upload one video → the pipeline finds the vehicles, reads the number plates,
and gives you a list of every plate with **how long it was in shot**.

Two ways to use it:

* **Web UI** — Video Analysis page (upload a clip, run the analysis, the plate
  table appears under the video list, with a CSV button).
* **Command line** — `python -m scripts.analyze_video_plates <video>` for batch
  or offline work.

---

## The three time figures

For each plate the report gives three different numbers, because "how long was
it there" can mean three different things:

| Column | Meaning | Use it when you want to know… |
| --- | --- | --- |
| **In shot** (dwell) | `last sighting − first sighting` | …how long the vehicle was in the area |
| **On screen** | time it was *actually* tracked | …how long we really had eyes on it |
| **Entries** | number of separate appearances | …whether it came and went |

**In shot** always ≥ **on screen**. Example: a car appears at 0:05, is hidden
behind a bus for 20 s, and is last seen at 1:00.

* in shot = **55 s** — it was in the area the whole time
* on screen = **35 s** — we only actually saw it for that long
* entries = **1** — the tracker bridged the occlusion

If it had *left* the frame and come back later, entries would be **2** and each
stretch would be listed separately under the row.

Also reported: entry/exit timestamps, the share of the video each plate
occupies, the vehicle class, OCR confidence, and whether it hit the watchlist.

### Where the numbers come from

Nothing is estimated or extrapolated. The analysis loop records, for every
tracked vehicle, the first and last frame in which the detector actually saw it
and how many sampled frames it was tracked for. One sampled frame covers
`ANALYSIS_EVERY_N_FRAMES / fps` seconds — that is the resolution of every
figure in the report (0.5 s at the default 5-frame sampling of a 10 fps clip).

Two details that matter for correctness:

* Only frames where the detector **matched** the vehicle count as a sighting.
  The tracker deliberately coasts for a few frames so a vehicle is not lost
  behind a brief occlusion; counting those coasted frames would inflate every
  dwell time by ~4 s.
* A vehicle whose plate cannot be read is **not dropped and not guessed**. It is
  listed separately as `UNREADABLE` with its measured time, so you can see that
  something was there and go look at the evidence crop.

---

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/analysis/plate-usage?video_id=…` | the report as JSON |
| `GET` | `/api/analysis/plate-usage.csv?video_id=…` | the same table as CSV |
| `GET` | `/api/analysis/videos/{id}/detections` | raw detections of one video |

`video_id` is optional — leave it out and you get the most recently added
video, so the one-clip workflow needs no extra lookup.

```jsonc
{
  "video":   { "source_name": "cam1.mp4", "duration_sec": 12.0, … },
  "summary": { "unique_plates": 3, "longest_plate": "GJ01AB1234",
               "longest_dwell_sec": 10.0, "watchlist_hits": 1, … },
  "plates": [
    { "plate": "GJ01AB1234", "vehicle_class": "car",
      "first_seen": "00:00:00", "last_seen": "00:00:09",
      "dwell_sec": 10.0,   "dwell_label": "00:00:10",
      "visible_sec": 10.0, "visible_label": "00:00:10",
      "appearances": 1, "presence_pct": 83.3,
      "plate_status": "HIGH", "watchlist_match": true,
      "segments": [ { "start": "00:00:00", "end": "00:00:09", … } ] }
  ],
  "unreadable": [ … ],      // vehicles tracked, plate not readable
  "notes":      [ … ]       // caveats, e.g. "analysis still running"
}
```

---

## Command line

```bash
cd TRINETRAAI/backend

python -m scripts.analyze_video_plates /path/to/clip.mp4

# keep the artefacts, and measure more finely (every 2nd frame)
python -m scripts.analyze_video_plates clip.mp4 --every-n 2 \
       --csv plates.csv --json plates.json

# also keep the video + detections in the database so the web UI can show it
python -m scripts.analyze_video_plates clip.mp4 --keep
```

Output:

```
NUMBER PLATES (longest in shot first)
PLATE           CLASS        IN SHOT  ON SCREEN     ENTRY      EXIT  ENTRIES
GJ01AB1234      car         00:00:10   00:00:10  00:00:00  00:00:09        1
DL08EF9012      car         00:00:08   00:00:08  00:00:04  00:00:11        1
MH12XY4567      car         00:00:03   00:00:03  00:00:02  00:00:04        1
```

The script prints which pipeline stages are actually available before it
starts, so a missing model is never mistaken for "no vehicles found".

---

## RF-DETR

Vehicle detection uses **RF-DETR** ([roboflow/rf-detr](https://github.com/roboflow/rf-detr)),
Roboflow's real-time DETR (SOTA on COCO), with the previous YOLO11 detector kept
as an automatic fallback.

```bash
pip install rfdetr                       # pulls torch + torchvision
```

Configuration (backend `.env`, or environment variables):

| Setting | Default | Meaning |
| --- | --- | --- |
| `DETECTOR_BACKEND` | `auto` | `auto` = RF-DETR if installed else YOLO11; `rfdetr`; `yolo` |
| `RFDETR_VARIANT` | `base` | `nano` \| `small` \| `medium` \| `base` \| `large` |
| `RFDETR_PRETRAIN_WEIGHTS` | *(empty)* | path to your own checkpoint; empty = published COCO weights |
| `RFDETR_RESOLUTION` | `0` | square inference size; `0` = the variant's default |
| `RFDETR_ENABLED` | `true` | set `false` to force YOLO11 even when rfdetr is installed |
| `PLATE_RFDETR_MODEL_PATH` | *(empty)* | optional **fine-tuned** RF-DETR plate detector |

`auto` prefers RF-DETR and silently falls back to YOLO11 if RF-DETR is missing
or fails to load, so installing it can only ever improve results — never break
a working deployment.

### Using RF-DETR for plate localisation too

The COCO checkpoints find vehicles, not plates. To use RF-DETR as the plate
localiser, fine-tune it on your own plate data and point
`PLATE_RFDETR_MODEL_PATH` at the checkpoint. Until then the classical OpenCV
plate proposer is used, exactly as before — the stage is skipped cleanly.

---

## Verifying it works

```bash
cd TRINETRAAI/backend
../../.venv/bin/python -m pytest tests/test_plate_usage.py tests/test_rfdetr_detector.py -q

# end-to-end on real pixels: real plate localisation + real OCR + real timing
python -m scripts.verify_plate_usage --show-csv
```

`scripts/verify_plate_usage.py` renders a clip with three vehicles carrying
readable plates, runs the production pipeline over it, and checks every measured
time against exact ground truth. Only the vehicle *detector* is scripted (it
returns the ground-truth boxes) so the check needs no model download.
