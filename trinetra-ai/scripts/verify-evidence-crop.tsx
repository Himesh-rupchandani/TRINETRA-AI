/**
 * REAL-CROP EVIDENCE VERIFICATION
 * -------------------------------
 * Proves the evidence panel shows what the CV engine actually captured, using
 * the SAME modules the app ships (adapters, the evidence guard, the panel
 * itself, server-rendered) against a running backend:
 *
 *   1. a sighting in the DB carries `evidence_ref`
 *   2. GET /api/evidence/{ref} serves that crop as a real image
 *   3. the shipped adapter turns it into a real crop URL (frame + plate crop)
 *   4. the shipped EvidencePanel renders an <img> on exactly that URL
 *   5. demo/synthetic evidence renders NO image (a stand-in can never pass)
 *
 *   BACKEND=http://127.0.0.1:8000 npm run verify:evidence
 */
import { renderToStaticMarkup } from 'react-dom/server';
// react-router v7 ships StaticRouter from the main entry (react-router-dom
// re-exports it) — it provides the router context the panel's <Link> needs.
import { StaticRouter } from 'react-router-dom';
import { EvidencePanel } from '@/components/vehicle/EvidencePanel';
import { realCrops } from '@/utils/evidence';
import { toVehicleEvent, type VehicleEventDto } from '@/services/adapters';

const BACKEND = process.env.BACKEND ?? 'http://127.0.0.1:8000';
const API = `${BACKEND.replace(/\/$/, '')}/api`;

let failures = 0;
let checks = 0;

function check(label: string, condition: boolean, detail = '') {
  checks += 1;
  if (condition) console.log(`  PASS  ${label}${detail ? ` — ${detail}` : ''}`);
  else {
    failures += 1;
    console.log(`  FAIL  ${label}${detail ? ` — ${detail}` : ''}`);
  }
}

const section = (t: string) => console.log(`\n${t}`);

/** Render the real component the way the browser would (minus effects). */
function renderPanel(dto: VehicleEventDto): string {
  const event = toVehicleEvent(dto);
  return renderToStaticMarkup(
    <StaticRouter location="/investigation">
      <EvidencePanel event={event} />
    </StaticRouter>,
  );
}

const imgSrcs = (html: string): string[] =>
  [...html.matchAll(/<img[^>]*\ssrc="([^"]+)"/g)].map((m) => m[1]);

async function main() {
  console.log(`TRINETRA real-crop evidence check against ${API}`);

  /* ------------------- 1. a sighting with a real crop ------------------- */
  section('Sighting with a captured crop');
  const res = await fetch(`${API}/events?page=1&size=100`);
  if (!res.ok) throw new Error(`GET /events -> HTTP ${res.status}`);
  const page = (await res.json()) as { items?: VehicleEventDto[] };
  const candidates = (page.items ?? []).filter(
    (e) => !!e.evidence_ref && /\.(jpe?g|png)$/i.test(e.evidence_ref ?? ''),
  );
  check('sightings carry evidence_ref', candidates.length > 0, `${candidates.length} of ${(page.items ?? []).length}`);

  /* --------------------- 2. the backend serves the crop --------------------- */
  // A ref can legitimately point at a file the retention sweep already removed,
  // so probe the candidates and verify the chain on one the store still has.
  section('Evidence store serves the crop');
  let withCrop: VehicleEventDto | undefined;
  let cropRes: Response | undefined;
  let bytes = 0;
  const missing: string[] = [];
  for (const c of candidates) {
    const r = await fetch(`${API}/evidence/${c.evidence_ref}`);
    if (r.ok) {
      withCrop = c;
      cropRes = r;
      bytes = (await r.arrayBuffer()).byteLength;
      break;
    }
    missing.push(`${c.evidence_ref} (HTTP ${r.status})`);
  }
  if (missing.length) {
    console.log(`  note  ${missing.length} ref(s) no longer in the store: ${missing.join(', ')}`);
  }

  if (!withCrop || !cropRes) {
    console.log(
      '\nBLOCKED — no sighting in this backend has a crop the evidence store can serve,\n' +
        'so there is no real image to verify. Run the CV engine against a camera (it writes\n' +
        'crops to cv-engine/evidence and posts evidence_ref with each event), then re-run.',
    );
    process.exit(2);
  }
  check('crop selected for verification', true, withCrop.evidence_ref!);
  check('GET /evidence/{ref} is 200', cropRes.status === 200, `HTTP ${cropRes.status}`);
  check('served as a JPEG/PNG', /image\/(jpeg|png)/.test(cropRes.headers.get('content-type') ?? ''),
    cropRes.headers.get('content-type') ?? 'no content-type');
  check('crop has real bytes', bytes > 1024, `${bytes} bytes`);

  /* ------------------- 3. adapter → real crop URLs ------------------- */
  section('Adapter mapping');
  const mapped = toVehicleEvent(withCrop);
  const crops = realCrops(mapped.evidence);
  check('adapter exposes the frame crop', !!crops?.frameUrl, crops?.frameUrl ?? 'none');
  check('frame URL points at the evidence route', /\/evidence\//.test(crops?.frameUrl ?? ''), crops?.frameUrl ?? 'none');
  check('plate crop derived once (never _plate_plate)', !/_plate_plate\./.test(crops?.plateCropUrl ?? ''),
    crops?.plateCropUrl ?? 'none');
  check('crop is not flagged synthetic', mapped.evidence?.synthetic !== true);

  /* ------------------- 4. the shipped panel renders it ------------------- */
  section('EvidencePanel render (server-rendered shipped component)');
  const html = renderPanel(withCrop);
  const srcs = imgSrcs(html);
  check('panel renders an <img>', srcs.length > 0, `${srcs.length} img tag(s)`);
  check('panel renders the captured crop', srcs.some((s) => s.includes('/evidence/') && s.endsWith(withCrop.evidence_ref!)),
    srcs.join(' | ') || 'none');
  check('no demo/synthetic imagery in the panel', !srcs.some((s) => /^(data|blob):/i.test(s) || s.includes('/evidence/veh-')),
    srcs.join(' | ') || 'none');
  check('panel labels it a captured crop', /Captured crop/.test(html));
  check('panel shows the evidence reference', html.includes(withCrop.evidence_ref!.split('/').pop()!),
    withCrop.evidence_ref!);

  /* ------------- 5. a sighting with no crop shows no image ------------- */
  section('Honesty: no crop, no image');
  const bare: VehicleEventDto = {
    id: -1,
    camera_id: 'CAM04',
    plate_number: 'GJ01ZZ0000',
    plate_confidence: 0.9,
    event_time: new Date().toISOString(),
  };
  const bareHtml = renderPanel(bare);
  check('no <img> when nothing was captured', imgSrcs(bareHtml).length === 0, imgSrcs(bareHtml).join(' | ') || 'none');
  check('panel states no captured image', /No captured image for this sighting/.test(bareHtml));

  const synthetic = renderPanel({ ...bare, id: -2, evidence_ref: undefined });
  check('panel never substitutes a stand-in photo', !/veh-(car|van|bus|bike)\.jpg/.test(synthetic));

  /* ------------------------------ result ------------------------------ */
  console.log(`\n${failures === 0 ? 'PASS' : 'FAIL'} — ${checks - failures}/${checks} checks passed`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(`\nBLOCKED — ${err instanceof Error ? err.message : String(err)}`);
  process.exit(2);
});
