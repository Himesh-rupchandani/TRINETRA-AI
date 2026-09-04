import type { Camera, CameraStreamTicket } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { mapCamera, mapStreamTicket, unwrapList } from './adapters';

/**
 * Camera service — Model 1 (CCTV Registry & GIS Foundation).
 *
 * This is the ONE source of camera identity for the whole app: every screen
 * (dashboard, grid, detail, registry, GIS) resolves cameras through here, so
 * a camera can never be labelled differently on two pages.
 *
 * Stream URLs are always resolved by the backend; the frontend holds no
 * Sentinel credentials and never constructs an authenticated stream URL.
 */
export const cameraService = {
  async list(): Promise<Camera[]> {
    if (isMockMode) return mock.getCameras();
    // The registry endpoint wraps its payload as { data: [...] }.
    return unwrapList(await get<unknown>('/cameras')).map(mapCamera);
  },

  async byId(id: string): Promise<Camera> {
    if (isMockMode) return mock.getCamera(id);
    return mapCamera(await get<Record<string, unknown>>(`/cameras/${encodeURIComponent(id)}`));
  },

  /** Short-lived playback ticket issued by the backend. */
  async stream(id: string): Promise<CameraStreamTicket> {
    if (isMockMode) return mock.getCameraStream(id);
    return mapStreamTicket(
      await get<Record<string, unknown>>(`/cameras/${encodeURIComponent(id)}/stream`),
    );
  },
};
