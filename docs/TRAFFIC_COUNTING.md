# Traffic observations — phase one

This adds **motion-aware tracking, per-camera line/zone configuration, and current-session counters**. It does not add wrong-way, restricted-zone violation alerts, speed enforcement, challans or a traffic-light detector.

## Using it

1. Open a configured camera with **Plate detection: On**.
2. Photos still appear immediately. The **Traffic observations · current session** panel sits below the player/photo workflow.
3. Expand **Counting line / zone settings**. Choose no rule, line crossing, or zone entry; select horizontal/vertical movement and a direction filter.
4. Adjust percentages against the video overlay: **yellow is an unsaved preview**, cyan is saved geometry. Lines have an adjustable position and span; zones are normalized rectangles. SVG `meet` aligns them with the same letterboxing as the video.
5. Save to persist the settings for that camera. The inference owner applies the revision on its next accepted sample and starts a fresh counting session. Other cameras, plate votes, notifications and saved sightings are unaffected.
6. **Reset session counts** also applies at the next sample; it never deletes saved evidence or resets plate agreement. Visible, previously confirmed tracks may immediately become observations in the new session.

The dashboard has a separate **Traffic observations — current camera sessions** table. It shows source provenance, observed class counts, qualifying crossings/entries, actual sample cadence and stale/error state. Recorded and live sessions are not summed into a fabricated network total. Existing Vehicle Log / plate-read KPIs remain separate.

## What a count means

- **Visible in last sample:** actual matched detections, not Kalman-predicted boxes.
- **Observed tracks:** a track has at least two real detections. Class is counted once per track/session. This is **not a count of unique registrations or guaranteed unique physical vehicles**; identity switches can still occur.
- **Line crossing:** two stable sides of a finite line segment, with a 1% deadband against jitter. A jump across the line between eligible samples can count even if no sample lands directly on the line.
- **Zone entry:** outside → inside, or a same-track segment crossing the zone interior between eligible samples. First seeing a vehicle already inside is not an entry. Boundary tangency is not an entry.
- At most **one qualifying crossing/entry per track/session**. Parking on the boundary and repeated frames do not repeatedly increment the count.
- The direction filter is image-relative: down/up for horizontal lines and right/left for vertical lines. It is **only a counting filter, never a wrong-way rule**.
- Geometry is evaluated only on fresh, observed positions; predictions, frozen timestamps, long gaps and scene/source changes cannot create crossings by interpolation.

## Limits and persistence

**Settings are persisted; counters are observation-session state, not a historical/day-total database.** Counters reset on source handover/reconnect, video loop/seek, resolution/scene changes, long sampling gaps, settings changes, an explicit reset, idle-state eviction or backend restart. The UI exposes the session start/reason.

This is sampled monitoring. At the default 1-second cadence, fast vehicles can appear and disappear between samples. Complete traffic counts require validated footage, an adequate tracking cadence and appropriate hardware. Do not represent these counters as a full traffic census or certified enforcement evidence.

Counting and OCR have separate budgets:

| Setting | Default | Purpose |
| --- | ---: | --- |
| `LIVE_ANPR_TRACKER` | `motion` | In-repository PTS-aware Kalman/two-stage-IoU tracker; `iou` retains the previous lightweight association for rollback |
| `LIVE_ANPR_MAX_TRACKED_VEHICLES` | 32 | Maximum detector observations admitted to tracking per sample |
| `LIVE_ANPR_MAX_VEHICLES` | 3 | Maximum current tracks used for OCR, photo preview and live ANPR boxes |
| `LIVE_ANPR_SAMPLE_SECONDS` | 1 | Shared sampling cadence; counting does not secretly run another model/frame loop |

The detector and its confidence threshold are unchanged. One YOLO inference supplies both paths. Active motion tracks are bounded to four times the observation budget (minimum 32); retired counter state is pruned. At capacity, fresh observations take priority over lost predictions. The UI flags an exceeded observation budget. No per-frame count rows are inserted into the database.

Use **one ASGI process**, as for live ANPR/photo caching. Distributed counters or durable daily aggregates need a separate persistence/shared-state design. Keep configuration endpoints behind the deployment's trusted/authenticated operator boundary.

## Code and provenance

The implementation reuses TRINETRA's existing `cv-engine/tracking/vehicle_tracker.py` logic, not third-party application source. Its canonical numpy-only module is now `TRINETRAAI/backend/app/services/motion_tracker_core.py` so backend-only Docker deployments include it. The standalone cv-engine keeps a compatibility import and the same public tracker API; run it from a full repository checkout.

`live_tracker.py` adapts raw observations to the existing ANPR pipeline. Immediate photo previews remain enabled on the first detection; OCR agreement and counting confirmation are independent. Predictions can keep an identity alive but are never used as captured evidence or crossing positions.

The two reviewed references were [Car_counting](https://github.com/natee-s/Car_counting) and [AI-Traffic-Violation-Monitoring-System](https://github.com/HadeedJalani/AI-Traffic-Violation-Monitoring-System). Only general tracking/counting/configuration ideas informed this phase. **No source, model weights, sample videos or assets were copied from those repositories**, and no Streamlit/second web application was added. Their unclear licensing is not treated as permission to copy their code.

## API

Both `/api` and `/api/v1` support:

- `GET /cameras/{id}/traffic-config`: persisted normalized configuration and revision (default crossing mode `off`).
- `PUT /cameras/{id}/traffic-config`: validate/save that camera's configuration; unknown fields, nonfinite/out-of-range positions and reversed/empty geometry are rejected.
- `POST /cameras/{id}/traffic-reset`: start a fresh counting session on the next sample, leaving saved sightings intact.
- `GET /traffic/sessions`: current per-camera observation sessions, each explicitly marked recorded/live-source provenance. It does not start streams or run inference.
- Existing ANPR snapshots now contain optional `traffic` statistics/configuration, so the camera UI reuses its existing sampling/status requests.

The additive `camera_traffic_configs` table is created by the existing startup `Base.metadata.create_all` path. No existing camera/event/evidence rows are rewritten.

## Verification

Regression coverage includes counting confirmation, one-count semantics, skipped line/zone crossings, jitter/tangency, long/frozen time gaps, normalized resolutions, configuration persistence/isolation, reset without losing OCR agreement, exact detector crops versus predictions, expired identities, class/camera isolation, bounded tracking, and short occlusion recovery. The standalone cv-engine tracker tests continue to exercise the same canonical implementation.

Browser checks use the repository's **photo-based demo recording**, not continuous traffic: setting save/reload, revision application, correctly normalized line overlay, invalid geometry rejection, session reset, dashboard visibility, and preserved live photos. Positive crossing geometry is verified with deterministic detector fixtures. Accuracy and smooth multi-camera performance still require an operator's authorized, continuous footage.
