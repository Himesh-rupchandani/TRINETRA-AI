"""
TRINETRA AI — Sample Python Client for External UIs.

Shows how to:
1. Check server health
2. Upload a video for detection (Turbo Mode: 15 seconds)
3. Poll real-time progress
4. Retrieve vehicle sightings, confidence scores, and evidence image URLs
"""
import time
import requests

SERVER_URL = "http://localhost:8000"


def main():
    print(f"Connecting to detection backend at {SERVER_URL}...")
    try:
        health = requests.get(f"{SERVER_URL}/health", timeout=5).json()
        print(f"Server Status: {health.get('status')} | Service: {health.get('service')}")
    except Exception as e:
        print(f"Could not connect to server at {SERVER_URL}: {e}")
        print("Please start the server first using: python server.py or run_server.bat")
        return

    # List footages available on server
    videos_res = requests.get(f"{SERVER_URL}/api/v1/videos").json()
    videos = videos_res.get("videos", [])
    print(f"\nAvailable footages on server ({len(videos)}):")
    for v in videos[:5]:
        print(f" - {v['filename']} ({v['size_mb']} MB)")

    # Choose a video to test
    video_to_test = videos[0]["filename"] if videos else "detection1video.mp4"
    print(f"\nStarting detection on: {video_to_test} in Turbo Mode (15s sample)...")

    # Start detection job via local path
    start_resp = requests.post(
        f"{SERVER_URL}/api/v1/detect/video",
        data={"video_path": video_to_test, "sample_seconds": 15.0, "target_fps": 5.0},
    ).json()

    job_id = start_resp["job_id"]
    print(f"Job started: {job_id}")

    # Poll progress
    start_time = time.time()
    while True:
        status_data = requests.get(f"{SERVER_URL}/api/v1/detect/jobs/{job_id}").json()
        status = status_data.get("status")
        stage = status_data.get("stage")
        pct = status_data.get("progress_pct", 0)
        veh = status_data.get("vehicles_detected", 0)
        ocr = status_data.get("ocr_reads", 0)
        elapsed = round(time.time() - start_time, 1)

        print(f"\r[{stage:24s}] {pct:5.1f}% | Vehicles: {veh} | OCR reads: {ocr} ({elapsed}s)", end="", flush=True)

        if status in ("COMPLETED", "FAILED"):
            break
        time.sleep(1.0)

    print("\n\nRetrieving detection results...")
    results = requests.get(f"{SERVER_URL}/api/v1/detect/jobs/{job_id}/results").json()
    sightings = results.get("sightings", [])

    print(f"\n=======================================================")
    print(f"  DETECTION RESULTS ({len(sightings)} Sightings)")
    print(f"=======================================================")
    for i, s in enumerate(sightings, 1):
        plate = s.get("plate_number")
        conf = s.get("plate_confidence", 0)
        v_class = s.get("vehicle_class")
        t_start = s.get("start_time")
        v_img = s.get("evidence_urls", {}).get("vehicle_image")
        p_img = s.get("evidence_urls", {}).get("plate_image")

        print(f"#{i:02d} [{v_class.upper():10s}] Track {s.get('track_id')} | Plate: {plate:12s} ({conf*100:.0f}%) | Time: {t_start}")
        if v_img:
            print(f"     Vehicle Crop: {SERVER_URL}{v_img}")
        if p_img:
            print(f"     Plate Crop:   {SERVER_URL}{p_img}")

    print(f"=======================================================\n")


if __name__ == "__main__":
    main()
