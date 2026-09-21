import type { Camera, CameraStreamTicket } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { toCamera, toStreamTicket, type CameraItemDto } from './adapters';

/** Backend live DTO shape (GET /cameras returns { data: [...] }). */
interface CameraListDto {
  data?: CameraItemDto[];
}

interface StreamTicketDto {
  camera_id: string;
  stream_type: string;
  stream_url: string;
  expires_at: string;
  playable?: boolean;
  reason?: string | null;
  detection_url?: string | null;
}

/**
 * Camera service — Model 1 (CCTV Registry & GIS Foundation).
 * Stream URLs are always resolved by the backend; the frontend holds no
 * Sentinel credentials and never constructs an authenticated stream URL.
 */
export const cameraService = {
  async list(): Promise<Camera[]> {
    if (isMockMode) return mock.getCameras();
    const res = await get<CameraItemDto[] | CameraListDto>('/cameras');
    const items = Array.isArray(res) ? res : (res.data ?? []);
    return items.map(toCamera);
  },

  async byId(id: string): Promise<Camera> {
    if (isMockMode) return mock.getCamera(id);
    return toCamera(await get<CameraItemDto>(`/cameras/${encodeURIComponent(id)}`));
  },

  /** Short-lived playback ticket issued by the backend. */
  async stream(id: string): Promise<CameraStreamTicket> {
    if (isMockMode) return mock.getCameraStream(id);
    return toStreamTicket(
      await get<StreamTicketDto>(`/cameras/${encodeURIComponent(id)}/stream`),
    );
  },

  /**
   * Probe whether this camera's live view is receiving REAL frames right now.
   * False while the backend is serving the NO-SIGNAL placeholder (source
   * unreachable from this network) — the UI then shows an honest state
   * instead of a fake LIVE badge.
   */
  async signal(id: string): Promise<boolean> {
    if (isMockMode) return true;
    const res = await get<{ has_signal?: boolean }>(
      `/cameras/${encodeURIComponent(id)}/live/signal`,
    );
    return res.has_signal !== false;
  },
};
