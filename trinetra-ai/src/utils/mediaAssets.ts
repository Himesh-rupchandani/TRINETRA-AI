import type { SyntheticEvent } from 'react';

/**
 * Demo camera imagery (AI-generated, clearly labelled "demo / synthetic" in the
 * UI). Shown in mock mode so the camera grid looks like a real deployment.
 * When the backend is connected these are replaced by live streams.
 *
 * NOTE: detection evidence is deliberately NOT here. The evidence panel shows
 * only crops the CV engine actually captured (`utils/evidence.ts`), so no
 * generated vehicle photo can ever be passed off as a capture.
 *
 * The image files are OPTIONAL assets: stripped builds may not ship them.
 * Every <img> that uses them pairs with an underlying placeholder layer and
 * this error handler, so a missing file degrades to a clean placeholder
 * instead of a broken-image icon.
 */

/** Hide a failed demo image so the placeholder layer behind it shows. */
export function hideBrokenImage(e: SyntheticEvent<HTMLImageElement>): void {
  e.currentTarget.style.display = 'none';
}

const SCENES = [
  '/cctv/cctv-01.jpg',
  '/cctv/cctv-02.jpg',
  '/cctv/cctv-03.jpg',
  '/cctv/cctv-04.jpg',
  '/cctv/cctv-05.jpg',
  '/cctv/cctv-06.jpg',
];

function hash(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
  return Math.abs(h);
}

/** Stable, realistic CCTV preview image for a camera (demo mode). */
export function cameraStill(cameraId: string): string {
  return SCENES[hash(cameraId.toLowerCase()) % SCENES.length];
}
