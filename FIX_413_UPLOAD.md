# Fix: "Request failed with status code 413" on video upload

## Root cause

Vercel's Serverless Functions have a **hard, unconfigurable 4.5 MB request-body
limit** at the edge proxy. It applies to ALL plans (Hobby / Pro / Enterprise)
and is enforced BEFORE the request ever reaches FastAPI — so there is *no*
`vercel.json` knob, no FastAPI `UploadFile` tweak, and no nginx-style
`client_max_body_size` that can lift it. Any video bigger than ~4 MB gets
rejected instantly with:

```
Request Entity Too Large
FUNCTION_PAYLOAD_TOO_LARGE
HTTP/1.1 413
```

The previous frontend uploaded the entire file as one `multipart/form-data`
POST (`POST /api/analysis/videos/upload` for the Video Analysis page, and
`POST /api/uploads/videos` for the "Upload CCTV Video" modal), so any real
CCTV clip blew straight past the 4.5 MB ceiling.

## What the fix does

It adds a **client-side chunked upload pipeline** — files are sliced into
3 MB chunks in the browser, each chunk is POSTed individually to a new
endpoint, and the server appends them to a temp file and assembles the
final video when the last chunk lands. Every individual chunk is well
under Vercel's 4.5 MB limit, so files up to the backend's configured
`MAX_UPLOAD_SIZE_MB` (250 MB) now upload cleanly.

### Files added / changed

**Backend (FastAPI)**

- `TRINETRAAI/backend/app/services/chunked_upload.py` — new service that
  owns chunk sessions, appends chunks to `uploads/._chunks/<id>.part`,
  enforces the 250 MB cap, validates the suffix on finalize, and moves
  the assembled file into its final directory (with de-dup on collision).
- `TRINETRAAI/backend/app/api/chunked_uploads.py` — new router with four
  endpoints mounted under `/api/uploads/chunks/…` (and `/api/v1/...`):
  - `POST /chunks/init`        → opens a session, returns `upload_id`
  - `POST /chunks/{id}`        → appends one chunk (0-indexed, in order)
  - `POST /chunks/{id}/abort`  → best-effort cleanup on client cancel/fail
  - `POST /chunks/{id}/complete` → assembles the file and registers it as
    either a) a CCTV demo camera (`source=upload`) or b) a multi-video
    analysis source (`source=analysis`), matching the old non-chunked
    response shape so the existing UI needs zero changes beyond the
    upload path.
- `TRINETRAAI/backend/app/main.py` — mounts the new router.
- `TRINETRAAI/backend/app/services/video_analysis_service.py` — adds
  `register_from_path()` used by chunked completion; fixes the legacy
  `register_upload()` path so multi-video uploads stream to disk instead
  of buffering the entire file in RAM (`await upload.read()` was a
  multi-GB OOM waiting to happen).
- `TRINETRAAI/backend/app/api/video_analysis.py` — the legacy multipart
  endpoint now streams to disk and delegates to `register_from_path()`,
  so even "direct" uploads no longer buffer the entire file in memory.

**Frontend (React/Vite)**

- `trinetra-ai/src/services/chunkedUpload.ts` — new client utility:
  `uploadChunked(file, opts, onProgress)` slices a File into 3 MB chunks,
  POSTs each to `/api/uploads/chunks/…`, reports progress, and aborts
  the server-side session if something fails.
- `trinetra-ai/src/services/uploadService.ts` — `upload()` now
  automatically switches to chunked upload for files > 2 MB, keeping
  tiny files on the simple legacy path. Exposes per-file progress to
  the modal.
- `trinetra-ai/src/services/videoAnalysisService.ts` — `uploadFiles()`
  now uploads each file independently, switching to chunked mode
  for files > 2 MB, and reports overall + per-file progress.
- `trinetra-ai/src/components/camera/UploadVideoModal.tsx` — shows a
  progress bar during chunked uploads.
- `trinetra-ai/src/components/analysis/AddVideosPanel.tsx` — shows a
  progress bar + per-file label during chunked uploads, and a friendly
  note explaining why large videos may take a while.

### Numbers

| Constant | Value | Why |
|---|---|---|
| `CHUNK_SIZE_BYTES` | **3 MB** | Leaves ~1.5 MB of headroom under Vercel's 4.5 MB cap for multipart overhead/headers |
| `DIRECT_UPLOAD_THRESHOLD` | 2 MB | Files this small or smaller still use the legacy single-shot POST (fast path) |
| `MAX_UPLOAD_SIZE_MB` | 250 (unchanged) | Backend-level cap; chunked upload respects it |
| `MAX_CHUNK_AGE_SECONDS` | 24 h | Abandoned sessions (closed tab, etc.) are garbage-collected |

## Other fixes included (drive-by)

1. **Memory safety on multi-video uploads** — `video_analysis.py` used to
   do `data = await upload.read()` which loaded the entire file into RAM
   before any size check, making a 100 MB upload a 100 MB spike plus the
   FormData buffer. It now streams 1 MB chunks straight to a temp file.
2. **Helpful error messages** — chunk-level HTTP errors surface the
   backend's `detail` instead of a generic "Request failed" message.
3. **Progress UI** — both upload dialogs now show a real progress bar
   so users don't think the tab has frozen while a 200 MB CCTV clip is
   being pushed up.

## How to deploy / verify

1. Push these changes to the `main` branch of
   `Himesh-rupchandani/TRINETRA-AI` and let Vercel build normally.
2. Once deployed, open **Video Analysis → Add videos**, pick any
   `.mp4` bigger than ~5 MB, and click "Add video". You should see the
   progress bar climb steadily to 100% — no more 413.
3. The **Dashboard → Upload CCTV Video** modal uses the same chunked
   pipeline, so single-video uploads are fixed too.

### Quick local verification (no build needed)

```bash
# Backend syntax check
python3 -m py_compile TRINETRAAI/backend/app/services/chunked_upload.py
python3 -m py_compile TRINETRAAI/backend/app/api/chunked_uploads.py
python3 -m py_compile TRINETRAAI/backend/app/api/video_analysis.py

# Frontend build
cd trinetra-ai && npm install && npm run build
```

## Why not something else?

- **"Just increase the body-size limit in vercel.json"** — that flag does
  not exist for Serverless Functions. Vercel confirmed it cannot be
  raised on any plan.
- **Vercel Blob / S3 presigned URLs** — the *proper* production solution
  (no chunked-upload machinery, GB-sized files, CDN delivery), but it
  requires either a paid Blob add-on or an AWS/GCP account. Chunked
  uploads work with the existing backend, for free, today. A follow-up
  could swap the chunk session store for Blob/S3 transparently because
  the service interface (`init/append/finalize`) is already isolated.
- **Edge Runtime / streaming functions** — they *also* have a 4 MB
  request-body cap for Edge and the streaming body doesn't help
  with *incoming* multipart payloads on Vercel's hosted platform.
