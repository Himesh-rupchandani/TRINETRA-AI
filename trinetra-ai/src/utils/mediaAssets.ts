import type { SyntheticEvent } from 'react';
import type { VehicleClass } from '@/types';

/**
 * Realistic demo imagery (AI-generated, clearly labelled "demo / synthetic"
 * in the UI). Shown in mock mode so cameras and detections look like a real
 * ANPR deployment. When the backend is connected these are replaced by
 * signed evidence URLs / live streams.
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

const VEHICLES: Record<VehicleClass, string> = {
  CAR: '/evidence/veh-car.jpg',
  MOTORCYCLE: '/evidence/veh-bike.jpg',
  BUS: '/evidence/veh-bus.jpg',
  VAN: '/evidence/veh-van.jpg',
  // NOTE: dedicated truck / rickshaw images pending — reusing close classes.
  TRUCK: '/evidence/veh-van.jpg',
  AUTO_RICKSHAW: '/evidence/veh-bike.jpg',
  UNKNOWN: '/evidence/veh-car.jpg',
};

/** Realistic per-class vehicle image for detection frames (demo mode). */
export function vehicleStill(v?: VehicleClass | null): string {
  return VEHICLES[v ?? 'UNKNOWN'] ?? VEHICLES.CAR;
}

/** Stable pseudo track id for a detection (like the ANPR stage would assign). */
export function trackId(eventId: string): number {
  return 100 + (hash(eventId) % 900);
}
