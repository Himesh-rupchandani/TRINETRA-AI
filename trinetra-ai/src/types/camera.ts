/**
 * Camera lifecycle states as the backend reports them
 * (`GET /api/cameras` -> `_resolve_camera_status`).
 *
 * `NOT_CONFIGURED` is a real, distinct backend state: the registry slot exists
 * but no stream source has been authorized yet. It used to be collapsed into
 * `OFFLINE` by the adapter, so an idle/unprovisioned camera was rendered as a
 * *fault* ("Not working", red) and counted as an outage.
 */
export type CameraStatus = 'ONLINE' | 'OFFLINE' | 'DEGRADED' | 'NOT_CONFIGURED';
export type StreamType = 'HLS' | 'RTSP' | 'WEBRTC' | 'MJPEG' | 'FILE';

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
  /**
   * Same-origin MJPEG view of this camera with real-time OpenCV vehicle
   * detection (green bounding boxes) rendered by the backend. Absent when the
   * backend cannot process the source.
   */
  detectionUrl?: string;
}
