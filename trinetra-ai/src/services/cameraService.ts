import type { Camera, CameraStreamTicket } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { config } from '@/lib/config';
import { toCamera, unwrapList, type CameraDto } from './adapters';

/**
 * Camera service — Model 1 (CCTV Registry & GIS Foundation).
 *
 * This is the single source of truth for camera data across every screen.
 * Stream URLs are always resolved by the backend / same-origin media proxy;
 * the frontend holds no Sentinel credentials and never constructs an
 * authenticated stream URL itself.
 */

/** In-flight de-duplication: many screens ask for the registry at once. */
let listInFlight: Promise<Camera[]> | null = null;

export const cameraService = {
  async list(): Promise<Camera[]> {
    if (isMockMode) return mock.getCameras();
    if (listInFlight) return listInFlight;
    listInFlight = get<unknown>('/cameras')
      .then((raw) => unwrapList<CameraDto>(raw).map(toCamera))
      .finally(() => {
        listInFlight = null;
      });
    return listInFlight;
  },

  async byId(id: string): Promise<Camera> {
    if (isMockMode) return mock.getCamera(id);
    const dto = await get<CameraDto>(`/cameras/${encodeURIComponent(id)}`);
    return toCamera(dto);
  },

  /** Registry indexed by canonical camera ID, for joining events -> camera metadata. */
  async index(): Promise<Map<string, Camera>> {
    const cams = await cameraService.list();
    return new Map(cams.map((c) => [c.id.toUpperCase(), c]));
  },

  /**
   * Playback ticket.
   *
   * The backend registry has no per-camera signing endpoint yet, so we derive
   * the same-origin WHEP path the media proxy exposes. No credential is ever
   * involved on the client: the proxy attaches whatever the gateway needs.
   */
  async stream(id: string): Promise<CameraStreamTicket> {
    if (isMockMode) return mock.getCameraStream(id);

    const cam = await cameraService.byId(id);
    const live = config.liveStreams && cam.status !== 'OFFLINE';
    return {
      cameraId: cam.id,
      streamType: live ? 'WEBRTC' : (cam.streamType ?? 'HLS'),
      streamUrl: live ? `${config.streamBasePath}/${cam.id.toLowerCase()}/whep` : '',
      expiresAt: new Date(Date.now() + 5 * 60_000).toISOString(),
    };
  },
};
