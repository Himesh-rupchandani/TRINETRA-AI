import type { VehicleEvent, VehicleProfile, VehicleRoute, WatchlistRecord } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { normalisePlate } from '@/lib/utils';
import { cameraService } from './cameraService';
import {
  toVehicleEvent,
  toVehicleRoute,
  toWatchlistRecord,
  unwrapList,
  withCameraContext,
  type RouteDto,
  type VehicleEventDto,
  type WatchlistDto,
} from './adapters';

/**
 * Vehicle investigation service — the hero flow (spec Phase 12/13/27).
 *
 * Sightings are always returned in chronological order so the cross-camera
 * trace (CAM04 -> CAM08 -> CAM12 -> CAM17) can never render out of sequence.
 */
export const vehicleService = {
  async events(plate: string): Promise<VehicleEvent[]> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleEvents(p);

    const [raw, cameras] = await Promise.all([
      get<unknown>(`/vehicles/${encodeURIComponent(p)}/events`),
      cameraService.index(),
    ]);
    const events = unwrapList<VehicleEventDto>(raw).map(toVehicleEvent);
    events.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    return withCameraContext(events, cameras);
  },

  async route(plate: string): Promise<VehicleRoute> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleRoute(p);

    const [dto, cameras] = await Promise.all([
      get<RouteDto>(`/vehicles/${encodeURIComponent(p)}/route`),
      cameraService.index(),
    ]);
    return toVehicleRoute(dto, cameras);
  },

  /**
   * Vehicle profile. The backend exposes no `/vehicles/{plate}` resource, so
   * the profile is derived from the vehicle's own sightings plus the watchlist
   * — no invented owner/make/model fields in LIVE mode.
   */
  async profile(plate: string): Promise<VehicleProfile | null> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleProfile(p);

    const [events, watchlist] = await Promise.all([
      vehicleService.events(p),
      vehicleService.watchlist(),
    ]);
    if (!events.length) return null;

    return {
      plate: p,
      vehicleClass: events[0].vehicleClass ?? 'UNKNOWN',
      registrationState: p.startsWith('GJ') ? 'Gujarat' : 'Other State',
      firstSeen: events[0].timestamp,
      lastSeen: events[events.length - 1].timestamp,
      totalSightings: events.length,
      watchlist: watchlist.find((w) => w.plate === p && w.active) ?? null,
    };
  },

  async watchlist(): Promise<WatchlistRecord[]> {
    if (isMockMode) return mock.getWatchlist();
    const raw = await get<unknown>('/watchlist');
    return unwrapList<WatchlistDto>(raw).map(toWatchlistRecord);
  },
};
