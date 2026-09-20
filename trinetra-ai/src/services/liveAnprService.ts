import { get, post } from './api';

export interface LiveDetection {
  x1: number; y1: number; x2: number; y2: number;
  class_name: string;
  confidence: number;
  track_id: number;
  plate_number: string | null;
  plate_confidence: number | null;
  plate_status: 'HIGH' | 'LOW_CONFIDENCE' | 'UNKNOWN';
  plate_box: [number, number, number, number] | null;
  event_id: number | null;
}

export interface LiveAnprSnapshot {
  camera_id: string;
  status: 'IDLE' | 'WARMING_UP' | 'PROCESSING' | 'SCANNING' | 'UNAVAILABLE' | 'ERROR' | 'DISABLED' | 'BUSY' | 'SHARED';
  reason?: string | null;
  source_id?: string;
  media_time?: number | null;
  frame_width: number;
  frame_height: number;
  /** 16×9 luminance sketch; prevents old boxes over a different scene. */
  frame_signature?: number[];
  result_age_ms: number | null;
  overlay_ttl_ms: number;
  sample_interval_ms: number;
  max_vehicles: number;
  pending: boolean;
  accepted?: boolean;
  detections: LiveDetection[];
}

export const liveAnprService = {
  sample(cameraId: string, jpeg: Blob, clientId: string, mediaTime: number, signal: AbortSignal) {
    return post<LiveAnprSnapshot>(`/cameras/${encodeURIComponent(cameraId)}/detect-frame`, jpeg, {
      headers: { 'Content-Type': 'image/jpeg' },
      params: { client_id: clientId, media_time: mediaTime },
      signal,
      timeout: 8_000,
    });
  },
  status(cameraId: string, signal?: AbortSignal) {
    return get<LiveAnprSnapshot>(`/cameras/${encodeURIComponent(cameraId)}/anpr`, { signal, timeout: 8_000 });
  },
};
