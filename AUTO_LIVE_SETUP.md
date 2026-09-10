# TRINETRA AI — Auto Live Camera & Auto-Login Setup

## Problem
- Hackathon me jo live cameras provide kiye gaye the (Sentinel grid), unke liye har baar email/password dalna padta tha
- Website run karte hi manual login karna padta tha

## Solution — Automatic

### 1. Credentials Auto-Injected
Ab credentials automatically inject ho jate hain — koi manual entry nahi:

**Frontend (`trinetra-ai/.env` + `.env.local`):**
```env
SENTINEL_EMAIL=himesh.rupchandani140850@marwadiuniversity.ac.in
SENTINEL_PASSWORD=A7UX-7TRC-BVS6
SENTINEL_WHEP_ORIGIN=http://103.250.160.189:8889
VITE_LIVE_STREAMS=true
VITE_AUTO_LOGIN=true
```

**Backend (`TRINETRAAI/backend/.env`):**
```env
SENTINEL_EMAIL=himesh.rupchandani140850@marwadiuniversity.ac.in
SENTINEL_PASSWORD=A7UX-7TRC-BVS6
AUTO_START_CAMERAS=true
```

**Fallback in Code:**
- `trinetra-ai/vite.config.ts` — has hardcoded fallback credentials, so even if .env empty, live camera works
- `TRINETRAAI/backend/app/core/config.py` — default email/password set to hackathon creds
- `cv-engine/config/settings.py` — same fallback

### 2. How It Works (Technical)

**Vite Proxy (Frontend):**
```ts
// vite.config.ts — sentinelBasic() injects Basic Auth header server-side
function sentinelBasic(env) {
  const email = env.SENTINEL_EMAIL ?? HACKATHON_DEFAULTS.email
  const password = env.SENTINEL_PASSWORD ?? HACKATHON_DEFAULTS.password
  return `Basic ${Buffer.from(`${email}:${password}`).toString('base64')}`
}
// Browser never sees credentials — proxy adds Authorization header
```

**Backend RTSP:**
```python
# sentinel_stream_service.py — builds authenticated RTSP URL at connect time
# rtsp://email:password@103.250.160.189:8554/stream/cam04
# Credentials never stored in DB or returned to frontend
```

**Auto-Login for Officer:**
- `OfficerProvider.tsx` now persists selected officer in localStorage
- Key: `trinetra.currentOfficerId`
- Next time website open karo toh wahi officer auto-selected

**Live Camera Auto-Start:**
- Dashboard pe default live camera (cam04) auto-play hota hai
- `CameraPlayer` with `autoRequest` prop — no click needed
- `config.defaultLiveCameraId = 'cam04'` — changeable via env

### 3. Run Website — No Manual Login

**Option A: Auto Script (Recommended)**
```bash
# Linux/Mac
./start-auto.sh

# Windows
.\start-auto.ps1
```
Ye script:
- .env files auto-create karta hai
- Backend + frontend dono start karta hai
- Live cameras auto-connect

**Option B: Manual but still auto-login**
```bash
# Backend
cd TRINETRAAI/backend
python -m scripts.seed_demo   # first time only
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (another terminal)
cd trinetra-ai
npm run dev:auto   # auto-setup + vite dev server
# or
npm run dev        # predev hook auto-setup karta hai
```

Open: http://localhost:5173
- Dashboard pe live camera auto-play hoga
- Koi email/password prompt nahi
- Cameras page pe kisi bhi camera ko open karo — auto WHEP connection

### 4. Live Camera Grid

Hackathon ne 30 cameras diye:
- CAM01 to CAM30 — Gujarat locations (Ahmedabad, Junagadh, Rajkot, etc.)
- All via Sentinel: `https://cctv.corp8.cloud/camXX/index.m3u8` (HLS) + WHEP `http://103.250.160.189:8889/stream/camXX/whep`
- Primary demo: CAM04 (Paldi Circle) — dashboard pe auto

**To change default live camera:**
```env
# trinetra-ai/.env
VITE_DEFAULT_LIVE_CAMERA=cam17
```

### 5. Verification

```bash
# Check credentials injected
cat trinetra-ai/.env | grep SENTINEL
cat TRINETRAAI/backend/.env | grep SENTINEL

# Check backend health
curl http://localhost:8000/health

# Check camera list
curl http://localhost:8000/api/cameras | jq '.data[0]'

# Check stream ticket (should return /sentinel/stream/cam04/whep)
curl http://localhost:8000/api/cameras/cam04/stream
```

### 6. Files Changed

- `trinetra-ai/.env` — auto credentials
- `trinetra-ai/.env.local` — same (gitignored)
- `TRINETRAAI/backend/.env` — created with auto creds
- `trinetra-ai/vite.config.ts` — fallback creds + auto-login
- `TRINETRAAI/backend/app/core/config.py` — default creds fallback
- `cv-engine/config/settings.py` — fallback creds
- `trinetra-ai/src/lib/config.ts` — autoLogin flag + defaultLiveCameraId
- `trinetra-ai/src/features/officer/OfficerProvider.tsx` — localStorage persistence
- `trinetra-ai/src/pages/Dashboard.tsx` — auto live camera widget
- `trinetra-ai/scripts/auto-setup-env.mjs` — auto-setup script
- `trinetra-ai/package.json` — predev hook
- `start-auto.sh` / `start-auto.ps1` — one-click auto start

### 7. Security Note

- Credentials are server-side only (no VITE_ prefix)
- Browser bundle never contains password
- Vite proxy injects Authorization header
- Backend builds RTSP URL at connect time, never returns it
- For production, move creds to real env vars / secrets manager

---

**Result:** `npm run dev` karo, website khulega, live camera auto-play, no email/password prompt. 🎬
