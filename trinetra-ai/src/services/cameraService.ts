import type { Camera, CameraStreamTicket } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { config } from '@/lib/config';
import { mapCamera, mapCameras, getCameraIndex } from './backendAdapter';

/**
 * Camera service — Model 1 (CCTV Registry & GIS Foundation).
 * Stream URLs are always resolved server-side; the frontend holds no
 * Sentinel credentials and never constructs an authenticated stream URL.
 */
export const cameraService = {
  async list(): Promise<Camera[]> {
    if (isMockMode) return mock.getCameras();
    const raw = await get<{ data: ReturnType<typeof mapCamera>[] }>('/cameras');
    return mapCameras(raw.data);
  },

  async byId(id: string): Promise<Camera> {
    if (isMockMode) return mock.getCamera(id);
    const raw = await get<Parameters<typeof mapCamera>[0]>(
      `/cameras/${encodeURIComponent(id)}`,
    );
    return mapCamera(raw);
  },

  /**
   * Short-lived playback ticket.
   *
   * Live mode: the WHEP signalling path is same-origin (`/sentinel/stream/...`
   * mapped by the dev server / reverse proxy onto the Sentinel gateway), so
   * this carries no credentials — the gateway origin never reaches the bundle.
   */
  async stream(id: string): Promise<CameraStreamTicket> {
    if (isMockMode) return mock.getCameraStream(id);
    if (!config.liveStreams) {
      return { cameraId: id, streamType: 'WEBRTC', streamUrl: '', expiresAt: new Date().toISOString() };
    }
    return {
      cameraId: id,
      streamType: 'WEBRTC',
      streamUrl: `${config.streamBasePath}/${id}/whep`,
      expiresAt: new Date(Date.now() + 30 * 60_000).toISOString(),
    };
  },
};

// The shared camera index is the join source for event/alert metadata.
export { getCameraIndex };
