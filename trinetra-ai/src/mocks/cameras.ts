import type { Camera } from '@/types';

/**
 * Camera registry (Model 1 foundation) — SENTINEL live grid, 05/09/2026.
 *
 * IDs and location labels are the SENTINEL control-room names, verbatim —
 * including their original casing and punctuation — so an operator reading a
 * sighting off CAM19 sees the same string the Sentinel grid prints. IDs stay
 * CAM01…CAM30 because the media gateway addresses a feed by that path
 * (`/sentinel/stream/cam19/whep`).
 *
 * Coordinates are the real siting of each camera, resolved to town/suburb
 * level. The grid spans Gujarat — Ahmedabad, Junagadh, Gir Somnath,
 * Gandhinagar, Rajkot, Navsari, Patan and Kutch — not a single city, so the
 * GIS default view is statewide (see VITE_MAP_* in .env).
 *
 * Two labels could not be pinned down (`Delight RLVD`, `Mohanpura`): they
 * carry zone "Unconfirmed" and fall back to the control-room coordinate
 * rather than a guessed town.
 *
 * Status: all 30 cameras reported LIVE on the 05/09/2026 12:30 IST grid, so
 * the registry is uniformly ONLINE. Offline/poor-quality states are driven by
 * the live WHEP probe, not by a fixture.
 *
 * Codec: the Sentinel grid does not publish codecs. The HEVC rows below are
 * carried over from the previous seed purely so the player's "H.265 — this
 * browser cannot decode it" warning path stays exercised in demo mode.
 */
interface Seed {
  name: string;
  location: string;
  lat: number;
  lng: number;
  dept: string;
  zone: string;
  codec: string;
  w: number;
  h: number;
  fps: number;
  stream: Camera['streamType'];
}

