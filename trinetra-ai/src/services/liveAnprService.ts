import { get, post } from './api';
import type { TrafficSnapshot } from './trafficService';

export type OcrStage = 'QUEUED' | 'READING' | 'CONFIRMING' | 'CONFIRMED' | 'RECENT_READ' |
  'NO_REGION' | 'TOO_SMALL' | 'NO_TEXT' | 'NO_PLATE_TEXT' | 'LOW_CONFIDENCE' | 'UNAVAILABLE' | 'ERROR';

export interface OcrProgress {
  ocr_state?: OcrStage;
  ocr_agreement_reads?: number;
  ocr_required_reads?: number;
  ocr_region_source?: string | null;
}

export interface LiveDetection extends OcrProgress {
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

export interface LivePhoto extends OcrProgress {
  id: string;
  track_id: number;
  class_name: string;
  image_path: string;
  plate_image_path: string | null;
  captured_at: string;
  media_time: number | null;
  plate_number: string | null;
  plate_status: 'HIGH' | 'LOW_CONFIDENCE' | 'UNKNOWN';
  plate_confidence: number | null;
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
  photos?: LivePhoto[];
  ocr?: { enabled: boolean; loaded: boolean; engine: string | null; state: string };
  traffic?: TrafficSnapshot | null;
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
