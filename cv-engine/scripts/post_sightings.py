#!/usr/bin/env python3
"""
Backend handoff for recorded-video sightings (Phase 25).

Reads the ``events.json`` produced by ``analyze_video_file.py`` and sends each
event to the backend's ingestion endpoint (``POST /api/v1/events``). It does
NOT change any backend logic — it only speaks the existing contract.

    # validate only, no network
    python scripts/post_sightings.py ../outputs/faculty_parking/events.json --dry-run

    # real handoff
    python scripts/post_sightings.py ../outputs/faculty_parking/events.json \
        --backend-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CV_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CV_ROOT))

from events.event_schema import EventValidationError, to_backend_payload  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="POST recorded-video events to the backend")
    ap.add_argument("events_json", type=Path)
    ap.add_argument("--backend-url", default="http://localhost:8000")
    ap.add_argument("--path", default="/api/v1/events")
    ap.add_argument("--dry-run", action="store_true", help="validate payloads, send nothing")
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args()

    events = json.loads(args.events_json.read_text())
    payloads = []
    for i, e in enumerate(events):
        try:
            payloads.append(to_backend_payload(e))
        except EventValidationError as exc:
            print(f"event[{i}] INVALID: {exc}", file=sys.stderr)
            return 1
    print(f"{len(payloads)} event(s) validated against the backend contract")

    if args.dry_run:
        print(json.dumps(payloads[0], indent=2) if payloads else "(no events)")
        return 0

    import httpx

    url = args.backend_url.rstrip("/") + args.path
    ok = failed = 0
    with httpx.Client(timeout=args.timeout) as client:
        for i, p in enumerate(payloads):
            try:
                r = client.post(url, json=p)
                if r.status_code in (200, 201):
                    ok += 1
                else:
                    failed += 1
                    print(f"event[{i}] HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
            except Exception as exc:
                failed += 1
                print(f"event[{i}] failed: {exc}", file=sys.stderr)
    print(f"posted={ok} failed={failed} -> {url}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
