import type { VehicleEvent } from '@/types';
import { apiAssetUrl } from '@/services/api';

/**
 * Source-video addressing for the evidence panel.
 *
 * Uploaded / analysed footage stores one vehicle crop per track and never a
 * plate sidecar (see `evidencePaths`), so the useful follow-up is the video
 * itself at the second the reading was taken. Two pipelines produce those
 * sightings, and each streams its file from a different endpoint.
 */

/** Streams the video this sighting was cut from; undefined when there is none. */
export function sourceVideoUrl(event: VehicleEvent): string | undefined {
  // Multi-video analysis stores per-video files, addressable only by video id.
  if (event.videoId) {
    return apiAssetUrl(`/analysis/videos/${encodeURIComponent(event.videoId)}/file`);
  }
  // Manually-uploaded footage became a camera, so the camera id is the handle.
  // An `analysis/` reference without a video id has no stream to offer, and a
  // guessed endpoint would only ever 404 — show the frame, not a broken player.
  if (!event.evidenceRef?.startsWith('uploads/') || !event.cameraId) return undefined;
  return apiAssetUrl(`/uploads/videos/${encodeURIComponent(event.cameraId)}/file`);
}

/** True when the frame slot can be swapped for the source video at that moment. */
export function hasSourceMoment(event: VehicleEvent): boolean {
  return event.videoOffsetSec != null
    && !event.evidence?.synthetic
    && Boolean(sourceVideoUrl(event));
}
