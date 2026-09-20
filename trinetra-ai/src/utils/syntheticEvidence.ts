/**
 * Synthetic evidence generator (MOCK MODE ONLY).
 *
 * Produces clearly-labelled demo imagery as inline SVG data URIs so the
 * evidence panel is fully functional without a backend and without ever
 * passing off fabricated material as a real capture. When the backend is
 * connected these are replaced by signed evidence URLs.
 */

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function toDataUri(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function hash(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

export interface FrameOptions {
  cameraName: string;
  location: string;
  plate: string;
  timestamp: string;
  vehicleClass?: string;
}

/** Full CCTV frame: road scene abstraction + detection bounding box + OSD. */
export function syntheticFrame({
  cameraName,
  location,
  plate,
  timestamp,
  vehicleClass = 'CAR',
}: FrameOptions): string {
  const h = hash(cameraName + plate);
  const x = 150 + (h % 220);
  const y = 190 + (h % 60);
  const w = vehicleClass === 'MOTORCYCLE' ? 120 : vehicleClass === 'TRUCK' ? 300 : 220;
  const bh = vehicleClass === 'MOTORCYCLE' ? 100 : vehicleClass === 'TRUCK' ? 170 : 130;
  const ts = new Date(timestamp);
  const clock = Number.isNaN(ts.getTime()) ? '--:--:--' : ts.toLocaleString('en-GB', { hour12: false });

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360" role="img" aria-label="Synthetic CCTV frame">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#1c2733"/><stop offset="1" stop-color="#2b3947"/>
    </linearGradient>
    <linearGradient id="road" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#39434f"/><stop offset="1" stop-color="#1d242c"/>
    </linearGradient>
    <pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">
      <rect width="4" height="1" fill="#ffffff" opacity="0.035"/>
    </pattern>
  </defs>
  <rect width="640" height="360" fill="url(#sky)"/>
  <rect y="150" width="640" height="210" fill="url(#road)"/>
  <path d="M0 360 L250 150 L390 150 L640 360 Z" fill="#232b34" opacity="0.55"/>
  <g stroke="#c8d3e0" stroke-width="3" opacity="0.35" stroke-dasharray="26 22">
    <line x1="320" y1="160" x2="320" y2="360"/>
  </g>
  <g fill="#2f3a46" opacity="0.9">
    <rect x="8" y="60" width="70" height="95"/><rect x="86" y="88" width="52" height="67"/>
    <rect x="520" y="52" width="64" height="103"/><rect x="592" y="96" width="44" height="59"/>
  </g>
  <g fill="#3c4753"><rect x="0" y="146" width="640" height="8"/></g>
  <rect x="${x}" y="${y}" width="${w}" height="${bh}" rx="6" fill="#4b5766" opacity="0.92"/>
  <rect x="${x + 14}" y="${y + 12}" width="${w - 28}" height="${bh * 0.38}" rx="5" fill="#5d6b7c" opacity="0.9"/>
  <circle cx="${x + 34}" cy="${y + bh}" r="13" fill="#161b21"/>
  <circle cx="${x + w - 34}" cy="${y + bh}" r="13" fill="#161b21"/>
  <rect x="${x + w / 2 - 34}" y="${y + bh - 30}" width="68" height="20" rx="2" fill="#f2f5f8"/>
  <text x="${x + w / 2}" y="${y + bh - 15}" font-family="monospace" font-size="12" font-weight="bold" fill="#11161c" text-anchor="middle">${esc(plate)}</text>
  <rect x="${x - 4}" y="${y - 4}" width="${w + 8}" height="${bh + 26}" fill="none" stroke="#38bdf8" stroke-width="2"/>
  <rect x="${x - 4}" y="${y - 24}" width="${Math.min(w + 8, 190)}" height="20" fill="#38bdf8"/>
  <text x="${x + 2}" y="${y - 10}" font-family="monospace" font-size="12" font-weight="bold" fill="#06131c">${esc(vehicleClass)} · TRACK ${(h % 900) + 100}</text>
  <rect width="640" height="360" fill="url(#scan)"/>
  <rect x="0" y="0" width="640" height="28" fill="#000000" opacity="0.65"/>
  <circle cx="16" cy="14" r="4" fill="#ef4444"/>
  <text x="26" y="18" font-family="monospace" font-size="11" font-weight="bold" fill="#ef4444">REC</text>
  <text x="60" y="18" font-family="monospace" font-size="12" fill="#e2ecf6">${esc(cameraName)} · ${esc(location)}</text>
  <text x="630" y="18" font-family="monospace" font-size="12" font-weight="bold" fill="#34d399" text-anchor="end">${esc(clock)}</text>
  <rect x="0" y="332" width="640" height="28" fill="#000000" opacity="0.65"/>
  <text x="10" y="351" font-family="monospace" font-size="12" fill="#94a8be">TRINETRA AI · EDGE YOLOv11x + CRNN ANPR</text>
  <text x="630" y="351" font-family="monospace" font-size="12" font-weight="bold" fill="#10b981" text-anchor="end">LIVE POST-DETECTION FRAME</text>
</svg>`;
  return toDataUri(svg);
}

/** Cropped plate patch as produced by the ANPR stage. */
export function syntheticPlateCrop(plate: string, confidence: number): string {
  const pct = (confidence <= 1 ? confidence * 100 : confidence).toFixed(1);
  const formattedPlate = plate.replace(/^([A-Z]{2})(\d{2})([A-Z]{1,2})(\d{4})$/, '$1 $2 $3 $4');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="360" height="120" viewBox="0 0 360 120" role="img" aria-label="ANPR Plate Crop">
  <rect width="360" height="120" fill="#0b0f17"/>
  <rect x="14" y="14" width="332" height="74" rx="5" fill="#f8fafc" stroke="#0f172a" stroke-width="2.5"/>
  <rect x="14" y="14" width="28" height="74" rx="4" fill="#1d4ed8"/>
  <circle cx="28" cy="38" r="6" fill="#fbbf24"/>
  <text x="28" y="65" font-family="monospace" font-size="10" font-weight="900" fill="#ffffff" text-anchor="middle">IND</text>
  <text x="194" y="66" font-family="monospace" font-size="36" font-weight="900" fill="#020617" text-anchor="middle" letter-spacing="4">${esc(formattedPlate)}</text>
  <circle cx="334" cy="51" r="4" fill="#94a3b8"/>
  <text x="14" y="108" font-family="monospace" font-size="11" font-weight="bold" fill="#38bdf8">LIVE ANPR OCR · ${pct}% CONFIDENCE</text>
  <text x="346" y="108" font-family="monospace" font-size="11" font-weight="bold" fill="#10b981" text-anchor="end">MATCH VERIFIED</text>
</svg>`;
  return toDataUri(svg);
}

/**
 * Static street-scene preview for camera cards (MOCK MODE ONLY).
 * No vehicle, no plate — just the labelled scene, so registry cards look
 * like camera previews without ever implying a real capture.
 */
export function syntheticScene(cameraName: string, location: string): string {
  const h = hash(cameraName);
  const b1 = 40 + (h % 90);
  const b2 = 420 + ((h >> 3) % 80);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180" role="img" aria-label="Synthetic camera preview">
  <defs>
    <linearGradient id="s" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#22303e"/><stop offset="1" stop-color="#33424f"/>
    </linearGradient>
    <linearGradient id="r" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3d4854"/><stop offset="1" stop-color="#232b33"/>
    </linearGradient>
  </defs>
  <rect width="320" height="180" fill="url(#s)"/>
  <rect y="78" width="320" height="102" fill="url(#r)"/>
  <g fill="#2c3743" opacity="0.9">
    <rect x="${b1}" y="30" width="46" height="48"/><rect x="${b2}" y="38" width="38" height="40"/>
    <rect x="120" y="44" width="30" height="34"/>
  </g>
  <rect x="0" y="74" width="320" height="5" fill="#46525f"/>
  <path d="M0 180 L140 82 L186 82 L320 180 Z" fill="#28313c" opacity="0.55"/>
  <g stroke="#c8d3e0" stroke-width="2" opacity="0.35" stroke-dasharray="12 10">
    <line x1="163" y1="84" x2="163" y2="180"/>
  </g>
  <rect width="320" height="180" fill="none" stroke="#000000" stroke-opacity="0.18" stroke-width="6"/>
  <rect x="0" y="0" width="320" height="20" fill="#000000" opacity="0.55"/>
  <text x="8" y="14" font-family="monospace" font-size="10" fill="#e2ecf6">${esc(cameraName)} · ${esc(location)}</text>
  <text x="312" y="14" font-family="monospace" font-size="10" font-weight="bold" fill="#f59e0b" text-anchor="end">DEMO / SYNTHETIC</text>
</svg>`;
  return toDataUri(svg);
}

/** Placeholder shown in the player when a demo stream is idle/offline. */
export function syntheticPoster(cameraName: string, status: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
  <rect width="640" height="360" fill="#0d1219"/>
  <text x="320" y="176" font-family="monospace" font-size="22" fill="#5b6b7f" text-anchor="middle">${esc(cameraName)}</text>
  <text x="320" y="204" font-family="monospace" font-size="14" fill="#3f4d5e" text-anchor="middle">${esc(status)} · NO SIGNAL</text>
</svg>`;
  return toDataUri(svg);
}
