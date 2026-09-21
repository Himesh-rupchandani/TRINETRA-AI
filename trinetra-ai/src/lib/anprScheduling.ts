import type { LiveAnprSnapshot } from '@/services/liveAnprService';

/** Poll small JSON when the worker is busy/unavailable instead of encoding/uploading a frame. */
export function frameAdmissionDelay(snapshot: LiveAnprSnapshot, sourceId: string): number {
  if (snapshot.resource_budget?.allowed === false || ['UNAVAILABLE','DISABLED','ERROR'].includes(snapshot.status)) return Math.max(5000, snapshot.retry_after_ms ?? 0);
  if (snapshot.pending || snapshot.status === 'BUSY') return Math.max(750, snapshot.retry_after_ms ?? 0);
  const leaseMs = Math.max(3000, snapshot.sample_interval_ms * 3);
  if (snapshot.source_id && snapshot.source_id !== sourceId && snapshot.result_age_ms != null && snapshot.result_age_ms < leaseMs) return 1500;
  return 0;
}

/** Preserve pixel detail; back off sampling, not the native video's frame rate. */
export function nextSampleDelay(snapshot: LiveAnprSnapshot, captureMs: number, dropped: number, elapsedFrames: number): number {
  const base = Math.max(1000, snapshot.sample_interval_ms || 1000);
  const congested = captureMs > 80 || (elapsedFrames > 0 && dropped/elapsedFrames > .1);
  return Math.max(base, snapshot.retry_after_ms ?? 0, congested ? 2500 : 0);
}


/** Stable for a playback session. Toggle commands do not change this URL. */
export function controlledMjpegUrl(url: string, viewerId: string, initialEnabled: boolean) {
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}viewer_id=${encodeURIComponent(viewerId)}&analysis=${initialEnabled ? 'true' : 'false'}`;
}


/** Explicit, camera-scoped opt-in; never inherit another camera's ON state. */
export function cameraDetectionEnabled(cameraId: string, enabledCameraId: string | null): boolean {
  return enabledCameraId != null && enabledCameraId === cameraId.toLowerCase();
}
