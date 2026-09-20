import type { VehicleEvent } from '@/types';
import type { LiveAnprSnapshot } from '@/services/liveAnprService';

/** object-contain geometry, in the sampled frame's coordinate system. */
export function containedBox(box: readonly number[], frameW: number, frameH: number, width: number, height: number) {
  const scale = Math.min(width / frameW, height / frameH);
  const left = (width - frameW * scale) / 2;
  const top = (height - frameH * scale) / 2;
  return [box[0] * scale + left, box[1] * scale + top,
    (box[2] - box[0]) * scale, (box[3] - box[1]) * scale] as const;
}

/** Never overlay a different viewer's file offset, a pre-seek frame or stale boxes. */
export function canDrawSnapshot(result: LiveAnprSnapshot, sourceId: string, mediaTime: number) {
  return result.source_id === sourceId && result.frame_width > 0 && result.frame_height > 0 &&
    result.result_age_ms != null && result.result_age_ms <= result.overlay_ttl_ms &&
    (result.media_time == null || (mediaTime >= result.media_time &&
      mediaTime - result.media_time <= result.overlay_ttl_ms / 1000));
}

/** Shared with the realtime provider; reconnect duplicates never grow a list. */
export function mergeLiveEvent(events: VehicleEvent[], incoming: VehicleEvent, limit = 60) {
  return [incoming, ...events.filter((event) => event.id !== incoming.id)].slice(0, limit);
}

/** Bounded, camera-scoped notification gate (not a watchlist alert generator). */
export class PlateNotificationGate {
  private seen = new Map<string, number>();
  private plates = new Map<string, number>();

  accept(event: VehicleEvent, now = Date.now()) {
    for (const [key, time] of this.plates) if (now - time > 60_000) this.plates.delete(key);
    if (this.seen.has(event.id)) return false;
    this.seen.set(event.id, now);
    if (this.seen.size > 1000) this.seen.delete(this.seen.keys().next().value!);
    if (!event.plate || !Number.isFinite(event.plateConfidence) || event.plateConfidence < 60 || event.watchlistMatch ||
        event.plateStatus === 'UNKNOWN' || event.plateStatus === 'SIMULATED') return false;
    const key = `${event.cameraId.toLowerCase()}:${event.plate.replace(/[^A-Z0-9]/gi, '').toUpperCase()}`;
    const previous = this.plates.get(key);
    this.plates.set(key, now);
    if (this.plates.size > 1000) this.plates.delete(this.plates.keys().next().value!);
    return previous == null || now - previous >= 60_000;
  }
}

/** Playback can recover onto a raw stream without pretending ANPR recovered too. */
export function anprStatusLabel(snapshot: LiveAnprSnapshot | null, error: string | null, rawFallback = false) {
  if (rawFallback || error || snapshot?.status === 'UNAVAILABLE' || snapshot?.status === 'ERROR') return 'ANPR UNAVAILABLE';
  if (snapshot?.status === 'DISABLED') return 'ANPR OFF';
  if (snapshot?.status === 'SHARED') return 'ANPR · SHARED';
  if (snapshot?.status === 'BUSY') return 'ANPR · BUSY';
  if (snapshot?.status === 'SCANNING' || snapshot?.status === 'PROCESSING') return `ANPR · UP TO ${snapshot.max_vehicles}`;
  return 'ANPR · CHECKING';
}

/** Mirrors the backend's inexpensive scene-cut guard, not an accuracy model. */
export function matchesSceneSignature(signature: readonly number[] | undefined, rgba: Uint8ClampedArray) {
  if (!signature) return true; // rolling upgrade from an older backend
  if (signature.length !== 16 * 9 || rgba.length !== signature.length * 4) return false;
  let difference = 0;
  for (let i = 0; i < signature.length; i++) {
    if (!Number.isFinite(signature[i])) return false;
    const pixel = i * 4;
    const luminance = 0.299 * rgba[pixel] + 0.587 * rgba[pixel + 1] + 0.114 * rgba[pixel + 2];
    difference += Math.abs(signature[i] - luminance);
  }
  return difference / signature.length <= 24;
}
