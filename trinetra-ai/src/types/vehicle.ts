export type VehicleClass =
  | 'CAR'
  | 'MOTORCYCLE'
  | 'TRUCK'
  | 'BUS'
  | 'AUTO_RICKSHAW'
  | 'VAN'
  | 'UNKNOWN';

export type WatchlistCategory =
  | 'STOLEN VEHICLE'
  | 'WANTED SUSPECT'
  | 'BLACKLISTED'
  | 'EXPIRED PERMIT'
  | 'PERSON OF INTEREST'
  | 'AMBER ALERT';

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

export interface WatchlistRecord {
  id: string;
  plate: string;
  category: WatchlistCategory;
  severity: Severity;
  reason: string;
  caseRef: string;
  addedBy: string;
  addedAt: string;
  active: boolean;
  contact?: string;
}

export interface VehicleProfile {
  plate: string;
  vehicleClass: VehicleClass;
  make?: string;
  model?: string;
  colour?: string;
  owner?: string;
  registrationState?: string;
  firstSeen?: string;
  lastSeen?: string;
  totalSightings: number;
  /** Distinct cameras that have recorded this plate. */
  camerasTouched?: number;
  watchlist?: WatchlistRecord | null;
}

/** One hop of a chronological cross-camera journey. */
export interface RoutePoint {
  sequence: number;
  eventId: string;
  cameraId: string;
  cameraName: string;
  location: string;
  latitude: number;
  longitude: number;
  timestamp: string;
  plateConfidence: number;
  /** Minutes elapsed since the previous point. */
  gapMinutes?: number;
  /** Straight-line km from the previous point. */
  distanceKm?: number;
  speedKmph?: number;
  /** Manually-uploaded CCTV video provenance (absent for live sightings). */
  videoFile?: string;
  /** Position inside the uploaded video, in seconds. */
  videoOffsetSec?: number;
}

export interface VehicleRoute {
  plate: string;
  points: RoutePoint[];
  startedAt?: string;
  endedAt?: string;
  totalDistanceKm: number;
  camerasTouched: number;
}
