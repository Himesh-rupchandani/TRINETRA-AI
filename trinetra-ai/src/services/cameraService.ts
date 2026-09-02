import type { Camera, CameraStreamTicket } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';

/**
 * Camera service — Model 1 (CCTV Registry & GIS Foundation).
 * Stream URLs are always resolved by the backend; the frontend holds no
 * Sentinel credentials and never constructs an authenticated stream URL.
 */
export const cameraService = {
  list(): Promise<Camera[]> {
    return isMockMode ? mock.getCameras() : get<Camera[]>('/cameras');
  },

  byId(id: string): Promise<Camera> {
    return isMockMode ? mock.getCamera(id) : get<Camera>(`/cameras/${encodeURIComponent(id)}`);
  },

  /** Short-lived signed playback ticket issued by the backend. */
  stream(id: string): Promise<CameraStreamTicket> {
    return isMockMode
      ? mock.getCameraStream(id)
      : get<CameraStreamTicket>(`/cameras/${encodeURIComponent(id)}/stream`);
  },
};