const SEEDS: Seed[] = [
  { name: 'CAM01', location: 'Chiman bhai Bridge', lat: 23.073, lng: 72.592, dept: 'Traffic Police', zone: 'Ahmedabad', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM02', location: 'Janpath', lat: 23.0225, lng: 72.5625, dept: 'Police', zone: 'Ahmedabad', codec: 'H264', w: 2560, h: 1440, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM03', location: 'O.N.G.C. Office', lat: 23.107, lng: 72.595, dept: 'Industrial Security', zone: 'Ahmedabad', codec: 'H264', w: 1280, h: 720, fps: 20, stream: 'WEBRTC' },
  { name: 'CAM04', location: 'Paldi Circle', lat: 23.0126, lng: 72.5647, dept: 'Police', zone: 'Ahmedabad', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM05', location: 'Visat teen Rasta', lat: 23.087, lng: 72.593, dept: 'Traffic Police', zone: 'Ahmedabad', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM06', location: 'Timbavadi gate-Junagadh', lat: 21.5236, lng: 70.455, dept: 'Police', zone: 'Junagadh', codec: 'H265', w: 1280, h: 720, fps: 15, stream: 'WEBRTC' },
  { name: 'CAM07', location: 'hero-showroom-gir-somnath', lat: 20.9097, lng: 70.3666, dept: 'Police', zone: 'Gir Somnath', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM08', location: 'majewadi-gate-junagadh', lat: 21.53, lng: 70.462, dept: 'Police', zone: 'Junagadh', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM09', location: 'new-bypass-near-by-circle-junagadh-2', lat: 21.5355, lng: 70.478, dept: 'Highway Authority', zone: 'Junagadh', codec: 'H264', w: 2560, h: 1440, fps: 30, stream: 'WEBRTC' },
  { name: 'CAM10', location: 'char-chowk-road-2-junagadh', lat: 21.5222, lng: 70.4573, dept: 'Police', zone: 'Junagadh', codec: 'H264', w: 1280, h: 720, fps: 20, stream: 'WEBRTC' },
  { name: 'CAM11', location: 'dolatpara-junagadh', lat: 21.5255, lng: 70.456, dept: 'Municipal (JMC)', zone: 'Junagadh', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM12', location: 'Tri Mandir Adalaj Tollnaka', lat: 23.1662, lng: 72.5807, dept: 'Highway Authority', zone: 'Gandhinagar', codec: 'H265', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM13', location: 'CN Vidhyalaya', lat: 23.0305, lng: 72.5456, dept: 'Municipal (AMC)', zone: 'Ahmedabad', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM14', location: 'Delight RLVD', lat: 23.0225, lng: 72.5714, dept: 'Traffic Police', zone: 'Unconfirmed', codec: 'H264', w: 1280, h: 720, fps: 20, stream: 'WEBRTC' },
  { name: 'CAM15', location: 'Suvidha park', lat: 23.0389, lng: 72.6608, dept: 'Municipal (AMC)', zone: 'Ahmedabad', codec: 'H264', w: 1280, h: 720, fps: 20, stream: 'WEBRTC' },
  { name: 'CAM16', location: 'Visat P2', lat: 23.091, lng: 72.598, dept: 'Traffic Police', zone: 'Ahmedabad', codec: 'H264', w: 2560, h: 1440, fps: 30, stream: 'WEBRTC' },
  { name: 'CAM17', location: 'Rajkot Bus Port CCTV', lat: 22.2908, lng: 70.799, dept: 'Transport Dept', zone: 'Rajkot', codec: 'H265', w: 1920, h: 1080, fps: 30, stream: 'WEBRTC' },
  { name: 'CAM18', location: 'Rajkot CCTV', lat: 22.3039, lng: 70.8022, dept: 'Police', zone: 'Rajkot', codec: 'H265', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM19', location: 'KHAPARIA GRAM PANCHAYAT, TALUKA GANDEVI, DISTRICT NAVSARI', lat: 20.8136, lng: 72.99, dept: 'Gram Panchayat', zone: 'Navsari', codec: 'H264', w: 1280, h: 720, fps: 20, stream: 'WEBRTC' },
  { name: 'CAM20', location: 'Mohanpura', lat: 23.0225, lng: 72.5714, dept: 'Police', zone: 'Unconfirmed', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM21', location: 'Patan Dethali Char Rasta', lat: 23.9167, lng: 72.35, dept: 'Police', zone: 'Patan', codec: 'H264', w: 2560, h: 1440, fps: 30, stream: 'WEBRTC' },
  { name: 'CAM22', location: 'BK Mervada tran Rasta', lat: 23.7833, lng: 72.1167, dept: 'Police', zone: 'Patan', codec: 'H265', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM23', location: 'kheram', lat: 20.76, lng: 72.97, dept: 'Gram Panchayat', zone: 'Navsari', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM24', location: 'dehgam', lat: 23.1691, lng: 72.8066, dept: 'Municipal (Dehgam)', zone: 'Gandhinagar', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM25', location: 'dhanori', lat: 20.788, lng: 72.977, dept: 'Gram Panchayat', zone: 'Navsari', codec: 'H264', w: 2560, h: 1440, fps: 30, stream: 'WEBRTC' },
  { name: 'CAM26', location: 'TANKAL', lat: 20.78, lng: 73.132, dept: 'Gram Panchayat', zone: 'Navsari', codec: 'H265', w: 1280, h: 720, fps: 20, stream: 'WEBRTC' },
  { name: 'CAM27', location: 'bilimora', lat: 20.7508, lng: 72.951, dept: 'Municipal (Bilimora)', zone: 'Navsari', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
  { name: 'CAM28', location: 'bilimora', lat: 20.7543, lng: 72.9562, dept: 'Municipal (Bilimora)', zone: 'Navsari', codec: 'H264', w: 2560, h: 1440, fps: 30, stream: 'WEBRTC' },
  { name: 'CAM29', location: 'bilimora', lat: 20.747, lng: 72.9478, dept: 'Municipal (Bilimora)', zone: 'Navsari', codec: 'H264', w: 2560, h: 1440, fps: 30, stream: 'WEBRTC' },
  { name: 'CAM30', location: 'Gandhidham Rambaugh p2', lat: 23.0759, lng: 70.131, dept: 'Municipal (GDM)', zone: 'Kutch', codec: 'H264', w: 1920, h: 1080, fps: 25, stream: 'WEBRTC' },
];

/** The 05/09/2026 grid reported every camera LIVE. */
const GRID_STATUS: Camera['status'] = 'ONLINE';

export const mockCameras: Camera[] = SEEDS.map((s, i) => ({
  id: s.name.toLowerCase(),
  name: s.name,
  location: s.location,
  latitude: s.lat,
  longitude: s.lng,
  department: s.dept,
  zone: s.zone,
  status: GRID_STATUS,
  codec: s.codec,
  width: s.w,
  height: s.h,
  fps: s.fps,
  streamType: s.stream,
  // Mock feeds are generated stills, not a camera. Labelling them LIVE in a
  // demo is exactly the confusion this project must not ship, so the mock data
  // is honest even when the real backend is not in play.
  sourceKind: 'RECORDED',
  installedAt: new Date(2023, i % 12, ((i * 3) % 27) + 1).toISOString(),
}));

export const cameraById = (id: string): Camera | undefined =>
  mockCameras.find((c) => c.id === id.toLowerCase());

export const cameraByName = (name: string): Camera | undefined =>
  mockCameras.find((c) => c.name.toUpperCase() === name.toUpperCase());
