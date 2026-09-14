/**
 * PROVIDED PLATES — exact user-supplied evidence images.
 *
 * When a number plate in this set is searched, Vehicle Log / Find a Vehicle /
 * Investigation must show the **exact** provided photo, not a synthetic SVG.
 * The image file is expected at `/plates/<PLATE>.jpg` (public folder).
 * If the file is missing at runtime the caller falls back to synthetic.
 *
 * This module is intentionally tiny and dependency-free so it can be imported
 * in mocks, services, and components without cycles. It also powers the
 * "faster and proper" path: real plates resolve to a static URL (no SVG
 * generation, no extra compute, browser-cached).
 */

export const PROVIDED_PLATES = [
  'RJ19CL5074',
  'GJ03HK2595',
  'GJ03NB2146',
  'GJ03JL5362',
  'GJ03JL2801',
] as const;

export type ProvidedPlate = (typeof PROVIDED_PLATES)[number];

const SET = new Set<string>(PROVIDED_PLATES);

export function isProvidedPlate(plate: string): boolean {
  return SET.has(plate.toUpperCase());
}

/** Static public URL for the exact provided image. No AI substitute. */
export function providedFrameUrl(plate: string): string | null {
  const p = plate.toUpperCase();
  if (!isProvidedPlate(p)) return null;
  // Vite serves `public/` at site root. Keep extension .jpg to match README.
  return `/plates/${p}.jpg`;
}

/** Plate crop uses the same exact photo (full car) — the ANPR stage would
 *  normally produce a tight crop, but for provided evidence the full frame
 *  is authoritative. Callers may style it with object-fit. */
export function providedPlateCropUrl(plate: string): string | null {
  return providedFrameUrl(plate);
}

/** Display metadata for gallery headings / alt text */
export const PROVIDED_PLATE_META: Record<ProvidedPlate, { label: string; desc: string }> = {
  RJ19CL5074: { label: 'RJ19CL5074', desc: 'White Hyundai i20 — front view' },
  GJ03HK2595: { label: 'GJ03HK2595', desc: 'Silver Hyundai i10 — rear, damaged bumper' },
  GJ03NB2146: { label: 'GJ03NB2146', desc: 'Dark grey Alto K10 — rear' },
  GJ03JL5362: { label: 'GJ03JL5362', desc: 'Dark grey Baleno — front' },
  GJ03JL2801: { label: 'GJ03JL2801', desc: 'Grey Suzuki — front' },
};
