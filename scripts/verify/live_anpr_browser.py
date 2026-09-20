#!/usr/bin/env python3
"""Opt-in REAL-model/browser smoke for an authorized, registered FILE camera.

Requires running ML backend + frontend (VITE_USE_MOCKS=false), and Playwright:
    pip install playwright && python -m playwright install chromium
    python scripts/verify/live_anpr_browser.py --camera-id recorded

Use an isolated test database/evidence directory and preferably a fresh camera
ID. This test only opens playback; it NEVER posts invented events, supplies an
OCR answer, changes thresholds, bypasses duplicate suppression or deletes data.
Readable, non-watchlisted footage is needed for an ordinary plate notification.
This verifies wiring on one recording, NOT live-camera accuracy/throughput.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote, urlparse


def arguments():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app-url", default="http://127.0.0.1:5173")
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--timeout", type=int, default=90, help="Seconds to wait for a real plate notification")
    parser.add_argument("--chromium-binary", help="Optional system Chromium/headless-shell executable")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--photos-only", action="store_true", help="Verify direct vehicle photos without waiting for a plate read/event")
    parser.add_argument("--output", type=Path, default=Path(".cache/live-anpr-browser"))
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error("--timeout must be 1–300 seconds")
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,50}", args.camera_id):
        parser.error("Use a registered camera ID (letters, numbers, hyphens or underscores)")
    origin = urlparse(args.app_url)
    if origin.scheme not in ("http", "https") or not origin.netloc or origin.username or origin.password:
        parser.error("--app-url must be an HTTP(S) application URL without embedded credentials")
    return args


def run(args):
    from playwright.sync_api import sync_playwright, expect

    base = args.app_url.rstrip("/")
    camera_id = args.camera_id.lower()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "passed": False, "camera_id": camera_id,
        "scope": "Real model + recorded-file playback + browser integration; not live accuracy or FPS",
        "javascript_errors": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=not args.headed, executable_path=args.chromium_binary,
            args=["--disable-gpu", "--no-zygote"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        context.on("page", lambda page: page.on("pageerror", lambda error: report["javascript_errors"].append(str(error))))
        try:
            def get_json(path):
                response = context.request.get(f"{base}/api{path}", timeout=10000)
                assert response.ok, f"{path.split('?')[0]} returned HTTP {response.status}"
                return response.json()

            cam = get_json(f"/cameras/{camera_id}")
            assert cam.get("stream_type", "").upper() == "FILE", "This smoke only opens a recorded FILE camera, never an unverified live source."
            if Path(cam.get("stream_url", "")).name == "demo_cam04.mp4":
                report["fixture_note"] = "Bundled demo alternates sample photographs; not continuous live traffic footage."
            canonical = quote(cam["camera_id"], safe="")
            event_path = f"/events?camera_id={canonical}&size=100"
            before = {event["id"] for event in get_json(event_path)["items"]}

            # Watch the Vehicle Log BEFORE playback. It must receive the new
            # row via SSE/quiet refresh; the test never clicks Refresh/reloads.
            log = context.new_page()
            log.goto(f"{base}/events?cameraId={camera_id}", wait_until="domcontentloaded")
            log.get_by_role("heading", name="Vehicle Log", exact=True).wait_for()
            camera = context.new_page()
            camera.goto(f"{base}/cameras/{camera_id}", wait_until="domcontentloaded")
            camera.get_by_role("button", name="Plate detection: On").wait_for()
            camera.wait_for_function("() => [...document.images].some(i => i.src.includes('/live/detect') && i.naturalWidth > 0)")
            gallery = camera.get_by_test_id("live-photo-evidence")
            gallery.wait_for(timeout=args.timeout * 1000)
            camera.wait_for_function("""() => {
                const photos = [...document.querySelectorAll('[data-testid="live-photo-evidence"] img')];
                return photos.length > 0 && photos.every(image => image.naturalWidth > 0);
            }""", timeout=15000)
            photo_count = gallery.locator("article").count()
            assert 1 <= photo_count <= get_json(f"/cameras/{camera_id}/anpr")["max_vehicles"]
            report["direct_photo_count"] = photo_count
            report["photos_do_not_require_a_log_selection"] = True
            if args.photos_only:
                first_capture = gallery.locator("article").first.get_attribute("data-capture-id")
                camera.wait_for_function("""old => document.querySelector('[data-capture-id]')?.getAttribute('data-capture-id') !== old""",
                                         arg=first_capture, timeout=15000)
                report["photo_auto_refresh"] = True
                camera.screenshot(path=str(args.output / "live-photo-evidence.png"), timeout=10000)
            else:
                toast = camera.get_by_text(re.compile(r"^Plate read · ")).first
                toast.wait_for(timeout=args.timeout * 1000)
                title = toast.inner_text()
                plate = title.split(" · ")[1]
                report["notification"] = title

                added = [event for event in get_json(event_path)["items"]
                         if event["id"] not in before and event["plate_number"] == plate]
                assert added, "Notification does not correspond to a newly persisted camera sighting"
                event = added[0]
                assert event["plate_status"] in ("HIGH", "LOW_CONFIDENCE") and event["video_file"]
                assert event["video_offset_sec"] is not None
                report.update(event_id=event["id"], plate=plate, plate_status=event["plate_status"],
                              recording=event["video_file"], offset_seconds=event["video_offset_sec"])
                if event["video_file"] == "demo_cam04.mp4":
                    report["fixture_note"] = "Bundled demo alternates sample photographs; not continuous live traffic footage."

                # The same persisted event must also be offered to the camera
                # overlay, not just to a toast. Poll lightweight cached state only.
                camera.wait_for_function("""async ({id, eventId, plate}) => {
                    const res = await fetch(`/api/cameras/${id}/anpr`);
                    if (!res.ok) return false;
                    const data = await res.json();
                    return data.detections.some(d => d.event_id === eventId && d.plate_number === plate);
                }""", arg={"id": camera_id, "eventId": event["id"], "plate": plate}, timeout=4000, polling=100)
                report["overlay_event_matches"] = True
                row = log.locator(f'tr[data-event-id="{event["id"]}"]')
                row.wait_for(timeout=5000)
                report["automatic_log_refresh"] = True
                camera.screenshot(path=str(args.output / "camera-notification.png"), timeout=10000)

                # Exercise navigation while ALREADY on /events too; changing only
                # URL query parameters must update the mounted page's filters.
                log.get_by_text(title, exact=True).locator("..").get_by_role("button", name="View in Vehicle Log").click()
                expect(log.locator("#f-plate")).to_have_value(plate)
                expect(log.locator("#f-camera")).to_have_value(camera_id)
                row.wait_for(timeout=5000)
                report["notification_action_updates_filters"] = True
                log.screenshot(path=str(args.output / "vehicle-log.png"), timeout=10000)

                ref = event["evidence_ref"]
                assert ref and ref.startswith("live/"), "Expected a real live-worker evidence crop"
                evidence = context.request.get(f"{base}/api/evidence/{quote(ref, safe='/')}")
                assert evidence.ok and evidence.headers.get("content-type", "").startswith("image/")
                assert len(evidence.body()) > 100
                report["evidence_served"] = True
            assert not report["javascript_errors"], "Browser JavaScript errors occurred"
            report["passed"] = True
        except Exception as exc:
            report["error"] = str(exc)
            raise
        finally:
            (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            browser.close()
    print(json.dumps(report, indent=2))
    print(f"Saved report/screenshots to {args.output}. No accuracy or deployment-speed guarantee is implied.")


if __name__ == "__main__":
    run(arguments())
