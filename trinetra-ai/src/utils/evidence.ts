import type { Evidence } from '@/types';

/**
 * EVIDENCE SOURCE GUARD
 * ---------------------
 * The evidence panel is investigative material, so it shows *only* crops the
 * CV engine actually captured and the backend serves from its evidence store
 * (`GET /api/evidence/{ref}`). Nothing else is allowed to masquerade as
 * evidence: no demo stills, no inlined placeholder art, no generated frames.
 *
 * Demo/synthetic evidence is still produced by the mock dataset (it drives the
 * rest of the demo UI), but it is filtered out here so an operator can never
 * mistake a generated image for a real capture.
 */

/** A crop URL is real only when it resolves to the backend evidence route. */
const EVIDENCE_ROUTE = /\/evidence\/[^/]+/i;

/** True for a URL that can only be a real stored crop. */
export function isRealCropUrl(url?: string | null): url is string {
  if (!url) return false;
  // data:/blob: URLs are generated in the browser, never captured by a camera.
  if (/^(data|blob):/i.test(url)) return false;
  return EVIDENCE_ROUTE.test(url);
}

export interface RealEvidence {
  /** Full-frame crop stored by the CV engine (absent for crop-only refs). */
  frameUrl?: string;
  /** ANPR plate crop stored by the CV engine. */
  plateCropUrl?: string;
  /** Backend reference (what an operator quotes in a case note). */
  ref?: string;
  capturedAt?: string;
}

/**
 * Extract the real captured crops from an event's evidence, or `null` when this
 * sighting has no genuine imagery (demo data, or a frame that was never stored).
 */
export function realCrops(evidence?: Evidence | null): RealEvidence | null {
  if (!evidence || evidence.synthetic) return null;
  const frameUrl = isRealCropUrl(evidence.frameUrl) ? evidence.frameUrl : undefined;
  const plateCropUrl = isRealCropUrl(evidence.plateCropUrl) ? evidence.plateCropUrl : undefined;
  if (!frameUrl && !plateCropUrl) return null;
  return { frameUrl, plateCropUrl, ref: evidence.ref, capturedAt: evidence.capturedAt };
}

/** Append a cache-busting token so "refresh" re-fetches the crop from disk. */
export function withCacheBust(url: string, nonce: number): string {
  if (nonce <= 0) return url;
  return `${url}${url.includes('?') ? '&' : '?'}r=${nonce}`;
}
