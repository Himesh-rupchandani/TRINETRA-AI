export type CameraStatus = 'ONLINE' | 'OFFLINE' | 'DEGRADED';
export type StreamType = 'HLS' | 'RTSP' | 'WEBRTC' | 'MJPEG';

/**
 * Camera as returned by Model 1 (CCTV Registry & GIS Foundation).
 * `streamUrl` is resolved server-side — the frontend never holds
 * Sentinel credentials and never builds an authenticated stream URL itself.
 */
export interface Camera {
  id: string;
  name: string;
  location: string;
  latitude: number;
  longitude: number;
  department?: string;
  status: CameraStatus;
  codec?: string;
  width?: number;
  height?: number;
  fps?: number;
  streamType?: StreamType;
  /** Short-lived, backend-signed playback URL. Absent until requested. */
  streamUrl?: string;
  lastSeen?: string;
  /**
   * True when the backend is serving synthetic frames because the real source
   * is unreachable. Such a camera is NOT a live feed and must be labelled.
   */
  isDemoFeed?: boolean;
  /** Why the live source failed, when the backend reports it. */
  lastError?: string;
  /** ISO timestamp of the most recent AI event on this camera. */
  lastEventAt?: string;
  eventCount24h?: number;
  zone?: string;
  installedAt?: string;
}

export interface CameraFilters {
  query?: string;
  status?: CameraStatus | 'ALL';
  department?: string | 'ALL';
  zone?: string | 'ALL';
  codec?: string | 'ALL';
  /** 'ANY' | 'ACTIVE' (events in last 24h) | 'QUIET' */
  activity?: 'ANY' | 'ACTIVE' | 'QUIET';
}

export interface CameraStreamTicket {
  cameraId: string;
  streamType: StreamType;
  /**
   * Playback URL issued by the backend. For WEBRTC this is the same-origin
   * WHEP signalling endpoint; empty when no source is published.
   */
  streamUrl: string;
  /** ISO expiry of the signed URL. */
  expiresAt: string;
  poster?: string;
}
