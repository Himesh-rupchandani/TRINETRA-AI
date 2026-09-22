import type { Severity, VehicleClass } from './vehicle';

export type EventType =
  | 'VEHICLE_DETECTION'
  | 'ANPR_READ'
  | 'WATCHLIST_MATCH'
  | 'CAMERA_OFFLINE'
  | 'CAMERA_RECOVERED'
  | 'SPEED_VIOLATION'
  | 'WRONG_WAY';

export interface Evidence {
  /** Backend reference; resolved to a signed URL by the evidence service. */
  ref: string;
  frameUrl?: string;
  plateCropUrl?: string;
  capturedAt: string;
  /** Marks demo/synthetic evidence so operators never confuse it with real material. */
  synthetic?: boolean;
}

export interface VehicleEvent {
  id: string;
  cameraId: string;
  cameraName?: string;
  vehicleId?: number;
  plate: string;
  plateConfidence: number;
  /** Exact OCR string before normalisation, so a weak read stays reviewable. */
  plateRaw?: string;
  /** OCR reliability; tentative reads are never silently promoted. */
  plateStatus?: 'HIGH' | 'LOW_CONFIDENCE' | 'UNKNOWN' | 'SIMULATED';
  timestamp: string;
  latitude: number;
  longitude: number;
  location?: string;
  vehicleClass?: VehicleClass;
  colour?: string;
  eventType: EventType;
  severity?: Severity;
  evidenceRef?: string;
  evidence?: Evidence;
  watchlistMatch?: boolean;
  direction?: string;
  speedKmph?: number;
  /** Manually-uploaded CCTV video provenance (absent for live sightings). */
  videoFile?: string;
  /** Position inside the uploaded video, in seconds. */
  videoOffsetSec?: number;
  /** Stored analysis video this sighting was cut from (multi-video analysis only). */
  videoId?: string;
  /** Frame index inside the source video, when the pipeline recorded one. */
  frameNumber?: number;
  /** Vehicle detector box [x1, y1, x2, y2] in source-frame pixels. */
  bbox?: [number, number, number, number];
  /** Vehicle detector confidence (0-100) — not the same thing as the OCR confidence. */
  vehicleConfidence?: number;
}

export interface EventFilters {
  plate?: string;
  cameraId?: string | 'ALL';
  eventType?: EventType | 'ALL';
  severity?: Severity | 'ALL';
  dateFrom?: string;
  dateTo?: string;
  timeFrom?: string;
  timeTo?: string;
  watchlistOnly?: boolean;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}
