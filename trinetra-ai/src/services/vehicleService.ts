import type { VehicleEvent, VehicleProfile, VehicleRoute, WatchlistRecord } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { normalisePlate } from '@/lib/utils';
import { mapEvent, mapRoute, mapVehicleProfile, mapWatchlist, unwrapList } from './adapters';

export const vehicleService = {
  async events(plate: string): Promise<VehicleEvent[]> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleEvents(p);
    // Chronological, newest-last: the trace is an ordered sighting sequence.
    const events = unwrapList(
      await get<unknown>(`/vehicles/${encodeURIComponent(p)}/events`, { params: { size: 100, page: 1 } }),
    ).map(mapEvent);
    return events.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  },

  async route(plate: string): Promise<VehicleRoute> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleRoute(p);
    return mapRoute(await get<unknown>(`/vehicles/${encodeURIComponent(p)}/route`));
  },

  async profile(plate: string): Promise<VehicleProfile | null> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleProfile(p);
    return mapVehicleProfile(await get<unknown>(`/vehicles/${encodeURIComponent(p)}`));
  },

  async watchlist(): Promise<WatchlistRecord[]> {
    if (isMockMode) return mock.getWatchlist();
    return unwrapList(await get<unknown>('/watchlist', { params: { size: 100, page: 1 } })).map(
      mapWatchlist,
    );
  },
};
