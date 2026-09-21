import type { VehicleEvent } from '@/types';

/** Resolve real evidence without turning a public URL into a broken local path. */
export function evidencePaths(ref: string | undefined, hasPlate: boolean) {
  const value = ref?.trim();
  if (!value) return undefined;
  if (/^https?:\/\//i.test(value)) {
    try {
      const url = new URL(value);
      if (url.username || url.password) return undefined;
      // Signed/external URLs must stay intact. Do not invent a plate sidecar.
      return { framePath: value, platePath: undefined };
    } catch { return undefined; }
  }
  const relative = value.replace(/^\/api\/(?:v1\/)?evidence\//, '');
  if (relative.startsWith('/') || relative.includes('\\') || /^[a-z][a-z0-9+.-]*:/i.test(relative)) return undefined;
  for (const char of relative) if (char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127) return undefined;
  const parts = relative.split('/');
  if (parts.some((part) => part === '..' || part === '.')) return undefined;
  const encoded = parts.map(encodeURIComponent).join('/');
  const framePath = `/evidence/${encoded}`;
  const isUpload = relative.startsWith('uploads/') || relative.startsWith('analysis/');
  return {
    framePath,
    platePath: hasPlate && !isUpload && /\.jpe?g$/i.test(relative)
      ? framePath.replace(/\.jpe?g$/i, '_plate.jpg') : undefined,
  };
}

/** Latest saved photo, independent of history/watchlist filters or feed pause. */
export function latestCameraEvidence(cameraId: string, events: VehicleEvent[]) {
  return events.filter((event) => event.cameraId.toLowerCase() === cameraId.toLowerCase() && event.evidence?.frameUrl)
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))[0] ?? null;
}
