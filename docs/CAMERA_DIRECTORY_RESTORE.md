# Restore the 30-camera list without restoring demo events

The old Vercel demo bootstrap combined the CAM01–CAM30 directory with example
watchlist/sighting/alert data. Switching to a full Render backend with demo
seeding disabled exposed the smaller four-camera fallback plus `CAMLIVE`.
That is a registry regression, not a Render five-video limit.

## Existing Render service

Deploy the updated branch with `deploy/render.Dockerfile`. The image now sets:

```dotenv
AUTO_REGISTER_SENTINEL_GRID=true
AUTO_SEED_DEMO=false
AUTO_START_CAMERAS=false
```

Only missing camera entries from the application's bundled Sentinel directory
are inserted at startup. No existing camera URL/name/settings, plate event,
evidence or traffic configuration is replaced or deleted. No demo sightings,
alerts or new example watchlist entries are added in non-demo mode. Newly added
cameras are not auto-started during that restoration pass.

The result is **30 grid camera entries**, plus the independent `CAMLIVE` slot
(and any other user cameras). A total of 31 with an unconfigured `CAMLIVE` is
normal. Setting `AUTO_REGISTER_SENTINEL_GRID=false` opts out; native/non-Render
starts keep that flag off unless explicitly enabled.

This is a bundled metadata directory, **not a fresh provider catalogue or a
live-availability check**. Names/stream IDs and declared format metadata are
reused from the existing directory. New rows do not copy fixture GPS, FPS or
synthetic health state into operational analysis. Existing rows keep their
coordinates and other settings unchanged. Operator location calibration or a
valid upstream sync is needed before geographic/speed analysis.

## Manual recovery (after this code is deployed)

- UI: **Ingest API → Restore 30-camera list**, confirm the metadata-only action.
- API: `POST /api/ingest/restore-camera-list` (also `/api/v1/...`).
- The result reports `added_count`, `grid_cameras`, `total_cameras` and
  `availability_checked: false`.
- Repeating the operation is safe: matching IDs are checked case-insensitively
  and skipped. A custom provider is not populated with this unrelated directory.
- The startup result is also visible at `/api/health` → `camera_registry`.

The endpoint uses the application's existing trusted-operator boundary. It
never starts all streams or tests camera passwords. Camera playback, backend
reachability and model throughput still need individual checks.

## Why Sync Catalogue could appear to do nothing

The configured catalogue URL can redirect to a sign-in page. Previously the
sync code tried to parse it as JSON, fell back to the existing five rows, and
the UI reloaded without showing the warning. The route could even report
`synced: true` alongside a failed sync.

Sync now validates that the response contains actual camera IDs, explicitly
reports login/non-JSON/error payloads, preserves the existing registry on
failure, and shows its result in the UI. It does not scrape a login form or
send credentials to redirects. Use an authorized JSON catalogue for fresh
provider metadata; use the separate restore action for the bundled directory.

Do not turn on generic demo seeding just to increase the visible camera count.
Do not delete/recreate the database. Render's ephemeral storage can still lose
runtime data across redeploys unless you configure durable storage; restoring
this directory is not a replacement for database/evidence backups.
