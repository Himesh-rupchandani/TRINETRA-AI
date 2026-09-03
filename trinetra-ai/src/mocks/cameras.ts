import type { Camera } from '@/types';

/**
 * Camera registry (Model 1 foundation).
 *
 * Locations are real Ahmedabad junctions and the operational metadata
 * (event counts, watchlist story, a few degraded/offline units) is synthetic
 * demo data. The `codec` column is NOT synthetic: it mirrors what the Sentinel
 * gateway actually publishes for each path, so the player can warn before it
 * tries to decode a stream the browser cannot handle.
 *
 * The grid is mixed H.264 / H.265 — cam06, cam12, cam17, cam18, cam22 and
 * cam26 are HEVC and will not decode over WebRTC in most browsers.
 */
interface Seed {
  name: string;
  location: string;
  lat: number;
  lng: number;
  dept: string;
  zone: string;
  status: Camera['status'];
  codec: string;
  w: number;
  h: number;
  fps: number;
  stream: Camera['streamType'];
}

const SEEDS: Seed[] = [
  ['CAM01', 'Law Garden Circle', 23.0225, 72.5595, 'Traffic Police', 'Central', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM02', 'Ellis Bridge', 23.0234, 72.5714, 'Traffic Police', 'Central', 'ONLINE', 'H264', 2560, 1440, 25, 'WEBRTC'],
  ['CAM03', 'Anjali Cross Roads', 22.995, 72.548, 'Municipal (AMC)', 'South', 'ONLINE', 'H264', 1280, 720, 20, 'WEBRTC'],
  ['CAM04', 'Paldi Circle', 23.0126, 72.5647, 'Police', 'Central', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM05', 'Navrangpura Circle', 23.0367, 72.56, 'Police', 'West', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM06', 'Gujarat University Junction', 23.0395, 72.545, 'Traffic Police', 'West', 'ONLINE', 'H265', 1280, 720, 15, 'WEBRTC'],
  ['CAM07', 'Panjrapole Cross Road', 23.029, 72.548, 'Traffic Police', 'West', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM08', 'Lal Darwaja Terminus', 23.025, 72.58, 'Police', 'Central', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM09', 'Kalupur Railway Station', 23.0272, 72.6014, 'Railway Police', 'East', 'ONLINE', 'H264', 2560, 1440, 30, 'WEBRTC'],
  ['CAM10', 'Jamalpur Gate', 23.013, 72.582, 'Police', 'Central', 'ONLINE', 'H264', 1280, 720, 20, 'WEBRTC'],
  ['CAM11', 'Delhi Darwaja', 23.04, 72.59, 'Municipal (AMC)', 'Central', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM12', 'Kankaria Lake Circle', 22.999, 72.602, 'Police', 'South', 'ONLINE', 'H265', 1920, 1080, 25, 'WEBRTC'],
  ['CAM13', 'CTM Cross Road', 22.99, 72.625, 'Traffic Police', 'South', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM14', 'Isanpur Cross Road', 22.97, 72.6, 'Traffic Police', 'South', 'ONLINE', 'H264', 1280, 720, 20, 'WEBRTC'],
  ['CAM15', 'Vatva GIDC Gate', 22.96, 72.63, 'Industrial Security', 'South', 'ONLINE', 'H264', 1280, 720, 12, 'WEBRTC'],
  ['CAM16', 'Narol Circle', 22.955, 72.585, 'Highway Authority', 'South', 'ONLINE', 'H264', 2560, 1440, 30, 'WEBRTC'],
  ['CAM17', 'Odhav Ring Road', 23.028, 72.665, 'Highway Authority', 'East', 'ONLINE', 'H265', 1920, 1080, 30, 'WEBRTC'],
  ['CAM18', 'Nikol Circle', 23.045, 72.665, 'Police', 'East', 'ONLINE', 'H265', 1920, 1080, 25, 'WEBRTC'],
  ['CAM19', 'Bapunagar Char Rasta', 23.04, 72.64, 'Police', 'East', 'ONLINE', 'H264', 1280, 720, 20, 'WEBRTC'],
  ['CAM20', 'Naroda Patiya', 23.07, 72.66, 'Traffic Police', 'East', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM21', 'Airport Circle Hansol', 23.073, 72.626, 'Airport Security', 'North', 'ONLINE', 'H264', 2560, 1440, 30, 'WEBRTC'],
  ['CAM22', 'Riverfront West Promenade', 23.05, 72.575, 'Municipal (AMC)', 'Central', 'ONLINE', 'H265', 1920, 1080, 25, 'WEBRTC'],
  ['CAM23', 'Gandhi Ashram Gate', 23.06, 72.58, 'Police', 'North', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM24', 'RTO Circle Subhash Bridge', 23.055, 72.586, 'Transport Dept', 'North', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM25', 'Motera Stadium Approach', 23.092, 72.597, 'Police', 'North', 'ONLINE', 'H264', 2560, 1440, 30, 'WEBRTC'],
  ['CAM26', 'Chandkheda Circle', 23.11, 72.59, 'Traffic Police', 'North', 'OFFLINE', 'H265', 1280, 720, 20, 'WEBRTC'],
  ['CAM27', 'Vastrapur Lake Junction', 23.0395, 72.529, 'Police', 'West', 'ONLINE', 'H264', 1920, 1080, 25, 'WEBRTC'],
  ['CAM28', 'Iskcon Cross Roads', 23.027, 72.507, 'Traffic Police', 'West', 'DEGRADED', 'H264', 2560, 1440, 30, 'WEBRTC'],
  ['CAM29', 'S.G. Highway Bopal', 23.03, 72.47, 'Highway Authority', 'West', 'OFFLINE', 'H264', 2560, 1440, 30, 'WEBRTC'],
  ['CAM30', 'Sarkhej Circle', 22.98, 72.5, 'Highway Authority', 'West', 'DEGRADED', 'H264', 1920, 1080, 25, 'WEBRTC'],
].map(
  (r) =>
    ({
      name: r[0],
      location: r[1],
      lat: r[2],
      lng: r[3],
      dept: r[4],
      zone: r[5],
      status: r[6],
      codec: r[7],
      w: r[8],
      h: r[9],
      fps: r[10],
      stream: r[11],
    }) as Seed,
);

export const mockCameras: Camera[] = SEEDS.map((s, i) => ({
  id: s.name.toLowerCase(),
  name: s.name,
  location: s.location,
  latitude: s.lat,
  longitude: s.lng,
  department: s.dept,
  zone: s.zone,
  status: s.status,
  codec: s.codec,
  width: s.w,
  height: s.h,
  fps: s.fps,
  streamType: s.stream,
  installedAt: new Date(2023, i % 12, ((i * 3) % 27) + 1).toISOString(),
}));

export const cameraById = (id: string): Camera | undefined =>
  mockCameras.find((c) => c.id === id.toLowerCase());

export const cameraByName = (name: string): Camera | undefined =>
  mockCameras.find((c) => c.name.toUpperCase() === name.toUpperCase());
